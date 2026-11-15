"""Local retrieval over the curated knowledge library.

Pipeline (TRD 6.4): registry -> extract text with section identifiers -> chunk by
section -> local vectorisation -> persisted index (knowledge/index) + chunk text in
SQLite -> top-k retrieval with a minimum relevance score -> chunk IDs validated
before citation.

Scoring: Okapi BM25 with a small domain synonym map, implemented in NumPy so no model
download is needed. Retrieval remains lexical (not semantic). The Sentence-Transformers/FAISS option in
the TRD can replace `_vectorise` without changing the interface.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from collections import Counter
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.db.database import Database, dumps

INDEX_VERSION = "bm25-1.1.0"
MIN_SCORE = 0.12  # fraction of the best achievable BM25 score for the query
BM25_K1, BM25_B = 1.5, 0.75
# Domain synonyms (lexical retrieval cannot infer these on its own).
SYNONYMS: dict[str, tuple[str, ...]] = {
    "pulse": ("heart rate",), "hr": ("heart rate",), "heart": ("cardiovascular",), "bp": ("blood pressure",),
    "tired": ("fatigue", "sleep"), "exhaust": ("fatigue",), "fatigue": ("tired", "sleep"), "sleepy": ("sleep", "fatigue"),
    "insomnia": ("sleep loss",), "sad": ("mood", "wellbeing"), "lonely": ("isolation", "confinement"), "mood": ("wellbeing",),
    "stress": ("wellbeing", "behavioral"), "anxious": ("stress", "wellbeing"), "dizzy": ("dizziness", "light-headedness"),
    "dizziness": ("light-headedness", "orthostatic"), "breathless": ("breathlessness",), "water": ("fluid intake",),
    "hydration": ("fluid intake",), "drink": ("fluid intake",), "weight": ("body mass",), "workout": ("exercise",),
    "exercise": ("countermeasure",), "bone": ("musculoskeletal", "bone density"), "muscle": ("musculoskeletal",),
    "back": ("spine",), "eye": ("vision",), "vision": ("neuro-ocular",), "radiation": ("dosimetry", "dose"),
    "anomaly": ("unusual pattern",), "baseline": ("personal history",),
}
STOPWORDS = set("""
a an and are as at be been but by can could do does for from had has have how if in into is it its may might more most
no not of on or should so such than that the their them then there these they this those to too was were what when
which while who will with would you your our we i me my also over after before during about any all each other only
""".split())

_lock = threading.Lock()


def _stem(token: str) -> str:
    for suffix in ("ations", "ation", "ments", "ment", "ness", "ings", "ing", "ies", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return token


def tokenize(text: str) -> list[str]:
    tokens = [_stem(t) for t in re.findall(r"[a-z][a-z0-9\-]+", text.lower()) if t not in STOPWORDS]
    return tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]


def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Split into (section, text) pairs by '## ' headings; drop the title and disclaimer lines."""
    sections: list[tuple[str, str]] = []
    current, buf = "Introduction", []
    for line in text.splitlines():
        if line.startswith("## "):
            if "".join(buf).strip():
                sections.append((current, " ".join(buf).strip()))
            current, buf = line[3:].strip(), []
        elif line.startswith("# ") or line.startswith(">"):
            continue
        else:
            buf.append(line.strip())
    if "".join(buf).strip():
        sections.append((current, " ".join(buf).strip()))
    return sections


