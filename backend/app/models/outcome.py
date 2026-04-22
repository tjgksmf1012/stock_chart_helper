from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class SignalOutcome(Base):
    __tablename__ = "signal_outcomes"
    __table_args__ = (
        Index("ix_signal_outcomes_symbol_tf_outcome", "symbol_code", "timeframe", "outcome"),
        Index("ix_signal_outcomes_recorded_at", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    symbol_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    signal_date: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)
    intent: Mapped[str | None] = mapped_column(String(40), default="breakout_wait")
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    exit_price: Mapped[float | None] = mapped_column(Float)
    exit_date: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    p_up_at_signal: Mapped[float | None] = mapped_column(Float)
    composite_score_at_signal: Mapped[float | None] = mapped_column(Float)
    textbook_similarity_at_signal: Mapped[float | None] = mapped_column(Float)
    trade_readiness_at_signal: Mapped[float | None] = mapped_column(Float)
    evaluation_basis: Mapped[str | None] = mapped_column(String(40))
    observed_high: Mapped[float | None] = mapped_column(Float)
    observed_low: Mapped[float | None] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
