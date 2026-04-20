import asyncio

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import dashboard, outcomes, patterns, screener, symbols, system, watchlist
from .core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

app = FastAPI(
    title="Stock Chart Helper API",
    description="국내 주식 차트 패턴 분석과 확률형 대시보드를 제공하는 API",
    version="0.3.0",
    docs_url="/docs",
)

_origins_raw = settings.allowed_origins.strip()
_allow_all = _origins_raw == "*"
_origin_list = ["*"] if _allow_all else [o.strip() for o in _origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origin_list,
    allow_credentials=not _allow_all,  # credentials + wildcard is invalid per CORS spec
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(symbols.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(patterns.router, prefix="/api/v1")
app.include_router(screener.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(watchlist.router, prefix="/api/v1")
app.include_router(outcomes.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.3.0"}


def _start_scheduler() -> None:
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        from .api.routes.system import run_scheduled_intraday_warmup
        from .services.backtest_engine import run_backtest
        from .services.scanner import run_scan

        scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=10, timezone="Asia/Seoul"),
            kwargs={"timeframe": "1d"},
            id="morning_scan",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=13, minute=30, timezone="Asia/Seoul"),
            kwargs={"timeframe": "1d"},
            id="midday_scan",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone="Asia/Seoul"),
            kwargs={"timeframe": "1d"},
            id="close_scan",
            replace_existing=True,
        )
        scheduler.add_job(
            run_backtest,
            CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="Asia/Seoul"),
            id="weekly_backtest",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scheduled_intraday_warmup,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=20, timezone="Asia/Seoul"),
            kwargs={"plan_id": "open_candidate_cache"},
            id="open_intraday_warmup",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scheduled_intraday_warmup,
            CronTrigger(day_of_week="mon-fri", hour=12, minute=40, timezone="Asia/Seoul"),
            kwargs={"plan_id": "midday_candidate_cache"},
            id="midday_intraday_warmup",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scheduled_intraday_warmup,
            CronTrigger(day_of_week="mon-fri", hour=14, minute=50, timezone="Asia/Seoul"),
            kwargs={"plan_id": "closing_candidate_cache"},
            id="closing_intraday_warmup",
            replace_existing=True,
        )

        # Keep-alive: self-ping every 14 min so Render free tier doesn't sleep
        import httpx as _httpx

        async def _keep_alive() -> None:
            try:
                async with _httpx.AsyncClient(timeout=10) as _c:
                    await _c.get("https://stock-chart-helper-api.onrender.com/health")
            except Exception:
                pass  # silently ignore; not critical

        from apscheduler.triggers.interval import IntervalTrigger

        scheduler.add_job(
            _keep_alive,
            IntervalTrigger(minutes=14),
            id="keep_alive",
            replace_existing=True,
        )

        scheduler.start()
        logger.info(
            "APScheduler started",
            jobs=[
                "morning_scan",
                "midday_scan",
                "close_scan",
                "weekly_backtest",
                "open_intraday_warmup",
                "midday_intraday_warmup",
                "closing_intraday_warmup",
            ],
        )
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

    from .services.backtest_engine import get_pattern_stats_map
    from .services.scanner import get_scan_results

    asyncio.create_task(get_scan_results("1d"))
    asyncio.create_task(get_pattern_stats_map())
    logger.info("Background scan and backtest warmup queued")
