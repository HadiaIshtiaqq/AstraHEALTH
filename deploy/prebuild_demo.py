"""Build-time step for the hosted demo image: seed the synthetic demo database once.

Seeding takes ~20 s on a laptop but minutes on a small cloud instance, so it is done while the image is built.
At runtime the app only moves the demo timeline forward. PINs are supplied by the host's secret settings
(ADMIN_PIN, MEDICAL_OFFICER_PIN); the random build-time ones are discarded.
Run from the backend directory.
"""
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402

with TestClient(app) as client:
    profiles = client.get("/api/v1/profiles").json()["profiles"]
    assert len(profiles) >= 3, profiles
    print("seeded profiles:", [p["profile_id"] for p in profiles])

data_dir = settings.database_path.parent
(data_dir / "INITIAL_SECRETS.txt").unlink(missing_ok=True)  # never ship plain-text PINs in an image
shutil.rmtree(data_dir / "backups", ignore_errors=True)
with closing(sqlite3.connect(settings.database_path)) as conn:
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
print("demo database ready:", settings.database_path)
