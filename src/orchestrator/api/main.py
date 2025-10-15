from __future__ import annotations

from datetime import UTC, datetime
from dotenv import load_dotenv
import logging
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from .routers.projects import router as projects_router
from .routers.diag import router as diag_router
from .routers.auth import router as auth_router
from .routers.agents import router as agents_router
from .routers.chat import router as chat_router
from .routers.catalog import router as catalog_router
from .routers.accelerators import router as accelerators_router
from .routers.telemetry import router as telemetry_router
from .routers.migration import router as migration_router
from ..observability.metrics import metrics_middleware_factory

load_dotenv()  # Load environment variables from .env if present (OPENAI_API_KEY, XAI_API_KEY, etc.)

app = FastAPI(title="OPNXT Orchestrator API", version="0.1.0")

logging.basicConfig(level=logging.INFO)
logging.getLogger("opnxt.accelerator").setLevel(logging.INFO)

# Observability: request latency histogram
app.middleware("http")(metrics_middleware_factory())

# Routers
app.include_router(projects_router)
app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(diag_router)
app.include_router(chat_router)
app.include_router(catalog_router)
app.include_router(accelerators_router)
app.include_router(telemetry_router)
app.include_router(migration_router)

# Also expose the same routers under /api for alignment with architecture doc
app.include_router(projects_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(diag_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(catalog_router, prefix="/api")
app.include_router(accelerators_router, prefix="/api")
app.include_router(telemetry_router, prefix="/api")
app.include_router(migration_router, prefix="/api")

# CORS (for Next.js dev server on localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated docs and other static files
app.mount("/files", StaticFiles(directory="docs"), name="files")


@app.get("/")
def root():
    return {"name": "OPNXT Orchestrator API", "version": "0.1.0"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "components": {
            "api": "ok",
            "repo": "in-memory",
        },
    }


@app.get("/metrics")
def metrics() -> Response:
    # Expose Prometheus metrics
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# API-prefixed convenience routes (kept alongside non-prefixed routes)
@app.get("/api")
def api_root():
    return {"name": "OPNXT Orchestrator API", "version": "0.1.0"}


@app.get("/api/health")
def api_health():
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "components": {
            "api": "ok",
            "repo": "in-memory",
        },
    }


@app.get("/api/metrics")
def api_metrics() -> Response:
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
