"""확률 가중치를 데이터로 학습 — probability_engine.py의 감으로 정한 가중치 합
(0.27 * rule_up + 0.25 * empirical_up + ...)을 실제 (특징, 승패) 데이터로 학습한
로지스틱 회귀로 교체할 수 있게 한다.

실제 사용자 로컬 환경(2026-07)에서 확인된 배경: isotonic 사후보정(probability_
calibration.py)을 실제 KRX 데이터로 검증했더니, brier score가 "그냥 base_rate
고정 예측"보다 나빴다 — 그것도 확인된 다른 버그(가짜 기본 승률, 백테스트
ZeroDivisionError로 인한 표본 누락)를 다 고친 뒤에도 동일했다. 즉 지금의 손으로
정한 가중치 자체가 패턴 타입에 따라 실제로 다른 승률(18~39%)을 제대로 못
구분하고 있다는 뜻이다. 이 모듈은 그 가중치를 데이터로 다시 학습해서 검증하는
용도다.

fit_probability_model()로 새로 학습한 모델 파일이 없으면 predict_directional_
probability()는 None을 돌려주고, probability_engine.py는 기존 감으로 정한
가중치 공식으로 그대로 폴백한다 — 이 모듈이 있다고 없던 데이터가 저절로
생기지는 않는다.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..core.config import get_settings

logger = logging.getLogger(__name__)

# probability_engine.py의 p_up_raw/p_down_raw 가중합에 들어가는 9개 방향정렬
# 하위 점수와 정확히 같은 이름·순서. 학습/추론 양쪽에서 이 순서를 그대로 써야
# coef 배열의 각 자리가 어떤 특징에 대응하는지 어긋나지 않는다.
FEATURE_NAMES: tuple[str, ...] = (
    "rule",
    "empirical",
    "confirmation",
    "regime",
    "completion",
    "recency",
    "data_quality",
    "reward_risk",
    "edge",
)

# 로지스틱 회귀는 특징이 9개라 이 정도 표본 미만이면 과적합 위험이 크다.
MIN_FIT_SAMPLES = 200


def _resolve_path(configured_path: str) -> Path:
    path = Path(configured_path)
    if path.is_absolute():
        return path
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / path


def _model_path() -> Path:
    settings = get_settings()
    return _resolve_path(settings.probability_model_path)


@dataclass
class ProbabilityModel:
    feature_names: list[str]
    mean: list[float]
    scale: list[float]
    coef: list[float]
    intercept: float
    sample_size: int
    fitted_at: str

    def to_dict(self) -> dict:
        return {
            "feature_names": self.feature_names,
            "mean": self.mean,
            "scale": self.scale,
            "coef": self.coef,
            "intercept": self.intercept,
            "sample_size": self.sample_size,
            "fitted_at": self.fitted_at,
        }


_cache: dict[str, object] = {"mtime": None, "model": None}


def _load_model() -> ProbabilityModel | None:
    path = _model_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None

    if _cache["mtime"] == mtime and _cache["model"] is not None:
        return _cache["model"]  # type: ignore[return-value]

    try:
        raw = json.loads(path.read_text())
        model = ProbabilityModel(
            feature_names=list(raw["feature_names"]),
            mean=[float(v) for v in raw["mean"]],
            scale=[float(v) for v in raw["scale"]],
            coef=[float(v) for v in raw["coef"]],
            intercept=float(raw["intercept"]),
            sample_size=int(raw.get("sample_size", 0)),
            fitted_at=str(raw.get("fitted_at", "")),
        )
    except Exception as exc:
        logger.warning("failed to load probability model (%s): %s", path, exc)
        return None

    if tuple(model.feature_names) != FEATURE_NAMES:
        logger.warning(
            "probability model feature_names mismatch (file=%s, expected=%s) -- ignoring stale model",
            model.feature_names, FEATURE_NAMES,
        )
        return None

    _cache["mtime"] = mtime
    _cache["model"] = model
    return model


def predict_directional_probability(features: dict[str, float]) -> float | None:
    """9개 방향정렬 하위 점수로 "패턴 자체 방향이 이길 확률"을 예측한다.

    학습된 모델 파일이 없으면 None을 반환 -- 호출부(probability_engine.py)는
    이 경우 기존 감으로 정한 가중치 공식으로 폴백해야 한다.
    """
    model = _load_model()
    if model is None:
        return None

    z = model.intercept
    for name, coef, mean, scale in zip(model.feature_names, model.coef, model.mean, model.scale):
        x = float(features.get(name, mean))
        standardized = (x - mean) / scale if scale > 1e-12 else 0.0
        z += coef * standardized

    return 1.0 / (1.0 + math.exp(-z))


def fit_probability_model(
    rows: list[tuple[dict[str, float], bool]], min_samples: int = MIN_FIT_SAMPLES
) -> ProbabilityModel | None:
    """(9개 방향정렬 특징, 승패) 표본으로 로지스틱 회귀를 학습한다.

    표본이 min_samples 미만이면 9차원 로지스틱 회귀엔 과적합 위험이 커서
    None을 반환한다.
    """
    clean = [(f, bool(w)) for f, w in rows if f]
    if len(clean) < min_samples:
        logger.warning(
            "skipping probability model fit: %d samples < min_samples=%d (would overfit)",
            len(clean), min_samples,
        )
        return None

    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    X = np.array([[float(f.get(name, 0.5)) for name in FEATURE_NAMES] for f, _ in clean])
    y = np.array([1.0 if w else 0.0 for _, w in clean])

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    clf = LogisticRegression(max_iter=1000)
    clf.fit(X_scaled, y)

    return ProbabilityModel(
        feature_names=list(FEATURE_NAMES),
        mean=[float(v) for v in scaler.mean_],
        scale=[float(v) if v > 1e-12 else 1.0 for v in scaler.scale_],
        coef=[float(v) for v in clf.coef_[0]],
        intercept=float(clf.intercept_[0]),
        sample_size=len(clean),
        fitted_at=datetime.now(timezone.utc).isoformat(),
    )


def save_probability_model(model: ProbabilityModel) -> None:
    path = _model_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=2))
    _cache["mtime"] = None
    _cache["model"] = None
