"""FastAPI entry point.

Reads config/app/modules.yaml at startup and registers only the routes
whose module is enabled. Toggling a module requires only a config change
and a server restart — no code changes.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse

# Ensure local workspace package imports work without installation.
_ROOT = Path(__file__).parents[2]
_PACKAGES = _ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

# ---------------------------------------------------------------------------
# Load module toggles
# ---------------------------------------------------------------------------
_CONFIG_PATH = _ROOT / "config" / "app" / "modules.yaml"
_SECURITY_PATH = _ROOT / "config" / "app" / "security.yaml"


def _load_modules() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_modules = _load_modules()


def _load_security() -> dict:
    if not _SECURITY_PATH.exists():
        return {}
    with _SECURITY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_security = _load_security()

# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Procurement OS API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

# Expose for route handlers (upload checks etc.)
app.state.security = _security

# ---------------------------------------------------------------------------
# Security controls (config/app/security.yaml)
# ---------------------------------------------------------------------------

# CORS (mostly relevant when UI is served from another origin)
_cors = (_security or {}).get("cors", {})
_allow_origins = _cors.get("allow_origins") or []
_allow_methods = _cors.get("allow_methods") or ["GET", "POST"]
if _allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allow_origins,
        allow_methods=_allow_methods,
        allow_headers=["*"],
    )

# API key auth (disabled by default)
_auth = (_security or {}).get("auth", {})
if bool(_auth.get("enabled", False)):
    _header_name = str(_auth.get("api_key_header") or "X-API-Key")
    _expected = os.environ.get("API_KEY")
    if not _expected:
        raise RuntimeError("API_KEY environment variable is required when auth.enabled=true")

    @app.middleware("http")
    async def _api_key_guard(request: Request, call_next):
        # Allow health checks and CORS preflight.
        if request.method == "OPTIONS" or request.url.path == "/health":
            return await call_next(request)

        provided = request.headers.get(_header_name)
        if provided != _expected:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

        return await call_next(request)

# ---------------------------------------------------------------------------
# Conditionally register routers based on modules.yaml
# ---------------------------------------------------------------------------
if _modules.get("spend", {}).get("enabled", False):
    from services.api.routes.spend import router as _spend_router
    app.include_router(_spend_router, prefix="/spend", tags=["spend"])

if _modules.get("rfx", {}).get("enabled", False):
    from services.api.routes.rfx import router as _rfx_router
    app.include_router(_rfx_router, prefix="/rfx", tags=["rfx"])

if _modules.get("ocr", {}).get("enabled", False):
    from services.api.routes.ocr import router as _ocr_router
    app.include_router(_ocr_router, prefix="/ocr", tags=["ocr"])

if _modules.get("ap", {}).get("enabled", False):
    from services.api.routes.ap import router as _ap_router
    app.include_router(_ap_router, prefix="/ap", tags=["ap"])

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
_STATIC = _ROOT / "services" / "api" / "static"
_STATIC.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# ---------------------------------------------------------------------------
# Health / root
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/spend/")


@app.get("/health", tags=["ops"])
def health() -> dict:
    enabled = [m for m, cfg in _modules.items() if cfg.get("enabled", False)]
    return {"status": "ok", "enabled_modules": enabled}