class KnowledgeIndex:
    def __init__(self) -> None:
        self.ready = False
        self.error: str | None = None
        self.vocab: dict[str, int] = {}
        self.idf: np.ndarray | None = None
        self.matrix: np.ndarray | None = None
        self.chunks: list[dict] = []
        self.documents: dict[str, dict] = {}

    # ---------------------------------------------------------------- build
    def build(self, db: Database, knowledge_dir: Path | None = None) -> dict:
        knowledge_dir = knowledge_dir or settings.knowledge_dir
        with _lock:
            try:
                registry = json.loads((knowledge_dir / "source_registry.json").read_text(encoding="utf-8"))
                docs, chunks = [], []
                for entry in registry["documents"]:
                    path = knowledge_dir / entry["file"]
                    raw = path.read_bytes()
                    text = raw.decode("utf-8")
                    doc = {
                        "document_id": entry["document_id"], "title": entry["title"], "publisher": entry["publisher"],
                        "version": entry.get("version"), "publication_date": entry.get("publication_date"),
                        "local_path": entry["file"], "checksum": hashlib.sha256(raw).hexdigest()[:16],
                        "related_reference": entry.get("related_reference"), "document_type": entry.get("document_type"),
                    }
                    docs.append(doc)
                    for i, (section, body) in enumerate(chunk_markdown(text) if path.suffix == ".md"
                                                        else [(f"Part {j + 1}", p) for j, p in enumerate(
                                                            [p for p in text.split("\n\n") if p.strip()])]):
                        chunks.append({
                            "chunk_id": f"{entry['document_id']}-C{i + 1:02d}",
                            "document_id": entry["document_id"],
                            "page_or_section": section,
                            "text": body,
                        })
                self._vectorise(chunks)
                self.documents = {d["document_id"]: d for d in docs}
                self.chunks = chunks
                with db.transaction() as conn:
                    conn.execute("DELETE FROM evidence_chunks")
                    conn.execute("DELETE FROM knowledge_documents")
                    conn.executemany(
                        "INSERT INTO knowledge_documents VALUES (:document_id,:title,:publisher,:version,:publication_date,"
                        ":local_path,:checksum,:related_reference,:document_type)", docs)
                    conn.executemany(
                        "INSERT INTO evidence_chunks VALUES (?,?,?,?,?)",
                        [(c["chunk_id"], c["document_id"], c["page_or_section"], c["text"], i) for i, c in enumerate(chunks)])
                self._persist(knowledge_dir / "index")
                self.ready, self.error = True, None
            except Exception as exc:  # index failure must not take the app down
                self.ready, self.error = False, f"{type(exc).__name__}: {exc}"
            return self.status()

    def _vectorise(self, chunks: list[dict]) -> None:
        """Okapi BM25 statistics (term-frequency matrix, IDF, document lengths)."""
        docs_tokens = [tokenize(c["page_or_section"] + " " + c["page_or_section"] + " " + c["text"]) for c in chunks]
        df: Counter = Counter()
        for toks in docs_tokens:
            df.update(set(toks))
        self.vocab = {t: i for i, t in enumerate(sorted(df))}
        n = len(chunks)
        self.idf = np.array([math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in sorted(df)])
        tf = np.zeros((n, len(self.vocab)))
        for row, toks in enumerate(docs_tokens):
            for tok, count in Counter(toks).items():
                tf[row, self.vocab[tok]] = count
        self.doc_len = tf.sum(axis=1)
        self.avgdl = float(self.doc_len.mean()) if n else 1.0
        self.matrix = tf

    def _query_weights(self, query: str) -> dict[int, float]:
        """Query terms (weight 1.0) plus domain synonyms (weight 0.5)."""
        weights: dict[int, float] = {}
        base = tokenize(query)
        for tok in base:
            if tok in self.vocab:
                weights[self.vocab[tok]] = 1.0
        for tok in list(base):
            for syn in SYNONYMS.get(tok, ()):
                for s in tokenize(syn):
                    if s in self.vocab and self.vocab[s] not in weights:
                        weights[self.vocab[s]] = 0.5
        return weights

    def _persist(self, index_dir: Path) -> None:
        index_dir.mkdir(parents=True, exist_ok=True)
        np.save(index_dir / "bm25_tf.npy", self.matrix)
        (index_dir / "index_meta.json").write_text(dumps({
            "index_version": INDEX_VERSION, "chunks": [c["chunk_id"] for c in self.chunks],
            "vocab_size": len(self.vocab), "documents": list(self.documents), "k1": BM25_K1, "b": BM25_B,
        }), encoding="utf-8")

    # ---------------------------------------------------------------- query
    def search(self, query: str, k: int = 3, min_score: float = MIN_SCORE, document_ids: list[str] | None = None) -> list[dict]:
        if not self.ready or self.matrix is None or not len(self.chunks):
            raise RuntimeError("Knowledge index unavailable")
        weights = self._query_weights(query)
        if not weights:
            return []
        idx = np.array(list(weights))
        w = np.array([weights[i] for i in idx])
        tf = self.matrix[:, idx]
        norm = BM25_K1 * (1 - BM25_B + BM25_B * self.doc_len / self.avgdl)
        contrib = self.idf[idx] * tf * (BM25_K1 + 1) / (tf + norm[:, None])
        raw = (contrib * w).sum(axis=1)
        # Normalise by the best achievable score for this query so a fixed relevance threshold is meaningful.
        best = float((self.idf[idx] * (BM25_K1 + 1) * w).sum()) or 1.0
        scores = raw / best
        order = np.argsort(-scores)
        out = []
        for i in order:
            if scores[i] < min_score or len(out) >= k:
                break
            chunk = self.chunks[int(i)]
            if document_ids and chunk["document_id"] not in document_ids:
                continue
            doc = self.documents[chunk["document_id"]]
            out.append({
                "chunk_id": chunk["chunk_id"], "document_id": doc["document_id"], "title": doc["title"],
                "publisher": doc["publisher"], "version": doc["version"], "publication_date": doc["publication_date"],
                "section": chunk["page_or_section"], "passage": chunk["text"], "score": round(float(scores[i]), 3),
                "related_reference": doc.get("related_reference"), "document_type": doc.get("document_type"),
            })
        return out

    def has_chunk(self, chunk_id: str) -> bool:
        return any(c["chunk_id"] == chunk_id for c in self.chunks)

    def status(self) -> dict:
        return {"ready": self.ready, "error": self.error, "index_version": INDEX_VERSION,
                "documents": len(self.documents), "chunks": len(self.chunks), "vocab_size": len(self.vocab),
                "min_score": MIN_SCORE}


knowledge_index = KnowledgeIndex()
