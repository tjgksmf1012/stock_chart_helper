"""라이브 신호의 자동 종이매매 기록.

일반 판단 저널(signal_outcomes)과 분리한 이유: 랩 전략은 시간 청산(N일 보유)이
많아 target/stop 기반 평가와 의미가 다르고, 백테스트와 동일한 simulate_trades로
청산해야 실측 EV를 백테스트 EV와 정확히 비교(드리프트 감시)할 수 있다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class LabPaperTrade(Base):
    __tablename__ = "lab_paper_trades"
    __table_args__ = (
        # 같은 전략·종목·신호일은 한 번만 기록 (중복 방지)
        Index("ux_lab_paper_dedupe", "strategy_id", "code", "signal_date", unique=True),
        Index("ix_lab_paper_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    signal_date: Mapped[str] = mapped_column(String(20), nullable=False)  # ISO date
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float | None] = mapped_column(Float)
    max_holding_days: Mapped[int] = mapped_column(Integer, nullable=False, default=40)

    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open", index=True)  # open|closed
    entry_date: Mapped[str | None] = mapped_column(String(20))
    entry_price: Mapped[float | None] = mapped_column(Float)
    exit_date: Mapped[str | None] = mapped_column(String(20))
    exit_price: Mapped[float | None] = mapped_column(Float)
    exit_reason: Mapped[str | None] = mapped_column(String(12))  # stop|target|time|data_end
    net_return_pct: Mapped[float | None] = mapped_column(Float)

    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
