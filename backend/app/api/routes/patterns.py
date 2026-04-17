from fastapi import APIRouter, HTTPException

from ..schemas import PatternLibraryEntry

router = APIRouter(prefix="/patterns", tags=["patterns"])

PATTERN_LIBRARY: list[PatternLibraryEntry] = [
    PatternLibraryEntry(
        pattern_type="double_bottom",
        name_kr="이중 바닥 (W)",
        grade="A",
        direction="bullish",
        description="두 개의 저점과 그 사이 반등 고점으로 형성되는 대표적인 상승 반전 패턴입니다.",
        structure_conditions=[
            "두 저점의 가격 차이가 크지 않아야 합니다.",
            "저점 사이에 의미 있는 반등 고점이 존재해야 합니다.",
            "패턴 형성 기간이 너무 짧지 않은 것이 좋습니다.",
        ],
        volume_conditions=[
            "두 번째 저점에서 매도 압력이 약해지는 흐름이 이상적입니다.",
            "목선 돌파 시 거래량이 증가하면 신뢰도가 높아집니다.",
        ],
        confirmation_conditions=[
            "종가 기준으로 목선을 상향 돌파해야 합니다.",
            "미완성 봉 돌파는 잠정 신호로만 간주합니다.",
        ],
        invalidation_conditions=[
            "두 번째 저점을 종가 기준으로 이탈하면 무효화됩니다.",
            "돌파 후 목선 아래로 다시 안착하면 재평가가 필요합니다.",
        ],
        cautions=[
            "하락 추세 중 단순 기술적 반등을 W 패턴으로 오해하지 않아야 합니다.",
            "저유동성 종목에서는 노이즈성 패턴이 자주 발생합니다.",
        ],
        svg_path="/patterns/double_bottom.svg",
    ),
    PatternLibraryEntry(
        pattern_type="double_top",
        name_kr="이중 천장 (M)",
        grade="A",
        direction="bearish",
        description="두 개의 고점과 그 사이 눌림 저점으로 형성되는 대표적인 하락 반전 패턴입니다.",
        structure_conditions=[
            "두 고점의 높이가 비슷해야 합니다.",
            "고점 사이에 뚜렷한 눌림 저점이 필요합니다.",
            "두 번째 고점이 첫 번째 고점을 크게 돌파하지 않는 것이 일반적입니다.",
        ],
        volume_conditions=[
            "두 번째 고점에서 거래량이 줄면 더 이상적입니다.",
            "목선 이탈 시 거래량 증가가 확인되면 신뢰도가 올라갑니다.",
        ],
        confirmation_conditions=[
            "종가 기준으로 목선을 하향 이탈해야 합니다.",
        ],
        invalidation_conditions=[
            "두 번째 고점을 재돌파하면 패턴 신뢰도가 크게 낮아집니다.",
        ],
        cautions=[
            "강한 상승 추세에서 나타난 짧은 조정은 M 패턴이 아닐 수 있습니다.",
            "목선 이탈 직후 되돌림은 흔하므로 종가 확인이 중요합니다.",
        ],
        svg_path="/patterns/double_top.svg",
    ),
    PatternLibraryEntry(
        pattern_type="head_and_shoulders",
        name_kr="헤드앤숄더",
        grade="A",
        direction="bearish",
        description="좌우 어깨보다 높은 머리가 있는 구조로, 상승 추세 종료 가능성을 시사합니다.",
        structure_conditions=[
            "가운데 머리가 좌우 어깨보다 높아야 합니다.",
            "좌우 어깨 높이가 어느 정도 대칭에 가까워야 합니다.",
            "두 어깨 사이의 저점을 연결한 목선이 의미 있어야 합니다.",
        ],
        volume_conditions=[
            "오른쪽 어깨로 갈수록 거래량이 둔화되면 더 좋습니다.",
            "목선 이탈 시 거래량이 늘면 하락 신호가 강화됩니다.",
        ],
        confirmation_conditions=[
            "종가 기준 목선 하향 이탈이 필요합니다.",
        ],
        invalidation_conditions=[
            "머리 고점을 재돌파하면 무효화 가능성이 커집니다.",
        ],
        cautions=[
            "비대칭이 심한 경우 억지 패턴 해석을 피해야 합니다.",
            "횡보 구간의 작은 봉 움직임은 패턴 품질이 낮습니다.",
        ],
        svg_path="/patterns/head_and_shoulders.svg",
    ),
    PatternLibraryEntry(
        pattern_type="inverse_head_and_shoulders",
        name_kr="역헤드앤숄더",
        grade="A",
        direction="bullish",
        description="좌우 어깨보다 낮은 머리가 형성되는 구조로, 하락 추세의 마무리 신호로 자주 해석됩니다.",
        structure_conditions=[
            "가운데 저점이 좌우 어깨보다 낮아야 합니다.",
            "좌우 어깨의 높이가 너무 크게 벌어지지 않아야 합니다.",
            "두 반등 고점을 잇는 목선이 뚜렷해야 합니다.",
        ],
        volume_conditions=[
            "오른쪽 어깨에서 매도 압력이 줄어드는 흐름이 바람직합니다.",
            "목선 돌파 시 거래량 증가가 동반되면 더 좋습니다.",
        ],
        confirmation_conditions=[
            "종가 기준 목선 상향 돌파가 필요합니다.",
        ],
        invalidation_conditions=[
            "머리 저점을 종가 기준으로 다시 이탈하면 무효화됩니다.",
        ],
        cautions=[
            "짧은 반등 구간을 역헤드앤숄더로 과잉 해석하지 않아야 합니다.",
        ],
        svg_path="/patterns/inverse_head_and_shoulders.svg",
    ),
    PatternLibraryEntry(
        pattern_type="ascending_triangle",
        name_kr="상승 삼각형",
        grade="A",
        direction="bullish",
        description="수평 저항선과 점점 높아지는 저점으로 구성되는 상승 지속/돌파 패턴입니다.",
        structure_conditions=[
            "상단 저항선이 비교적 수평이어야 합니다.",
            "저점이 점차 높아지며 수렴해야 합니다.",
            "저항선 테스트가 두 번 이상 있으면 더 좋습니다.",
        ],
        volume_conditions=[
            "수렴 구간에서 거래량이 점차 줄어드는 흐름이 일반적입니다.",
            "저항 돌파 시 거래량 증가가 확인되면 신뢰도가 올라갑니다.",
        ],
        confirmation_conditions=[
            "종가 기준 저항선 상향 돌파가 필요합니다.",
        ],
        invalidation_conditions=[
            "상승 추세선 하향 이탈 시 패턴이 약해집니다.",
        ],
        cautions=[
            "급등 직후 형성된 과열 구간은 실패 확률이 높을 수 있습니다.",
        ],
        svg_path="/patterns/ascending_triangle.svg",
    ),
    PatternLibraryEntry(
        pattern_type="descending_triangle",
        name_kr="하락 삼각형",
        grade="A",
        direction="bearish",
        description="수평 지지선과 점점 낮아지는 고점으로 형성되는 하락 지속/이탈 패턴입니다.",
        structure_conditions=[
            "하단 지지선이 비교적 수평이어야 합니다.",
            "고점이 점차 낮아지며 압박이 커져야 합니다.",
            "지지선 테스트가 반복될수록 중요도가 올라갑니다.",
        ],
        volume_conditions=[
            "수렴 구간에서는 거래량이 줄고, 이탈 시 증가하는 흐름이 이상적입니다.",
        ],
        confirmation_conditions=[
            "종가 기준 지지선 하향 이탈이 필요합니다.",
        ],
        invalidation_conditions=[
            "하락 추세선을 상향 돌파하면 패턴 해석을 재검토해야 합니다.",
        ],
        cautions=[
            "횡보 박스와 혼동하지 않도록 고점 하락 구조를 확인해야 합니다.",
        ],
        svg_path="/patterns/descending_triangle.svg",
    ),
    PatternLibraryEntry(
        pattern_type="symmetric_triangle",
        name_kr="대칭 삼각형",
        grade="A",
        direction="neutral",
        description="고점은 낮아지고 저점은 높아지면서 변동폭이 수렴하는 중립 패턴입니다.",
        structure_conditions=[
            "상단과 하단 추세선이 모두 수렴해야 합니다.",
            "최소 두 번 이상의 고점·저점 접촉이 필요합니다.",
        ],
        volume_conditions=[
            "수렴이 진행될수록 거래량이 줄어드는 경향이 있습니다.",
            "어느 방향이든 돌파 시 거래량 증가가 중요합니다.",
        ],
        confirmation_conditions=[
            "상단 또는 하단 추세선을 종가 기준으로 돌파/이탈해야 합니다.",
        ],
        invalidation_conditions=[
            "돌파 후 곧바로 삼각형 내부로 복귀하면 신호가 약해집니다.",
        ],
        cautions=[
            "방향성이 정해지기 전에는 중립 패턴으로 보는 것이 안전합니다.",
        ],
        svg_path="/patterns/symmetric_triangle.svg",
    ),
    PatternLibraryEntry(
        pattern_type="rectangle",
        name_kr="박스권",
        grade="A",
        direction="neutral",
        description="수평 저항과 수평 지지 사이를 왕복하는 횡보 구조입니다.",
        structure_conditions=[
            "상단 저항과 하단 지지가 비교적 평평해야 합니다.",
            "상하단 테스트가 반복될수록 박스 신뢰도가 높습니다.",
        ],
        volume_conditions=[
            "박스 내부에서는 거래량이 둔화되고, 돌파 시 확대되는 경우가 많습니다.",
        ],
        confirmation_conditions=[
            "상단 돌파 또는 하단 이탈을 종가 기준으로 확인합니다.",
        ],
        invalidation_conditions=[
            "돌파 후 박스 내부로 빠르게 복귀하면 실패 패턴일 수 있습니다.",
        ],
        cautions=[
            "너무 좁은 박스는 단순 노이즈일 수 있습니다.",
            "전체 시장 변동성이 큰 날에는 가짜 돌파가 늘어날 수 있습니다.",
        ],
        svg_path="/patterns/rectangle.svg",
    ),
]


@router.get("/library")
async def get_pattern_library() -> list[PatternLibraryEntry]:
    return PATTERN_LIBRARY


@router.get("/library/{pattern_type}")
async def get_pattern(pattern_type: str) -> PatternLibraryEntry:
    for pattern in PATTERN_LIBRARY:
        if pattern.pattern_type == pattern_type:
            return pattern
    raise HTTPException(404, f"Pattern '{pattern_type}' not found")
