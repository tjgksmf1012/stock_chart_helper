from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class ScanRun(Base):
    __tablename__ = "scan_runs"
    __table_args__ = (
        Index("ix_scan_runs_timeframe_finished_at", "timeframe", "finished_at"),
        Index("ix_scan_runs_reference_date", "reference_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    timeframe_label: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready")
    candidate_source: Mapped[str | None] = mapped_column(String(40))
    reference_date: Mapped[str | None] = mapped_column(String(20), index=True)
    reference_reason: Mapped[str | None] = mapped_column(String(40))
    universe_size: Mapped[int | None] = mapped_column(Integer)
    candidate_count: Mapped[int | None] = mapped_column(Integer)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)

    candidates: Mapped[list["ScanCandidateSnapshot"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class ScanCandidateSnapshot(Base):
    __tablename__ = "scan_candidate_snapshots"
    __table_args__ = (
        Index("ix_scan_candidates_run_rank", "run_id", "rank"),
        Index("ix_scan_candidates_symbol_timeframe", "symbol_code", "timeframe"),
        Index("ix_scan_candidates_signal_date", "signal_date"),
        Index("ix_scan_candidates_pattern_state", "pattern_type", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False, index=True)

    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    symbol_name: Mapped[str] = mapped_column(String(100), nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    timeframe_label: Mapped[str] = mapped_column(String(20), nullable=False)
    signal_date: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    signal_price: Mapped[float | None] = mapped_column(Float)

    pattern_type: Mapped[str | None] = mapped_column(String(50), index=True)
    state: Mapped[str | None] = mapped_column(String(30), index=True)
    action_plan: Mapped[str | None] = mapped_column(String(40))
    action_plan_label: Mapped[str | None] = mapped_column(String(40))
    setup_stage: Mapped[str | None] = mapped_column(String(40))
    no_signal_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    p_up: Mapped[float] = mapped_column(Float, default=0.0)
    p_down: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    entry_score: Mapped[float] = mapped_column(Float, default=0.0)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    trade_readiness_score: Mapped[float] = mapped_column(Float, default=0.0)
    entry_window_score: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0)
    reentry_score: Mapped[float] = mapped_column(Float, default=0.0)
    historical_edge_score: Mapped[float] = mapped_column(Float, default=0.0)
    data_quality: Mapped[float] = mapped_column(Float, default=0.0)
    sample_reliability: Mapped[float] = mapped_column(Float, default=0.0)
    reward_risk_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    target_distance_pct: Mapped[float] = mapped_column(Float, default=0.0)
    stop_distance_pct: Mapped[float] = mapped_column(Float, default=0.0)

    target_level: Mapped[float | None] = mapped_column(Float)
    invalidation_level: Mapped[float | None] = mapped_column(Float)
    trigger_level: Mapped[float | None] = mapped_column(Float)

    fetch_status: Mapped[str | None] = mapped_column(String(40))
    candidate_source: Mapped[str | None] = mapped_column(String(40))
    reason_summary: Mapped[str | None] = mapped_column(Text)

    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    run: Mapped[ScanRun] = relationship(back_populates="candidates", lazy="noload")
