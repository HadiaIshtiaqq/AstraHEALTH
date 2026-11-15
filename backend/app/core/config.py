"""Application configuration.

Values come from environment variables, optionally loaded from a `.env` file at the
repository root or in `backend/`. Nothing here performs network I/O.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

APP_VERSION = "1.0.0"


def _load_dotenv() -> None:
    for candidate in (REPO_DIR / ".env", BACKEND_DIR / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


@dataclass
class Settings:
    app_mode: str = field(default_factory=lambda: os.environ.get("APP_MODE", "offline"))
    database_path: Path = field(
        default_factory=lambda: _resolve(
            os.environ.get("DATABASE_PATH", "./data/astrahealth.db")
        )
    )
    local_llm_provider: str = field(
        default_factory=lambda: os.environ.get("LOCAL_LLM_PROVIDER", "ollama")
    )
    local_llm_base_url: str = field(
        default_factory=lambda: os.environ.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434")
    )
    local_llm_model: str = field(
        default_factory=lambda: os.environ.get("LOCAL_LLM_MODEL", "qwen2.5:3b")
    )
    local_llm_enabled: bool = field(default_factory=lambda: _bool("LOCAL_LLM_ENABLED", True))
    local_llm_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("LOCAL_LLM_TIMEOUT_S", "180"))
    )
    knowledge_dir: Path = field(
        default_factory=lambda: _resolve(os.environ.get("KNOWLEDGE_DIR", "../knowledge"))
    )
    ruleset_path: Path = field(
        default_factory=lambda: _resolve(
            os.environ.get("RULESET_PATH", "./rules/ruleset.v1.json")
        )
    )
    enable_synthetic_data: bool = field(
        default_factory=lambda: _bool("ENABLE_SYNTHETIC_DATA", True)
    )
    allow_external_network: bool = field(
        default_factory=lambda: _bool("ALLOW_EXTERNAL_NETWORK", False)
    )
    # "auto": warm up and keep the model loaded only when enough RAM is free, so it never slows analysis.
    local_llm_warmup: str = field(default_factory=lambda: os.environ.get("LOCAL_LLM_WARMUP", "auto").lower())
    llm_min_free_ram_gb: float = field(default_factory=lambda: float(os.environ.get("LLM_MIN_FREE_RAM_GB", "6")))
    demo_clock_shift: bool = field(default_factory=lambda: _bool("DEMO_CLOCK_SHIFT", True))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))
    min_baseline_points: int = field(
        default_factory=lambda: int(os.environ.get("MIN_BASELINE_POINTS", "7"))
    )
    min_anomaly_days: int = field(
        default_factory=lambda: int(os.environ.get("MIN_ANOMALY_DAYS", "14"))
    )
    agent_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("AGENT_TIMEOUT_S", "10"))
    )
    cors_origins: list[str] = field(
        default_factory=lambda: os.environ.get(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
    )


settings = Settings()
