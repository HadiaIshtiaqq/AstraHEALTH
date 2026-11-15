"""PDF export (dependency-free PDF 1.4 writer) and passphrase-encrypted exports."""
from __future__ import annotations

import base64
import os
import textwrap

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"ASTRAENC1"
_REPLACE = {"—": "-", "–": "-", "·": "|", "→": "->", "“": '"', "”": '"', "‘": "'", "’": "'", "≥": ">=", "≤": "<=",
            "µ": "u", "…": "...", "±": "+/-", "•": "*"}


def _latin(text: str) -> str:
    for a, b in _REPLACE.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


def _esc(text: str) -> str:
    return _latin(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def report_lines(report: dict) -> list[tuple[str, str]]:
    """(style, text) lines; style: h1 | h2 | b | n | small."""
    h = report["header"]
    a = report.get("latest_assessment") or {}
    out = [("h1", "ASTRAHEALTH AI - Mission Health Report"),
           ("small", f"Report {report['report_id']} | generated {report['generated_at']} " + (" | SYNTHETIC DATA" if report.get("is_synthetic") else "")),
           ("b", report["disclaimer"]),
           ("h2", "Header"),
           ("n", f"Profile: {h['profile_alias']} ({h['profile_id']})  Mission: {h['mission']}, day {h['mission_day']}"),
           ("n", f"Window: {h['window_start']} to {h['window_end']}"),
           ("n", f"Versions: app {report['versions']['app']}; rules {report['versions']['ruleset']} "
                 f"({report['versions']['ruleset_status']}); {report['versions']['anomaly_model']}; index {report['versions']['knowledge_index']}"),
           ("h2", "Latest assessment"),
           ("b", f"{a.get('state_label', 'No analysis in window - status unknown')}"),
           ("n", a.get("headline", "")),
           ("n", f"Unresolved REVIEW/URGENT alerts: {report['unresolved_alerts']}"),
           ("h2", f"Findings ({len(report['findings'])})")]
    for f in report["findings"]:
        out.append(("b", f"[{f['severity']}] {f['code']} ({f.get('agent_id')}; rules {', '.join(f['rule_ids']) or '-'})"))
        out.append(("n", f["summary"]))
        if f["next_steps"]:
            out.append(("n", "Next step: " + f["next_steps"][0]))
        refs = "; ".join(f"{r['title']} - {r['section']} [{r['chunk_id']}]" for r in f["references"]) or f["evidence_status"]
        out.append(("small", f"Evidence: {refs}. Source observations: {', '.join(f['evidence_observation_ids'][:6]) or 'none'}"))
    out.append(("h2", f"Alerts ({len(report['alerts'])})"))
    for al in report["alerts"]:
        out.append(("n", f"[{al['severity']}] {al['title']} - {al['state']} - {al['created_at']}"))
        out.append(("small", f"{al['reason']} Next step: {al['next_step']}"))
    out.append(("h2", "Metric summary"))
    for m in report["metric_summaries"]:
        out.append(("n", f"{m['label']} ({m['unit']}): n={m['n']}  min={m['min'] if m['min'] is not None else 'missing'}  "
                         f"median={m['median'] if m['median'] is not None else '-'}  max={m['max'] if m['max'] is not None else '-'}"))
    out.append(("h2", f"Measurements ({len(report['measurements'])})"))
    for m in report["measurements"]:
        out.append(("small", f"{m['measured_at']}  {m['label']}: {m['value']} {m['unit']}  "
                             f"[{m['source']}, {m['quality_status']}] {m['observation_id']}"))
    out.append(("h2", "Sources"))
    out += [("n", f"{s['title']} - {s['publisher']}, v{s['version']} ({s['publication_date']})") for s in report["sources"]] or [("n", "No evidence cited.")]
    return out


def render_pdf(report: dict) -> bytes:
    styles = {"h1": ("F2", 15, 20, 80), "h2": ("F2", 11.5, 17, 96), "b": ("F2", 9, 12, 112), "n": ("F1", 9, 12, 112),
              "small": ("F1", 7.5, 10, 135)}
    width, height, margin = 595, 842, 48
    pages: list[list[str]] = [[]]
    y = height - margin
    for style, text in report_lines(report):
        font, size, lead, wrap = styles[style]
        if style == "h2":
            y -= 6
        for chunk in textwrap.wrap(_latin(text), wrap) or [""]:
            if y < margin + lead:
                pages.append([])
                y = height - margin
            pages[-1].append(f"BT /{font} {size} Tf {margin} {y:.1f} Td ({_esc(chunk)}) Tj ET")
            y -= lead
    total = len(pages)
    objects: list[bytes] = []

    def add(obj: str | bytes) -> int:
        objects.append(obj.encode("latin-1") if isinstance(obj, str) else obj)
        return len(objects)

    catalog = add("<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add("")  # placeholder
    f1 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    kids = []
    for n, lines in enumerate(pages, start=1):
        footer = f"BT /F1 7.5 Tf {margin} 24 Td (ASTRAHEALTH AI prototype - not a medical device - synthetic data | page {n}/{total}) Tj ET"
        stream = "\n".join(lines + [footer]).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {width} {height}] "
                        f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {content} 0 R >>"))
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _key(passphrase: str, salt: bytes) -> bytes:
    return base64.urlsafe_b64encode(Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8")))


def encrypt(data: bytes, passphrase: str) -> bytes:
    if len(passphrase) < 10:
        raise ValueError("Passphrase must be at least 10 characters.")
    salt = os.urandom(16)
    return MAGIC + salt + Fernet(_key(passphrase, salt)).encrypt(data)


def decrypt(blob: bytes, passphrase: str) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("Not an ASTRAHEALTH encrypted export")
    salt, token = blob[len(MAGIC):len(MAGIC) + 16], blob[len(MAGIC) + 16:]
    try:
        return Fernet(_key(passphrase, salt)).decrypt(token)
    except InvalidToken as exc:
        raise ValueError("Wrong passphrase or corrupted file") from exc
