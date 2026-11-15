"""Local access control and secrets for a single-laptop prototype.

Secrets live in backend/data/credentials.json (format v3):
- PINs (medical officer, admin) are stored only as salted scrypt hashes. Plain values are written once to
  INITIAL_SECRETS.txt for the operator to note down and delete.
- Wrong PINs trigger a short, fixed cool-down (60 s per 5 failures) and are audited. The cool-down limits
  guessing to ~5 attempts/minute (a 6-digit PIN would take months) without letting another program lock
  the medical officer out for long.
- Device records need a device token (hashed).
- The data-encryption key is wrapped with Windows DPAPI: unreadable under another user account or on another
  machine.

Not an operational identity system: PINs are per role, not per person.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import os
import secrets
import stat
import sys
import threading
import time

from fastapi import Header, HTTPException

from app.core.config import settings

_cache: dict | None = None
_lock = threading.Lock()
_failures: dict[str, dict] = {}
MAX_FAILURES = 5
COOLDOWN_S = 60
PIN_KINDS = ("medical_officer_pin", "admin_pin")


# ---------------------------------------------------------------- DPAPI (Windows user-bound key protection)
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes | None:
    if sys.platform != "win32":
        return None
    try:
        crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
        buf = ctypes.create_string_buffer(data, len(data))
        blob_in, blob_out = _Blob(len(data), buf), _Blob()
        fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        if not fn(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):
            return None
        out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        kernel32.LocalFree(blob_out.pbData)
        return out
    except (AttributeError, OSError):
        return None


def _wrap(raw: bytes) -> dict:
    protected = _dpapi(raw, protect=True)
    return {"dpapi": base64.b64encode(protected).decode()} if protected is not None else {"plain": raw.hex()}


def _unwrap(entry: dict) -> bytes:
    if "dpapi" in entry:
        raw = _dpapi(base64.b64decode(entry["dpapi"]), protect=False)
        if raw is None:
            raise RuntimeError("Key cannot be unwrapped by this Windows account (DPAPI).")
        return raw
    return bytes.fromhex(entry["plain"])


# ---------------------------------------------------------------- credentials file
def credentials_path():
    return settings.database_path.parent / "credentials.json"


def initial_secrets_path():
    return settings.database_path.parent / "INITIAL_SECRETS.txt"


def _hash_pin(pin: str, salt: bytes | None = None) -> dict:
    salt = salt or os.urandom(16)
    return {"salt": salt.hex(), "hash": hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()}




def _write(path, data: dict) -> None:
    if path.exists():
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_credentials() -> dict:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        path = credentials_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if data.get("version") == 3:
            _cache = data
            return _cache
        plain: dict[str, str] = {}
        if data.get("version") == 2:  # migrate: keep PIN hashes and data key, wrap/replace the rest
            pins, device, data_key = data["pins"], data["device_token"], data["data_key"]
        else:  # first start or v1 (plain-text PINs)
            for kind, env in (("medical_officer_pin", "MEDICAL_OFFICER_PIN"), ("admin_pin", "ADMIN_PIN")):
                plain[kind] = data.get(kind) or os.environ.get(env) or f"{secrets.randbelow(10**6):06d}"
            plain["device_token"] = os.environ.get("DEVICE_TOKEN") or secrets.token_urlsafe(18)
            pins = {k: _hash_pin(plain[k]) for k in PIN_KINDS}
            device, data_key = _hash_pin(plain["device_token"]), _wrap(os.urandom(32))
        data = {"version": 3, "pins": pins, "device_token": device, "data_key": data_key, "secret_keys": {}}
        _write(path, data)
        if plain:
            initial_secrets_path().write_text(
                "ASTRAHEALTH AI - initial secrets (shown once). Note them down, then DELETE this file.\n"
                f"Medical officer PIN: {plain['medical_officer_pin']}\n"
                f"Admin PIN:           {plain['admin_pin']}\n"
                f"Device token:        {plain['device_token']}\n", encoding="utf-8")
        _cache = data
        return _cache


def save_credentials(data: dict) -> None:
    global _cache
    with _lock:
        _write(credentials_path(), data)
        _cache = data


def reset_cache() -> None:
    global _cache
    with _lock:
        _cache = None
    _failures.clear()


def secret_key(name: str) -> bytes:
    if name == "data":
        return _unwrap(load_credentials()["data_key"])
    return _unwrap(load_credentials()["secret_keys"][name])


def data_key() -> bytes:
    return secret_key("data")


def key_protection() -> str:
    return "Windows DPAPI (user-bound)" if "dpapi" in load_credentials()["data_key"] else "file permissions only"


# ---------------------------------------------------------------- PIN checks with a short cool-down
def _verify(entry: dict, supplied: str) -> bool:
    digest = hashlib.scrypt(supplied.encode(), salt=bytes.fromhex(entry["salt"]), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(digest.hex(), entry["hash"])


def lock_status(kind: str) -> float:
    state = _failures.get(kind)
    return max(0.0, state["until"] - time.time()) if state else 0.0


def security_events() -> dict:
    return {k: {"failures": v["count"], "cooldown_s": round(lock_status(k))} for k, v in _failures.items()}


def check_pin(kind: str, supplied: str | None) -> bool:
    if not supplied:
        return False  # no PIN offered: not a guessing attempt
    remaining = lock_status(kind)
    if remaining > 0:
        raise HTTPException(429, f"Too many wrong PINs. Try again in {int(remaining) + 1} s.")
    entry = load_credentials()["pins"].get(kind)
    ok = entry is not None and _verify(entry, str(supplied))
    state = _failures.setdefault(kind, {"count": 0, "until": 0.0})
    if ok:
        state.update(count=0, until=0.0)
        return True
    state["count"] += 1
    _audit_failure(kind, state["count"])
    if state["count"] % MAX_FAILURES == 0:
        state["until"] = time.time() + COOLDOWN_S  # fixed: bounded impact of malicious failures
    return False


def _audit_failure(kind: str, count: int) -> None:
    try:
        from app.db.database import get_db
        from app.services.repository import audit
        audit(get_db(), "security.pin_failed", kind, actor_role="unknown", consecutive_failures=count)
    except Exception:  # auditing must never break authentication
        pass


def require_admin(x_admin_pin: str | None = Header(default=None)) -> None:
    if not check_pin("admin_pin", x_admin_pin):
        raise HTTPException(403, "Admin PIN required for this action.")


def require_medical_officer_pin(pin: str | None) -> None:
    if not check_pin("medical_officer_pin", pin):
        raise HTTPException(403, "Medical officer PIN required.")


def require_device_token(x_device_token: str | None = Header(default=None)) -> None:
    entry = load_credentials()["device_token"]
    if not x_device_token or not _verify(entry, x_device_token):
        raise HTTPException(401, "Valid X-Device-Token header required to push device records.")


# ---------------------------------------------------------------- field encryption at rest
_PREFIX = "enc:v1:"


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(data_key()))


def encrypt_text(text: str | None) -> str | None:
    if not text:
        return text
    return _PREFIX + _fernet().encrypt(text.encode()).decode()


def decrypt_text(value: str | None) -> str | None:
    if not value or not value.startswith(_PREFIX):
        return value
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except (InvalidToken, RuntimeError):
        return "[encrypted — not readable on this account]"


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    return _fernet().decrypt(data)
