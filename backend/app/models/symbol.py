from sqlalchemy import String, Float, Boolean, BigInteger, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from ..core.database import Base


class Market(str, enum.Enum):
    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"


class Symbol(Base):
    __tablename__ = "symbols"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    market: Mapped[Market] = mapped_column(SAEnum(Market), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(100))

    market_cap: Mapped[float | None] = mapped_column(Float)           # 억 원
    avg_volume_20d: Mapped[float | None] = mapped_column(Float)       # 억 원
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_management: Mapped[bool] = mapped_column(Boolean, default=False)  # 관리종목
    is_halted: Mapped[bool] = mapped_column(Boolean, default=False)      # 거래정지
    is_spac: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    daily_bars: Mapped[list["DailyBar"]] = relationship(back_populates="symbol", lazy="noload")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="symbol", lazy="noload")

    @property
    def in_universe(self) -> bool:
        if not self.is_active or self.is_management or self.is_halted or self.is_spac:
            return False
        if self.market_cap is not None and self.market_cap < 500:
            return False
        if self.avg_volume_20d is not None and self.avg_volume_20d < 3:
            return False
        return True
