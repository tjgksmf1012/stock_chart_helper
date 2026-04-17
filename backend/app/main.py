from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from .api.routes import symbols, dashboard, patterns, screener
from .core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

app = FastAPI(
    title="Stock Chart Helper API",
    description="실시간 주식 차트 분석 헬퍼 — 교과서 패턴 매핑 + 확률 엔진",
    version="0.1.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(symbols.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(patterns.router, prefix="/api/v1")
app.include_router(screener.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@app.on_event("startup")
async def on_startup():
    logger.info("Stock Chart Helper API started", debug=settings.debug)
    # DB init is optional — skip gracefully if no DB configured
    try:
        from .core.database import init_db
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning("DB init skipped (no DB configured)", error=str(e))
