"""InsightFlow AI – FastAPI application entry point."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import scheduler
from .config import CORS_ORIGINS, FRONTEND_DIST, SAMPLE_DIR, SCHEDULER_ENABLED, SEED_DEMO
from .database import init_db
from .routers import ai, analytics, auth, dashboards, datasets, warehouse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if SEED_DEMO:
        from .seed import seed_demo
        seed_demo()
    if SCHEDULER_ENABLED:
        scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title="InsightFlow AI",
    description="AI-powered universal data analytics, visualization and decision support platform",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, datasets.router, analytics.router, dashboards.router, warehouse.router, ai.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/demo-source/marketing", tags=["demo"])
def demo_marketing_api():
    """A mock external REST API used to demonstrate the API connector (and scheduled refresh)."""
    path = SAMPLE_DIR / "marketing.json"
    if not path.exists():
        return JSONResponse({"data": []})
    return JSONResponse(json.loads(path.read_text()))


# Serve the compiled React app (single-container deployment)
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file() and FRONTEND_DIST in candidate.resolve().parents:
            return FileResponse(candidate)
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        return FileResponse(FRONTEND_DIST / "index.html")
