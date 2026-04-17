from fastapi import APIRouter
from ..schemas import PatternLibraryEntry

router = APIRouter(prefix="/patterns", tags=["patterns"])

# Static pattern library — structure based on plan §5.3
PATTERN_LIBRARY: list[PatternLibraryEntry] = [
    PatternLibraryEntry(
        pattern_type="double_bottom",
        name_kr="이중바닥 (W패턴)",
        grade="A",
        direction="bullish",
        description="가격이 비슷한 두 저점을 형성한 후 목선(neckline)을 돌파하면 상승 전환을 신호한다.",
        structure_conditions=[
            "두 저점의 가격이 ±5% 이내로 유사해야 한다",
            "두 저점 사이에 뚜렷한 반등 고점(목선)이 존재해야 한다",
            "두 번째 저점은 첫 번째 저점보다 5% 이상 낮으면 안 된다",
            "패턴 형성 기간은 최소 10봉 이상 권장",
        ],
        volume_conditions=[
            "첫 번째 저점 형성 시 거래량 증가",
            "반등 구간에서 거래량 감소 (압축)",
            "목선 돌파 시 거래량 급증이 이상적",
        ],
        confirmation_conditions=[
            "종가 기준 목선 상단 돌파 확인 (close confirmed)",
            "미완료 봉 기준 확인은 잠정(Provisional) 상태로만 표시",
        ],
        invalidation_conditions=[
            "두 번째 저점 하방 1% 이상 이탈",
            "목선 돌파 후 재하락하여 목선 아래 종가 마감",
        ],
        cautions=[
            "하락추세 중간의 반등 저점을 이중바닥으로 오판하지 말 것",
            "저유동성 종목에서는 노이즈로 인한 오탐이 많음",
            "두 저점 간격이 너무 짧으면 (5봉 미만) 신뢰도 낮음",
        ],
        svg_path="/patterns/double_bottom.svg",
    ),
    PatternLibraryEntry(
        pattern_type="double_top",
        name_kr="이중천장 (M패턴)",
        grade="A",
        direction="bearish",
        description="가격이 비슷한 두 고점을 형성한 후 목선을 하향 돌파하면 하락 전환을 신호한다.",
        structure_conditions=[
            "두 고점의 가격이 ±5% 이내로 유사해야 한다",
            "두 고점 사이에 뚜렷한 눌림 저점(목선)이 존재해야 한다",
            "두 번째 고점은 첫 번째 고점보다 5% 이상 높으면 안 된다",
        ],
        volume_conditions=[
            "두 번째 고점에서 첫 번째보다 거래량이 감소하는 것이 이상적",
            "목선 하향 이탈 시 거래량 증가 확인",
        ],
        confirmation_conditions=[
            "종가 기준 목선 하방 이탈 확인",
        ],
        invalidation_conditions=[
            "두 번째 고점 상방 1% 이상 돌파 종가",
        ],
        cautions=[
            "상승추세 중간의 조정을 이중천장으로 오판하지 말 것",
            "목선 이탈 후 되돌림(pull-back)은 자연스러운 현상",
        ],
        svg_path="/patterns/double_top.svg",
    ),
    PatternLibraryEntry(
        pattern_type="head_and_shoulders",
        name_kr="헤드앤숄더",
        grade="A",
        direction="bearish",
        description="좌우 숄더와 가운데 더 높은 헤드로 구성된 하락 반전 패턴. 목선 이탈로 완성.",
        structure_conditions=[
            "헤드가 두 숄더보다 반드시 높아야 한다",
            "두 숄더의 고점이 ±10% 이내로 대칭이어야 한다",
            "목선은 두 숄더 사이 저점을 연결",
        ],
        volume_conditions=[
            "헤드에서 거래량이 좌측 숄더보다 감소하는 것이 전형적",
            "우측 숄더는 헤드보다 거래량이 현저히 낮아야 한다",
        ],
        confirmation_conditions=[
            "목선 하향 이탈 종가 확인",
        ],
        invalidation_conditions=[
            "헤드 고점 상방 돌파",
            "우측 숄더가 헤드를 넘어설 경우",
        ],
        cautions=[
            "목선이 수평이 아닌 경우 판단이 어려움",
            "넓은 패턴일수록 신뢰도 높음",
        ],
        svg_path="/patterns/head_and_shoulders.svg",
    ),
    PatternLibraryEntry(
        pattern_type="inverse_head_and_shoulders",
        name_kr="역헤드앤숄더",
        grade="A",
        direction="bullish",
        description="좌우 숄더와 가운데 더 낮은 헤드로 구성된 상승 반전 패턴.",
        structure_conditions=[
            "헤드가 두 숄더보다 반드시 낮아야 한다",
            "두 숄더의 저점이 ±10% 이내로 대칭",
        ],
        volume_conditions=[
            "헤드 형성 시 거래량 급감 후 반등 시 증가가 이상적",
            "목선 돌파 시 거래량 증가 확인",
        ],
        confirmation_conditions=["목선 상방 돌파 종가 확인"],
        invalidation_conditions=["헤드 저점 하방 이탈"],
        cautions=["하락추세 말미에서만 유효한 패턴"],
        svg_path="/patterns/inverse_head_and_shoulders.svg",
    ),
    PatternLibraryEntry(
        pattern_type="ascending_triangle",
        name_kr="상승 삼각형",
        grade="A",
        direction="bullish",
        description="수평 저항선과 상승하는 지지선으로 구성. 저항 돌파 시 상승 신호.",
        structure_conditions=[
            "저항선이 수평(±2% 이내)",
            "저점이 지속적으로 높아져야 한다",
            "최소 2회 이상 저항 테스트",
        ],
        volume_conditions=["패턴 중 거래량 감소 후 돌파 시 증가"],
        confirmation_conditions=["저항선 상방 종가 돌파"],
        invalidation_conditions=["지지선 하방 이탈"],
        cautions=["상승추세에서 지속 패턴으로 더 신뢰도 높음"],
        svg_path="/patterns/ascending_triangle.svg",
    ),
    PatternLibraryEntry(
        pattern_type="descending_triangle",
        name_kr="하락 삼각형",
        grade="A",
        direction="bearish",
        description="수평 지지선과 하락하는 저항선으로 구성. 지지 이탈 시 하락 신호.",
        structure_conditions=[
            "지지선이 수평(±2% 이내)",
            "고점이 지속적으로 낮아져야 한다",
        ],
        volume_conditions=["지지 이탈 시 거래량 증가"],
        confirmation_conditions=["지지선 하방 종가 이탈"],
        invalidation_conditions=["저항선 상방 돌파"],
        cautions=["하락추세에서 지속 패턴으로 더 신뢰도 높음"],
        svg_path="/patterns/descending_triangle.svg",
    ),
    PatternLibraryEntry(
        pattern_type="symmetric_triangle",
        name_kr="대칭 삼각형",
        grade="A",
        direction="neutral",
        description="수렴하는 고점과 저점으로 구성. 추세 방향으로 돌파 시 신호 발생.",
        structure_conditions=[
            "고점이 지속 하락, 저점이 지속 상승",
            "최소 2-3회의 고저점 터치",
        ],
        volume_conditions=["수렴 중 거래량 감소, 돌파 시 증가"],
        confirmation_conditions=["어느 방향이든 종가 돌파 확인"],
        invalidation_conditions=["수렴 완성 후 돌파 실패 재진입"],
        cautions=["방향 예측이 어려움, 돌파 방향 확인 후 진입"],
        svg_path="/patterns/symmetric_triangle.svg",
    ),
    PatternLibraryEntry(
        pattern_type="rectangle",
        name_kr="박스권 (Rectangle)",
        grade="A",
        direction="neutral",
        description="수평 저항과 지지 사이 횡보. 돌파 방향으로 신호 발생.",
        structure_conditions=[
            "저항선과 지지선이 모두 수평(±3% 이내)",
            "최소 2회 이상 저항·지지 테스트",
        ],
        volume_conditions=["박스 내 거래량 감소, 돌파 시 급증"],
        confirmation_conditions=["저항 또는 지지 종가 이탈"],
        invalidation_conditions=["박스 중간에서 반대 방향 이탈"],
        cautions=["박스 크기가 작으면 (3% 미만) 노이즈 가능성"],
        svg_path="/patterns/rectangle.svg",
    ),
]


@router.get("/library")
async def get_pattern_library() -> list[PatternLibraryEntry]:
    return PATTERN_LIBRARY


@router.get("/library/{pattern_type}")
async def get_pattern(pattern_type: str) -> PatternLibraryEntry:
    for p in PATTERN_LIBRARY:
        if p.pattern_type == pattern_type:
            return p
    from fastapi import HTTPException
    raise HTTPException(404, f"Pattern '{pattern_type}' not found")
