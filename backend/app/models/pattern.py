from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, Enum as SAEnum, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import enum
from ..core.database import Base


class PatternState(str, enum.Enum):
    FORMING = "forming"
    ARMED = "armed"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"
    PLAYED_OUT = "played_out"


class PatternGrade(str, enum.Enum):
    A = "A"   # 구조 패턴 (가중치 1.00)
    B = "B"   # 구조+캔들 결합 (0.70)
    C = "C"   # 단일/소수 캔들 (0.35)


class Timeframe(str, enum.Enum):
    DAILY = "1d"
    H60 = "60m"
    M15 = "15m"


class PatternCandidate(Base):
    __tablename__ = "pattern_candidates"
    __table_args__ = (
        Index("ix_pattern_candidates_symbol_tf", "symbol_id", "timeframe"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False, index=True)
    timeframe: Mapped[Timeframe] = mapped_column(SAEnum(Timeframe), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    grade: Mapped[PatternGrade] = mapped_column(SAEnum(PatternGrade), nullable=False)
    state: Mapped[PatternState] = mapped_column(SAEnum(PatternState), nullable=False, default=PatternState.FORMING)

    # Geometry
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime)
    key_points_json: Mapped[str | None] = mapped_column(Text)  # JSON: [{date, price, type}, ...]

    # Levels
    neckline: Mapped[float | None] = mapped_column(Float)
    invalidation_level: Mapped[float | None] = mapped_column(Float)
    target_level: Mapped[float | None] = mapped_column(Float)

    is_provisional: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TextbookMatch(Base):
    __tablename__ = "textbook_matches"
    __table_args__ = (
        Index("ix_textbook_matches_symbol_tf", "symbol_id", "timeframe"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False, index=True)
    timeframe: Mapped[Timeframe] = mapped_column(SAEnum(Timeframe), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Similarity scores (0.0 ~ 1.0)
    textbook_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    geometry_fit: Mapped[float] = mapped_column(Float, nullable=False)
    swing_structure_fit: Mapped[float] = mapped_column(Float, nullable=False)
    volume_context_fit: Mapped[float] = mapped_column(Float, nullable=False)
    volatility_context_fit: Mapped[float] = mapped_column(Float, nullable=False)
    regime_fit: Mapped[float] = mapped_column(Float, nullable=False)

    state: Mapped[PatternState] = mapped_column(SAEnum(PatternState), nullable=False)
    invalidation_level: Mapped[float | None] = mapped_column(Float)
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
