from sqlalchemy import String, Float, BigInteger, Date, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date, datetime
from ..core.database import Base


class DailyBar(Base):
    __tablename__ = "daily_bars"
    __table_args__ = (
        Index("ix_daily_bars_symbol_date", "symbol_id", "date", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[float | None] = mapped_column(Float)  # 거래대금 (억 원)

    # 수정주가 여부
    is_adjusted: Mapped[bool] = mapped_column(default=True)

    symbol: Mapped["Symbol"] = relationship(back_populates="daily_bars", lazy="noload")


class IntradayBar60m(Base):
    __tablename__ = "intraday_bars_60m"
    __table_args__ = (
        Index("ix_intraday_60m_symbol_dt", "symbol_id", "datetime", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False, index=True)
    datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_regular_session: Mapped[bool] = mapped_column(default=True)


class IntradayBar15m(Base):
    __tablename__ = "intraday_bars_15m"
    __table_args__ = (
        Index("ix_intraday_15m_symbol_dt", "symbol_id", "datetime", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False, index=True)
    datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_regular_session: Mapped[bool] = mapped_column(default=True)
