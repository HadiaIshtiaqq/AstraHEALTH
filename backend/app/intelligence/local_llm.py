"""Optional local LLM runtime client (Ollama on loopback only).

The LLM only drafts plain-language explanations of findings that the deterministic
pipeline has already produced. Its output never feeds the rule engine.
"""
from __future__ import annotations

import json
import time
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.netguard import is_loopback_host

PROMPT_VERSION = "explain-v1.2"


class LLMUnavailable(RuntimeError):
    pass


def _base_url() -> str:
    url = settings.local_llm_base_url.rstrip("/")
    host = urlparse(url).hostname
    if not is_loopback_host(host):
        raise LLMUnavailable(f"Refusing non-loopback LLM endpoint '{host}' (local inference only)")
    return url


def health(timeout: float = 1.5) -> dict:
    info = {"provider": settings.local_llm_provider, "model": settings.local_llm_model,
            "enabled": settings.local_llm_enabled, "base_url": settings.local_llm_base_url,
            "reachable": False, "model_available": False, "prompt_version": PROMPT_VERSION}
    if not settings.local_llm_enabled:
        info["detail"] = "Disabled by configuration"
        return info
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.get(f"{_base_url()}/api/tags")
            resp.raise_for_status()
            names = [m.get("name") for m in resp.json().get("models", [])]
        info.update(reachable=True, installed_models=names,
                    model_available=settings.local_llm_model in names)
        if not info["model_available"]:
            info["detail"] = f"Model '{settings.local_llm_model}' is not installed (ollama pull {settings.local_llm_model})"
    except (httpx.HTTPError, LLMUnavailable, OSError) as exc:
        info["detail"] = f"Runtime not reachable: {type(exc).__name__}"
    return info


def free_ram_gb() -> float | None:
    """Available physical memory in GB (Windows), or None when it cannot be read."""
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return status.ullAvailPhys / 1024**3
    except (AttributeError, OSError):
        return None


def should_keep_loaded() -> bool:
    """Keep the model resident only when it will not push the analysis pipeline into swapping."""
    free = free_ram_gb()
    return free is not None and free >= settings.llm_min_free_ram_gb


def keep_alive() -> str:
    # On a low-memory laptop the model is unloaded soon after each explanation so analysis stays fast.
    return "30m" if should_keep_loaded() else "1m"


def warm_up() -> bool:
    """Load the model into memory in the background at startup so the first explanation is not a cold start."""
    try:
        with httpx.Client(timeout=300, trust_env=False) as client:
            client.post(f"{_base_url()}/api/generate", json={"model": settings.local_llm_model, "prompt": "ok",
                                                              "stream": False, "keep_alive": keep_alive(),
                                                              "options": {"num_predict": 1}})
        return True
    except (httpx.HTTPError, LLMUnavailable, OSError):
        return False


def generate_json(prompt: str, system: str) -> tuple[dict, dict]:
    """Call the local model and return (parsed_json, metadata). Raises LLMUnavailable."""
    if not settings.local_llm_enabled:
        raise LLMUnavailable("Local LLM disabled by configuration")
    started = time.perf_counter()
    payload = {
        "model": settings.local_llm_model,
        "system": system,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 450, "num_ctx": 2048, "seed": 7},
        "keep_alive": keep_alive(),
    }
    try:
        with httpx.Client(timeout=settings.local_llm_timeout_s, trust_env=False) as client:
            resp = client.post(f"{_base_url()}/api/generate", json=payload)
            resp.raise_for_status()
            body = resp.json()
    except (httpx.HTTPError, OSError) as exc:
        raise LLMUnavailable(f"Local LLM call failed: {type(exc).__name__}") from exc
    meta = {"model": body.get("model", settings.local_llm_model), "latency_ms": round((time.perf_counter() - started) * 1000),
            "prompt_version": PROMPT_VERSION, "eval_count": body.get("eval_count")}
    text = body.get("response", "")
    try:
        return json.loads(text), meta
    except json.JSONDecodeError as exc:
        repaired = _repair_truncated(text)
        if repaired is not None:
            meta["repaired_truncated_json"] = True
            return repaired, meta
        meta["raw_response"] = text[:500]
        raise ValueError("LLM output is not valid JSON") from exc


def _repair_truncated(text: str) -> dict | None:
    """Keep only the complete statement objects of a JSON reply cut off by the token limit."""
    end = text.rfind("}")
    while end > 0:
        try:
            parsed = json.loads(text[: end + 1] + "]}")
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            end = text.rfind("}", 0, end)
    return None
