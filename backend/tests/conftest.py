import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["LOCAL_LLM_ENABLED"] = "false"  # tests never depend on a model runtime
os.environ["MEDICAL_OFFICER_PIN"] = "111111"
os.environ["ADMIN_PIN"] = "222222"
os.environ["DEVICE_TOKEN"] = "test-device-token"
os.environ["DEMO_CLOCK_SHIFT"] = "false"
ADMIN = {"X-Admin-PIN": "222222"}


@pytest.fixture(scope="session")
def tmp_db_path(tmp_path_factory):
    return tmp_path_factory.mktemp("db") / "test.db"


@pytest.fixture(scope="session")
def client(tmp_db_path):
    from app.core.config import settings
    from app.db.database import Database, set_db

    settings.database_path = tmp_db_path
    settings.local_llm_enabled = False
    set_db(Database(tmp_db_path))
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(client):
    from app.db.database import get_db

    return get_db()


def now_iso():
    from app.db.database import iso, utcnow

    return iso(utcnow())
