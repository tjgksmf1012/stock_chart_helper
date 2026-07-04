from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Stock Chart Helper"
    debug: bool = False
    deployment_platform: str = "local"

    database_url: str = "postgresql+asyncpg://sch_user:sch_pass@localhost:5432/stock_chart_helper"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    self_healthcheck_url: str = ""
    enable_platform_keepalive: bool = False
    # 상시 서버 배포(Render 등)에서만 쓰는 자동 스캔/관심종목 알림/주간 정비 잡을 켤지.
    # 로컬 데스크톱 모드는 사용자가 켤 때만 동작하므로 백그라운드 스케줄이 의미가
    # 없다 — .env.local.example은 이 값을 false로 둔다.
    enable_scheduler: bool = True

    # OpenAI API (optional, for LLM-written recommendation commentary)
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_timeout_seconds: int = 45
    openai_max_output_tokens: int = 3000
    openai_enable_recommendations: bool = True
    openai_overlay_item_limit: int = 2
    openai_overlay_cache_ttl_seconds: int = 1800
    openai_overlay_refresh_after_seconds: int = 600

    # Scan workload controls.
    # ⚠️ 여기 기본값이 실제 Render 동작에 직접 영향. 환경변수 미설정 시에도 충분히 스캔되도록 높게 유지.
    # 한도를 올리면 로테이션 커서(scanner._rotate_scan_slice)가 한 사이클에 더 많은
    # 종목을 커버해 전체 유니버스를 도는 주기가 짧아진다 — SCAN_MAX_DURATION_SECONDS
    # 예산 안에서 배치 크기(5)로 처리 가능한 수준까지만 올렸다.
    startup_daily_scan_enabled: bool = True       # 서버 재시작 시 항상 스캔
    background_scan_limit: int = 300              # 시작 스캔 최대 종목 수 (환경변수 BACKGROUND_SCAN_LIMIT)
    background_scan_batch_size: int = 5           # 시작 스캔 배치 크기
    manual_scan_limit: int = 150                  # 수동 스캔 최대 종목 수
    manual_scan_batch_size: int = 5
    scheduled_scan_limit: int = 700               # 예약 스캔 최대 종목 수
    scheduled_scan_batch_size: int = 5
    scan_max_duration_seconds: int = 600          # 시작/수동 스캔 최대 시간 (10분)
    scheduled_scan_max_duration_seconds: int = 1200  # 예약 스캔 최대 시간 (20분)
    scan_symbol_timeout_seconds: int = 15         # 종목당 타임아웃
    fdr_daily_timeout_seconds: int = 10
    market_cap_timeout_seconds: int = 15
    enable_scheduled_intraday_warmup: bool = False

    # KIS API (optional, for real-time data)
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""
    kis_env: str = "auto"
    kis_base_url: str = "https://openapi.koreainvestment.com:9443"
    kis_mock_base_url: str = "https://openapivts.koreainvestment.com:29443"
    kis_token_cache_path: str = "data/kis_token_cache.json"
    kis_max_concurrent_requests: int = 2
    kis_request_spacing_ms: int = 350

    # Toss Securities Open API (optional, alternative real-time source alongside KIS)
    toss_client_id: str = ""
    toss_client_secret: str = ""
    toss_base_url: str = "https://openapi.tossinvest.com"
    toss_token_cache_path: str = "data/toss_token_cache.json"
    toss_max_concurrent_requests: int = 3
    toss_request_spacing_ms: int = 150
    toss_failure_cooldown_seconds: int = 900
    # 실시간 분봉/현재가 소스 우선순위 (콤마 구분). 설정되지 않았거나 미구성된
    # provider는 건너뛴다. 예: "kis,toss"로 바꾸면 KIS를 우선 시도.
    live_intraday_provider_order: str = "toss,kis"

    # Cache TTL (seconds)
    daily_bars_ttl: int = 3600
    intraday_bars_ttl: int = 300
    pattern_cache_ttl: int = 14400        # 4시간 (분석 결과 캐시 — 변경 전 5분으로 너무 짧았음)
    scan_results_ttl: int = 43200         # 12시간 (스캔 결과 캐시 — 다음 장까지 유지)
    dashboard_cache_ttl: int = 30         # 대시보드 폴링 간격 (변경 금지)
    intraday_storage_path: str = "data/intraday_cache.sqlite3"
    # 규칙 기반 확률(probability_engine.py)을 실제 승률에 맞춰 사후 보정하는
    # isotonic regression 매핑 파일. scripts/fit_probability_calibration.py로
    # 생성 — 파일이 없으면 보정 없이(항등 함수) 그대로 동작한다.
    probability_calibration_path: str = "data/probability_calibration.json"
    # p_up/p_down을 섞는 9개 하위 점수의 가중치를 감 대신 실제 데이터(로지스틱
    # 회귀)로 학습한 모델 파일. scripts/fit_probability_model.py로 생성 — 파일이
    # 없으면 probability_engine.py의 기존 손으로 정한 가중치 공식 그대로 동작한다.
    probability_model_path: str = "data/probability_model.json"
    intraday_store_retention_days: int = 45
    intraday_recent_store_reuse_minutes: int = 2
    intraday_seed_limit: int = 40
    intraday_seed_multiplier: int = 4
    intraday_live_candidate_limit: int = 12
    kis_failure_cooldown_seconds: int = 900
    yahoo_failure_cooldown_seconds: int = 600

    # Telegram 알림 — 관심종목이 돌파선/손절/익절에 도달하면 발송.
    # 토큰·chat_id는 Render 환경변수로 설정 (둘 다 있어야 활성화)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Universe filters
    # 500억/30억이던 하한을 완화 — 기존 값은 코스닥 중소형주 상당수를 스캔
    # 유니버스에서 통째로 제외해 분석 대상 종목 수를 필요 이상으로 줄였다.
    min_market_cap_billion: float = 300.0   # 3,000억 원
    min_avg_volume_billion: float = 1.5     # 15억 원 (20일 평균 거래대금)

    # CORS — comma-separated list of allowed origins; "*" to allow all
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    # 텔레그램 관심종목 알림 메시지에 넣는 차트 링크의 기준 주소. 상시 서버로
    # 호스팅할 때만 의미가 있고(로컬 데스크톱 모드는 워치리스트 알림 자체를 안 씀),
    # 비워두면 링크 없이 종목명/코드만 보낸다.
    frontend_base_url: str = ""

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
