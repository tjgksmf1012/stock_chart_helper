from sqlalchemy import String, Float, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import enum
from ..core.database import Base


class MarketRegime(str, enum.Enum):
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    EVENT = "event"


class RegimeLabel(Base):
    __tablename__ = "regime_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    index_code: Mapped[str] = mapped_column(String(20), nullable=False)  # 코스피: 0001
    regime: Mapped[MarketRegime] = mapped_column(SAEnum(MarketRegime), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
