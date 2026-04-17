from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, Enum as SAEnum, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..core.database import Base
from .pattern import Timeframe


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_symbol_tf_updated", "symbol_id", "timeframe", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False, index=True)
    timeframe: Mapped[Timeframe] = mapped_column(SAEnum(Timeframe), nullable=False)

    # Probabilities
    p_up_3d: Mapped[float | None] = mapped_column(Float)
    p_up_5d: Mapped[float | None] = mapped_column(Float)
    p_up_10d: Mapped[float | None] = mapped_column(Float)
    p_down_3d: Mapped[float | None] = mapped_column(Float)
    p_down_5d: Mapped[float | None] = mapped_column(Float)
    p_down_10d: Mapped[float | None] = mapped_column(Float)

    # Composite scores
    textbook_similarity: Mapped[float | None] = mapped_column(Float)
    pattern_confirmation_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    entry_score: Mapped[float | None] = mapped_column(Float)

    # Meta
    no_signal_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    no_signal_reason: Mapped[str | None] = mapped_column(String(200))
    reason_summary: Mapped[str | None] = mapped_column(Text)
    sample_size: Mapped[int | None] = mapped_column()
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    symbol: Mapped["Symbol"] = relationship(back_populates="predictions", lazy="noload")


class RecommendationSnapshot(Base):
    __tablename__ = "recommendation_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # long_high_prob, short_high_prob, etc.
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    rank: Mapped[int] = mapped_column(nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_json: Mapped[str | None] = mapped_column(Text)
