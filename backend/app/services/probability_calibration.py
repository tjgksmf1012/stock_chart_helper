"""확률 재보정 — 규칙 기반 확률(p_up/p_down)이 실제 승률과 얼마나 맞는지를
과거 데이터로 학습해서 최종 표시값을 보정한다 (통계학에서 흔히 쓰는
Platt/isotonic 계열의 사후 확률 캘리브레이션 기법).

compute_probability()가 감으로 정한 가중치로 계산한 결과 자체를 바꾸는 게
아니라, 그 출력값 위에 "이 휴리스틱이 65%라고 할 때 실제로는 몇 %였나"를
사후 보정하는 층을 하나 더 얹는다.

fit_calibration_mapping()으로 새로 학습한 매핑 파일이 없으면 calibrate_
probability()는 항등 함수(입력 그대로 반환)로 동작한다 — 이 모듈이 있다고
없던 데이터가 저절로 생기지는 않는다. 실제 KRX 데이터가 있는 환경에서
scripts/fit_probability_calibration.py를 실행해야 진짜 보정값이 생긴다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..core.config import get_settings

logger = logging.getLogger(__name__)

# Isotonic regression은 표본이 적으면 노이즈에 그대로 들러붙어 과적합된다.
# 이 미만이면 학습을 거부하고 기존 매핑(또는 무보정)을 유지하는 편이 낫다.
MIN_FIT_SAMPLES = 200


def _resolve_path(configured_path: str) -> Path:
    path = Path(configured_path)
    if path.is_absolute():
        return path
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / path


def _calibration_path() -> Path:
    settings = get_settings()
    return _resolve_path(settings.probability_calibration_path)


@dataclass
class CalibrationMapping:
    x: list[float]
    y: list[float]
    sample_size: int
    fitted_at: str

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "sample_size": self.sample_size, "fitted_at": self.fitted_at}


_cache: dict[str, object] = {"mtime": None, "mapping": None}


def _load_mapping() -> CalibrationMapping | None:
    path = _calibration_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None

    if _cache["mtime"] == mtime and _cache["mapping"] is not None:
        return _cache["mapping"]  # type: ignore[return-value]

    try:
        raw = json.loads(path.read_text())
        mapping = CalibrationMapping(
            x=[float(v) for v in raw["x"]],
            y=[float(v) for v in raw["y"]],
            sample_size=int(raw.get("sample_size", 0)),
            fitted_at=str(raw.get("fitted_at", "")),
        )
    except Exception as exc:
        logger.warning("failed to load probability calibration mapping (%s): %s", path, exc)
        return None

    _cache["mtime"] = mtime
    _cache["mapping"] = mapping
    return mapping


def calibrate_probability(raw_prob: float) -> float:
    """raw_prob(휴리스틱이 낸 방향 확률)를 학습된 매핑으로 보정.

    매핑 파일이 없거나 점이 2개 미만이면 원값을 그대로 반환한다(무보정).
    """
    mapping = _load_mapping()
    if mapping is None or len(mapping.x) < 2:
        return raw_prob
    calibrated = float(np.interp(raw_prob, mapping.x, mapping.y))
    return max(0.0, min(1.0, calibrated))


def fit_calibration_mapping(
    pairs: list[tuple[float, bool]], min_samples: int = MIN_FIT_SAMPLES
) -> CalibrationMapping | None:
    """(predicted, won) 쌍으로 isotonic regression을 학습해 보정 매핑을 만든다.

    표본이 min_samples 미만이면 과적합 위험이 커서 None을 반환한다 — 호출부는
    이 경우 기존 매핑을 그대로 유지하거나 재보정 자체를 건너뛰어야 한다.
    """
    clean = [(float(p), bool(w)) for p, w in pairs if p is not None]
    if len(clean) < min_samples:
        logger.warning(
            "skipping calibration fit: %d samples < min_samples=%d (would overfit)",
            len(clean), min_samples,
        )
        return None

    from sklearn.isotonic import IsotonicRegression  # lazy — only needed when (re)fitting

    xs = np.array([p for p, _ in clean])
    ys = np.array([1.0 if w else 0.0 for _, w in clean])
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(xs, ys)

    return CalibrationMapping(
        x=[float(v) for v in iso.X_thresholds_],
        y=[float(v) for v in iso.y_thresholds_],
        sample_size=len(clean),
        fitted_at=datetime.now(timezone.utc).isoformat(),
    )


def save_calibration_mapping(mapping: CalibrationMapping) -> None:
    path = _calibration_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping.to_dict(), ensure_ascii=False, indent=2))
    _cache["mtime"] = None
    _cache["mapping"] = None
