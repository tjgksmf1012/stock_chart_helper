from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Stock Chart Helper"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://sch_user:sch_pass@localhost:5432/stock_chart_helper"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"

    # KIS API (optional, for real-time data)
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""
    kis_base_url: str = "https://openapi.koreainvestment.com:9443"

    # Cache TTL (seconds)
    daily_bars_ttl: int = 3600
    intraday_bars_ttl: int = 300
    pattern_cache_ttl: int = 300
    dashboard_cache_ttl: int = 30
    intraday_storage_path: str = "data/intraday_cache.sqlite3"
    intraday_store_retention_days: int = 45
    intraday_seed_limit: int = 40
    intraday_seed_multiplier: int = 4

    # Universe filters
    min_market_cap_billion: float = 500.0   # 5,000억 원
    min_avg_volume_billion: float = 3.0     # 30억 원 (20일 평균 거래대금)

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
