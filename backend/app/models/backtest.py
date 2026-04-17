from sqlalchemy import String, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from ..core.database import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    pattern_type: Mapped[str | None] = mapped_column(String(50))
    timeframe: Mapped[str | None] = mapped_column(String(10))
    period_start: Mapped[datetime | None] = mapped_column(DateTime)
    period_end: Mapped[datetime | None] = mapped_column(DateTime)

    # Key metrics
    hit_rate: Mapped[float | None] = mapped_column(Float)
    expectancy: Mapped[float | None] = mapped_column(Float)
    brier_score: Mapped[float | None] = mapped_column(Float)
    max_drawdown: Mapped[float | None] = mapped_column(Float)
    sample_count: Mapped[int | None] = mapped_column()

    results_json: Mapped[str | None] = mapped_column(Text)
