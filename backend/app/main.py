"""ASTRAHEALTH AI backend entry point (FastAPI modular monolith)."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.routes import router
from app.core import netguard
from app.core.config import APP_VERSION, REPO_DIR, settings
from app.db.database import get_db
from app.rag.index import knowledge_index
from app.safety.rules import get_ruleset

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("astrahealth")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.allow_external_network:
        netguard.install()
    db = get_db()
    db.init()
    get_ruleset()
    status = knowledge_index.build(db)
    log.info("Knowledge index: %s", status)
    from app.core.security import credentials_path, load_credentials
    from app.orchestration.orchestrator import recover_interrupted_explanations

    load_credentials()
    log.info("Medical officer and admin PINs are stored in %s", credentials_path())
    from app.services.backup import daily_backup

    log.info("Backup: %s", daily_backup())
    recovered = recover_interrupted_explanations(db)
    if recovered:
        log.info("Marked %d interrupted explanation(s) as unavailable", recovered)
    if settings.enable_synthetic_data:
        from app.seed.synthetic import seed_all, shift_demo_clock

        if seed_all(db):
            log.info("Synthetic demo data seeded")
        elif settings.demo_clock_shift:
            shifted = shift_demo_clock(db)
            if shifted:
                log.info("Synthetic demo timeline moved forward %d day(s) so it ends yesterday", shifted)
    stop = threading.Event()
    if settings.enable_synthetic_data and settings.demo_clock_shift:
        def keep_demo_current() -> None:  # a demo left running overnight stays current
            from app.seed.synthetic import shift_demo_clock
            while not stop.wait(3600):
                try:
                    shift_demo_clock(db)
                except Exception:
                    log.exception("Demo clock maintenance failed")
        threading.Thread(target=keep_demo_current, daemon=True, name="demo-clock").start()
    if settings.local_llm_enabled:
        from app.intelligence.local_llm import should_keep_loaded, warm_up
        if settings.local_llm_warmup in ("1", "true", "yes", "on") or (settings.local_llm_warmup == "auto" and should_keep_loaded()):
            threading.Thread(target=warm_up, daemon=True, name="llm-warmup").start()
        else:
            log.info("LLM warm-up skipped: not enough free memory; analysis keeps priority")
    yield
    stop.set()


app = FastAPI(title="ASTRAHEALTH AI", version=APP_VERSION, lifespan=lifespan,
              description="Offline-first astronaut health monitoring prototype. Not a medical device.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def correlation(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    # The browser may only talk to this local server: no external scripts, fonts, images or API calls.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; font-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    if request.url.path.startswith("/api/"):
        log.info("%s %s %s %.1fms cid=%s", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - started) * 1000, cid)
    return response


app.include_router(router)

# Serve the built frontend (frontend/dist) when present, so the demo runs from one local process.
_dist = REPO_DIR / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(404, "Not found")
        target = _dist / path
        if path and target.is_file() and Path(target).resolve().is_relative_to(_dist.resolve()):
            return FileResponse(target)
        return FileResponse(_dist / "index.html")
