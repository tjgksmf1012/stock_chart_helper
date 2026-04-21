from pydantic_settings import BaseSettings
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

    # OpenAI API (optional, for LLM-written recommendation commentary)
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_timeout_seconds: int = 30
    openai_max_output_tokens: int = 900
    openai_enable_recommendations: bool = True
    openai_overlay_item_limit: int = 4
    openai_overlay_cache_ttl_seconds: int = 1800
    openai_overlay_refresh_after_seconds: int = 600

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

    # Cache TTL (seconds)
    daily_bars_ttl: int = 3600
    intraday_bars_ttl: int = 300
    pattern_cache_ttl: int = 300
    dashboard_cache_ttl: int = 30
    intraday_storage_path: str = "data/intraday_cache.sqlite3"
    intraday_store_retention_days: int = 45
    intraday_recent_store_reuse_minutes: int = 2
    intraday_seed_limit: int = 40
    intraday_seed_multiplier: int = 4
    intraday_live_candidate_limit: int = 12
    kis_failure_cooldown_seconds: int = 900
    yahoo_failure_cooldown_seconds: int = 600

    # Universe filters
    min_market_cap_billion: float = 500.0   # 5,000억 원
    min_avg_volume_billion: float = 3.0     # 30억 원 (20일 평균 거래대금)

    # CORS — comma-separated list of allowed origins; "*" to allow all
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
