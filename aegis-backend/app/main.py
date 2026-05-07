"""
app/main.py
───────────
FastAPI application factory.
Registers all routers, middleware, exception handlers, and startup events.
"""
import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings

settings = get_settings()
log = structlog.get_logger()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    log.info("aegis.startup", env=settings.app_env, version=settings.app_version)

    # In development: auto-create tables
    if settings.app_env == "development":
        from app.database import create_tables
        await create_tables()
        log.info("aegis.db.tables_created")

    yield

    log.info("aegis.shutdown")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Aegis GRC Platform",
        description="Intelligent GRC and audit platform for SMBs",
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware ─────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # ── Exception handlers ─────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        log.error("aegis.unhandled_exception", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    # ── Routers ────────────────────────────────────────────────────────────
    from app.api.routes.auth_route import router as auth_router
    from app.api.routes.orgs_route import router as orgs_router
    from app.api.routes.risks_route import router as risks_router
    from app.api.routes.controls_route import router as controls_router
    from app.api.routes.canvas_route import router as canvas_router
    from app.api.routes.audit_route import router as audit_router
    from app.api.routes.radar_route import router as radar_router
    from app.api.routes.pulse_route import router as pulse_router
    from app.api.routes.copilot_route import router as copilot_router
    from app.api.routes.dashboard_route import router as dashboard_router
    from app.api.routes.time_machine_route import router as time_machine_router
    from app.api.routes.regulatory_route import router as regulatory_router
    from app.api.routes.audit_report_route import router as audit_report_router
    from app.api.routes.audit_copilot_route import router as audit_copilot_router
    from app.realtime.websocket import ws_router

    API_PREFIX = "/api/v1"

    app.include_router(auth_router,         prefix=API_PREFIX)
    app.include_router(orgs_router,         prefix=API_PREFIX)
    app.include_router(risks_router,        prefix=API_PREFIX)
    app.include_router(controls_router,     prefix=API_PREFIX)
    app.include_router(canvas_router,       prefix=API_PREFIX)
    app.include_router(audit_router,        prefix=API_PREFIX)
    app.include_router(radar_router,        prefix=API_PREFIX)
    app.include_router(pulse_router,        prefix=API_PREFIX)
    app.include_router(copilot_router,      prefix=API_PREFIX)
    app.include_router(dashboard_router,    prefix=API_PREFIX)
    app.include_router(time_machine_router,  prefix=API_PREFIX)
    app.include_router(regulatory_router,    prefix=API_PREFIX)
    app.include_router(audit_report_router,  prefix=API_PREFIX)
    app.include_router(audit_copilot_router, prefix=API_PREFIX)
    app.include_router(ws_router)  # WebSocket — no prefix

    # ── Health check ───────────────────────────────────────────────────────
    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok", "version": settings.app_version, "env": settings.app_env}

    @app.get("/", tags=["meta"])
    async def root():
        return {"name": "Aegis GRC Platform", "docs": "/docs"}

    return app


app = create_app()
