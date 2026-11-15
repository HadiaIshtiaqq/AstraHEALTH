"""Local database backups (SQLite online backup API). Keeps the newest few copies.

Skipped (and reported) when free disk space is low, so a backup can never fill the disk.
"""
from __future__ import annotations

import shutil
from contextlib import closing
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

KEEP = 5
MIN_FREE_MB = 300


def backup_dir() -> Path:
    return settings.database_path.parent / "backups"


def list_backups() -> list[dict]:
    d = backup_dir()
    if not d.exists():
        return []
    return [{"file": p.name, "size_kb": round(p.stat().st_size / 1024, 1)}
            for p in sorted(d.glob("astrahealth-*.db*"), reverse=True)]


def make_backup(reason: str = "manual") -> dict:
    src = settings.database_path
    if not src.exists():
        return {"ok": False, "reason": "no database yet"}
    free_mb = shutil.disk_usage(src.parent).free / 1024 / 1024
    need_mb = src.stat().st_size / 1024 / 1024 + MIN_FREE_MB
    if free_mb < need_mb:
        return {"ok": False, "reason": f"skipped: only {free_mb:.0f} MB free (need {need_mb:.0f} MB)"}
    d = backup_dir()
    d.mkdir(parents=True, exist_ok=True)
    from app.core.security import encrypt_bytes
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    tmp = d / f".tmp-{stamp}.db"
    # sqlite3's context manager only commits; close explicitly so Windows releases the file.
    with closing(sqlite3.connect(str(src))) as s, closing(sqlite3.connect(str(tmp))) as t:
        s.backup(t)
    target = d / f"astrahealth-{stamp}.db.enc"
    target.write_bytes(encrypt_bytes(tmp.read_bytes()))  # encrypted with the DPAPI-protected data key
    tmp.unlink(missing_ok=True)
    for old in sorted(d.glob("astrahealth-*.db*"), reverse=True)[KEEP:]:
        old.unlink(missing_ok=True)
    return {"ok": True, "file": target.name, "reason": reason, "encrypted": True}


def restore_to(backup_name: str, target: Path) -> Path:
    """Decrypt a backup to a new file (never overwrites the live database)."""
    from app.core.security import decrypt_bytes
    target.write_bytes(decrypt_bytes((backup_dir() / backup_name).read_bytes()))
    return target


def daily_backup() -> dict:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    if any(b["file"].startswith(f"astrahealth-{today}") for b in list_backups()):
        return {"ok": True, "reason": "already backed up today"}
    return make_backup("daily")
