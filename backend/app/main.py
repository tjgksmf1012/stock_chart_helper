import asyncio
import sys

if sys.platform == "win32":
    # Windows 콘솔의 기본 코드페이지(cp949 등)는 로그에 쓰이는 em dash(—), 화살표(→)
    # 같은 유니코드 문자를 인코딩하지 못해 UnicodeEncodeError로 앱이 죽는다.
    # stdout/stderr를 UTF-8로 강제해 어떤 콘솔 코드페이지에서도 죽지 않게 한다.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import ai, dashboard, lab, outcomes, patterns, screener, symbols, system, watchlist
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
_origin_list = ["*"] if _allow_all else [origin.strip() for origin in _origins_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origin_list,
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(symbols.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(patterns.router, prefix="/api/v1")
app.include_router(screener.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(watchlist.router, prefix="/api/v1")
app.include_router(outcomes.router, prefix="/api/v1")
app.include_router(lab.router, prefix="/api/v1")


@app.api_route("/health", methods=["GET", "HEAD"])
async def health() -> dict:
    return {"status": "ok", "version": "0.3.0"}


@app.api_route("/", methods=["GET", "HEAD"])
async def root() -> dict:
    return {"status": "ok", "service": "stock-chart-helper-api", "version": "0.3.0"}


def _start_scheduler() -> None:
    if not settings.enable_scheduler:
        logger.info("Scheduler disabled (enable_scheduler=false) — running in on-demand/local mode")
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        from .api.routes.outcomes import run_scheduled_outcome_evaluation
        from .api.routes.system import run_scheduled_intraday_warmup
        from .services.alert_service import run_watchlist_alert_check
        from .services.backtest_engine import run_backtest
        from .services.scan_history_service import prune_scan_history
        from .services.scanner import run_scan

        scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

        # 08:30 — 장 시작 전 전일 종가 기준 전체 스캔 (사이트 진입 즉시 데이터 확인 가능)
        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=8, minute=30, timezone="Asia/Seoul"),
            kwargs={
                "timeframe": "1d",
                "limit": settings.scheduled_scan_limit,
                "batch_size": settings.scheduled_scan_batch_size,
                "force_refresh": True,
            },
            id="premarket_scan",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=10, timezone="Asia/Seoul"),
            kwargs={
                "timeframe": "1d",
                "limit": settings.scheduled_scan_limit,
                "batch_size": settings.scheduled_scan_batch_size,
            },
            id="morning_scan",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=13, minute=30, timezone="Asia/Seoul"),
            kwargs={
                "timeframe": "1d",
                "limit": settings.scheduled_scan_limit,
                "batch_size": settings.scheduled_scan_batch_size,
            },
            id="midday_scan",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone="Asia/Seoul"),
            kwargs={
                "timeframe": "1d",
                "limit": settings.scheduled_scan_limit,
                "batch_size": settings.scheduled_scan_batch_size,
            },
            id="close_scan",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scheduled_outcome_evaluation,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=20, timezone="Asia/Seoul"),
            id="close_outcome_evaluation",
            replace_existing=True,
        )
        # 관심종목 가격 알림 — 장중 10분 간격 (텔레그램 미설정 시 내부에서 no-op)
        scheduler.add_job(
            run_watchlist_alert_check,
            CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/10", timezone="Asia/Seoul"),
            id="watchlist_alert_check",
            replace_existing=True,
        )
        # 주봉/월봉 자동 스캔 — 일봉 리샘플 기반이라 장 마감 후 하루 1회면 충분.
        # 일봉 close_scan(16:00)과 시간을 띄워 free tier 부하 분산.
        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=40, timezone="Asia/Seoul"),
            kwargs={
                "timeframe": "1wk",
                "limit": settings.background_scan_limit,
                "batch_size": settings.background_scan_batch_size,
                "force_refresh": True,
            },
            id="weekly_timeframe_scan",
            replace_existing=True,
        )
        scheduler.add_job(
            run_scan,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=55, timezone="Asia/Seoul"),
            kwargs={
                "timeframe": "1mo",
                "limit": settings.background_scan_limit,
                "batch_size": settings.background_scan_batch_size,
                "force_refresh": True,
            },
            id="monthly_timeframe_scan",
            replace_existing=True,
        )
        scheduler.add_job(
            run_backtest,
            CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="Asia/Seoul"),
            id="weekly_backtest",
            replace_existing=True,
        )
        scheduler.add_job(
            prune_scan_history,
            CronTrigger(day_of_week="sun", hour=3, minute=30, timezone="Asia/Seoul"),
            id="weekly_scan_history_prune",
            replace_existing=True,
        )
        if settings.enable_scheduled_intraday_warmup:
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

        keep_alive_enabled = settings.enable_platform_keepalive and bool(settings.self_healthcheck_url.strip())
        if keep_alive_enabled:
            import httpx as _httpx

            async def _keep_alive() -> None:
                try:
                    async with _httpx.AsyncClient(timeout=10) as client:
                        await client.get(settings.self_healthcheck_url.strip())
                except Exception:
                    pass

            scheduler.add_job(
                _keep_alive,
                IntervalTrigger(minutes=14),
                id="keep_alive",
                replace_existing=True,
            )

        scheduler.start()
        jobs = [
            "premarket_scan",
            "morning_scan",
            "midday_scan",
            "close_scan",
            "weekly_timeframe_scan",
            "monthly_timeframe_scan",
            "watchlist_alert_check",
            "close_outcome_evaluation",
            "weekly_backtest",
            "weekly_scan_history_prune",
        ]
        if settings.enable_scheduled_intraday_warmup:
            jobs.extend(
                [
                    "open_intraday_warmup",
                    "midday_intraday_warmup",
                    "closing_intraday_warmup",
                ]
            )
        if keep_alive_enabled:
            jobs.append("keep_alive")

        logger.info("APScheduler started", jobs=jobs, deployment_platform=settings.deployment_platform)
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

    from .api.routes.system import trigger_background_kis_prime
    from .services.backtest_engine import get_pattern_stats_map
    from .services.data_fetcher import get_data_fetcher
    from .services.scanner import run_scan

    fetcher = get_data_fetcher()

    async def _universe_then_scan() -> None:
        """universe 빌드를 먼저 완료한 뒤 스타트업 스캔 시작 (race condition 방지).

        항상 force_refresh=True로 실행:
        - 이전 캐시가 6개처럼 너무 적거나 오래된 경우에도 새 스캔을 보장
        - 배포 후 즉시 최신 데이터로 교체
        - 스캔 중에는 이전 캐시(6개)가 그대로 보이다가, 완료 후 새 결과로 교체됨
        """
        try:
            await asyncio.wait_for(fetcher.get_universe(), timeout=90.0)
            logger.info("Universe warmup complete — starting startup scan")
        except Exception as exc:
            logger.warning("Universe warmup failed (%s); scan will use fallback universe", exc)
        if settings.startup_daily_scan_enabled:
            await run_scan(
                timeframe="1d",
                limit=settings.background_scan_limit,
                batch_size=settings.background_scan_batch_size,
                force_refresh=True,   # 항상 새 스캔 (오래된 소규모 캐시 방치 방지)
                source="startup",
            )

    asyncio.create_task(_universe_then_scan())
    asyncio.create_task(get_pattern_stats_map())
    if settings.kis_app_key and settings.kis_app_secret:
        trigger_background_kis_prime(triggered_by="startup")
    logger.info(
        "Background warmup queued",
        startup_daily_scan_enabled=settings.startup_daily_scan_enabled,
    )
