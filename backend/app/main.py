import asyncio

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import dashboard, patterns, screener, symbols
from .core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

app = FastAPI(
    title="Stock Chart Helper API",
    description="국내 주식 차트 패턴 분석과 확률 대시보드를 제공하는 API",
    version="0.2.0",
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
    return {"status": "ok", "version": "0.2.0"}


def _start_scheduler() -> None:
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        from .services.scanner import run_scan
        from .services.backtest_engine import run_backtest

        scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=10, timezone="Asia/Seoul"),
            id="morning_scan",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=13, minute=30, timezone="Asia/Seoul"),
            id="midday_scan",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone="Asia/Seoul"),
            id="close_scan",
            replace_existing=True,
        )

        # Weekly backtest: Sunday 02:00 KST
        scheduler.add_job(
            run_backtest,
            CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="Asia/Seoul"),
            id="weekly_backtest",
            replace_existing=True,
        )

        scheduler.start()
        logger.info("APScheduler started", jobs=["morning_scan", "midday_scan", "close_scan", "weekly_backtest"])
    except ImportError:
        logger.warning("APScheduler not installed; scheduled scans are disabled")
    except Exception as exc:
        logger.warning("APScheduler failed to start", error=str(exc))


@app.on_event("startup")
async def on_startup():
    logger.info("Stock Chart Helper API started", debug=settings.debug)

    try:
        from .core.database import init_db

        await init_db()
        logger.info("Database initialized")
    except Exception as exc:
        logger.warning("DB init skipped", error=str(exc))

    _start_scheduler()

    from .services.scanner import get_scan_results
    from .services.backtest_engine import get_pattern_stats_map

    asyncio.create_task(get_scan_results())
    asyncio.create_task(get_pattern_stats_map())   # warm backtest cache
    logger.info("Background scan + backtest tasks queued")
