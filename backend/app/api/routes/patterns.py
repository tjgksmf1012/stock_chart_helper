from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ..schemas import PatternLibraryEntry, PatternStatsEntry, PatternStatsResponse
from ...services.backtest_engine import get_pattern_stats_map, run_backtest
from ...services.timeframe_service import timeframe_label

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
            "두 저점 사이에 의미 있는 반등 고점이 있어야 합니다.",
            "패턴 형성 기간이 너무 짧지 않은 편이 좋습니다.",
        ],
        volume_conditions=[
            "두 번째 저점에서 매도 압력이 둔화되면 더 좋습니다.",
            "돌파선 돌파 때 거래량 증가가 동반되면 신뢰도가 높아집니다.",
        ],
        confirmation_conditions=[
            "종가 기준으로 돌파선을 상향 돌파해야 합니다.",
            "장중 돌파만으로는 확인 완료로 보기 어렵습니다.",
        ],
        invalidation_conditions=[
            "두 번째 저점을 종가 기준으로 다시 이탈하면 무효에 가깝습니다.",
            "돌파 후 돌파선 아래로 빠르게 복귀하면 재평가가 필요합니다.",
        ],
        cautions=[
            "하락 추세 중 단순 반등을 W 패턴으로 과대 해석하지 않아야 합니다.",
            "저유동성 종목에서는 노이즈성 패턴이 자주 나타납니다.",
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
            "고점 사이에 선명한 눌림 저점이 필요합니다.",
            "두 번째 고점이 첫 번째 고점을 강하게 돌파하지 않는 편이 일반적입니다.",
        ],
        volume_conditions=[
            "두 번째 고점에서 거래량이 줄면 더 이상적입니다.",
            "돌파선 이탈 시 거래량 증가가 확인되면 신뢰도가 높아집니다.",
        ],
        confirmation_conditions=[
            "종가 기준으로 돌파선을 하향 이탈해야 합니다.",
        ],
        invalidation_conditions=[
            "두 번째 고점을 재돌파하면 패턴 신뢰도가 크게 낮아집니다.",
        ],
        cautions=[
            "강한 상승 추세에서는 짧은 조정을 M 패턴으로 착각할 수 있습니다.",
            "돌파선 이탈 직후 되돌림이 흔해 종가 확인이 중요합니다.",
        ],
        svg_path="/patterns/double_top.svg",
    ),
    PatternLibraryEntry(
        pattern_type="head_and_shoulders",
        name_kr="헤드 앤 숄더",
        grade="A",
        direction="bearish",
        description="좌우 어깨보다 높은 머리가 있는 구조로 상승 추세 종료 가능성을 시사합니다.",
        structure_conditions=[
            "가운데 머리가 좌우 어깨보다 높아야 합니다.",
            "좌우 어깨 높이가 어느 정도 대칭에 가까워야 합니다.",
            "어깨 사이 저점을 연결한 돌파선이 비교적 선명해야 합니다.",
        ],
        volume_conditions=[
            "오른쪽 어깨로 갈수록 거래량이 둔화되면 더 좋습니다.",
            "돌파선 이탈 시 거래량이 늘면 하락 신호가 강화됩니다.",
        ],
        confirmation_conditions=[
            "종가 기준 돌파선 하향 이탈이 필요합니다.",
        ],
        invalidation_conditions=[
            "머리 고점을 재돌파하면 무효 가능성이 커집니다.",
        ],
        cautions=[
            "비대칭이 심한 경우 억지 패턴 해석을 피해야 합니다.",
            "횡보 구간의 작은 움직임은 패턴보다 잡음일 수 있습니다.",
        ],
        svg_path="/patterns/head_and_shoulders.svg",
    ),
    PatternLibraryEntry(
        pattern_type="inverse_head_and_shoulders",
        name_kr="역 헤드 앤 숄더",
        grade="A",
        direction="bullish",
        description="좌우 어깨보다 낮은 머리가 형성되는 구조로 하락 추세 마무리 신호로 자주 해석됩니다.",
        structure_conditions=[
            "가운데 저점이 좌우 어깨보다 더 낮아야 합니다.",
            "좌우 어깨 높이 차이가 너무 크지 않아야 합니다.",
            "각 반등 고점을 잇는 돌파선이 선명해야 합니다.",
        ],
        volume_conditions=[
            "오른쪽 어깨에서 매도 압력이 줄어드는 흐름이 바람직합니다.",
            "돌파선 돌파 때 거래량 증가가 동반되면 더 좋습니다.",
        ],
        confirmation_conditions=[
            "종가 기준 돌파선 상향 돌파가 필요합니다.",
        ],
        invalidation_conditions=[
            "머리 저점을 종가 기준으로 다시 이탈하면 무효에 가깝습니다.",
        ],
        cautions=[
            "짧은 반등을 역 헤드 앤 숄더로 과도하게 해석하지 않아야 합니다.",
        ],
        svg_path="/patterns/inverse_head_and_shoulders.svg",
    ),
    PatternLibraryEntry(
        pattern_type="ascending_triangle",
        name_kr="상승 삼각형",
        grade="A",
        direction="bullish",
        description="수평 저항선과 점점 높아지는 저점으로 구성되는 상승 지속 돌파 패턴입니다.",
        structure_conditions=[
            "상단 저항선이 비교적 수평이어야 합니다.",
            "저점이 점차 높아지며 수렴해야 합니다.",
            "저항선 테스트가 두 번 이상 있으면 더 좋습니다.",
        ],
        volume_conditions=[
            "수렴 구간에서 거래량이 점차 줄어드는 흐름이 일반적입니다.",
            "저항선 돌파 시 거래량 증가가 확인되면 신뢰도가 높아집니다.",
        ],
        confirmation_conditions=[
            "종가 기준으로 저항선 상향 돌파가 필요합니다.",
        ],
        invalidation_conditions=[
            "상승 추세선 하향 이탈 시 패턴 강도가 약해집니다.",
        ],
        cautions=[
            "급등 직후 과열 구간에서는 실패 확률이 높을 수 있습니다.",
        ],
        svg_path="/patterns/ascending_triangle.svg",
    ),
    PatternLibraryEntry(
        pattern_type="descending_triangle",
        name_kr="하락 삼각형",
        grade="A",
        direction="bearish",
        description="수평 지지선과 점점 낮아지는 고점으로 형성되는 하락 지속 이탈 패턴입니다.",
        structure_conditions=[
            "하단 지지선이 비교적 수평이어야 합니다.",
            "고점이 점차 낮아지며 압박이 커져야 합니다.",
            "지지선 테스트가 반복될수록 중요도가 올라갑니다.",
        ],
        volume_conditions=[
            "수렴 구간에서 거래량이 줄고, 이탈 때 증가하면 더 이상적입니다.",
        ],
        confirmation_conditions=[
            "종가 기준 지지선 하향 이탈이 필요합니다.",
        ],
        invalidation_conditions=[
            "상향 돌파가 나올 경우 패턴 해석이 약해집니다.",
        ],
        cautions=[
            "단순 박스권과 혼동되지 않도록 고점 하락 구조를 확인해야 합니다.",
        ],
        svg_path="/patterns/descending_triangle.svg",
    ),
    PatternLibraryEntry(
        pattern_type="symmetric_triangle",
        name_kr="대칭 삼각형",
        grade="A",
        direction="neutral",
        description="고점은 낮아지고 저점은 높아지면서 변동폭이 수렴되는 중립 패턴입니다.",
        structure_conditions=[
            "상단과 하단 추세선이 모두 수렴해야 합니다.",
            "최소 두 번 이상 고점과 저점 접촉이 필요합니다.",
        ],
        volume_conditions=[
            "수렴이 진행될수록 거래량이 줄어드는 경향이 있습니다.",
            "어느 방향이든 돌파 시 거래량 증가는 중요합니다.",
        ],
        confirmation_conditions=[
            "상단 또는 하단 추세선을 종가 기준으로 돌파하거나 이탈해야 합니다.",
        ],
        invalidation_conditions=[
            "돌파 직후 삼각형 내부로 복귀하면 신호가 약해집니다.",
        ],
        cautions=[
            "방향성이 정해지기 전까지는 중립 패턴으로 보는 편이 안전합니다.",
        ],
        svg_path="/patterns/symmetric_triangle.svg",
    ),
    PatternLibraryEntry(
        pattern_type="rectangle",
        name_kr="박스권",
        grade="A",
        direction="neutral",
        description="수평 저항과 수평 지지 사이를 반복하는 횡보 구조입니다.",
        structure_conditions=[
            "상단 저항과 하단 지지가 비교적 평평해야 합니다.",
            "상하단 테스트가 반복될수록 박스 신뢰도가 높습니다.",
        ],
        volume_conditions=[
            "박스 내부에서는 거래량이 둔화되고, 돌파 시 늘어나는 경우가 많습니다.",
        ],
        confirmation_conditions=[
            "상단 돌파 또는 하단 이탈을 종가 기준으로 확인합니다.",
        ],
        invalidation_conditions=[
            "돌파 후 박스 내부로 빠르게 복귀하면 실패 패턴일 수 있습니다.",
        ],
        cautions=[
            "너무 좁은 박스는 단순 노이즈일 수 있습니다.",
            "시장 변동성이 큰 날에는 가짜 돌파가 늘어날 수 있습니다.",
        ],
        svg_path="/patterns/rectangle.svg",
    ),
    PatternLibraryEntry(
        pattern_type="vcp",
        name_kr="VCP 변동성 수축",
        grade="A",
        direction="bullish",
        description="상승 추세 안에서 눌림 깊이와 변동 폭이 점점 줄고 거래량까지 마르다가 돌파를 준비하는 지속형 패턴입니다.",
        structure_conditions=[
            "최근 3회 이상의 눌림 깊이가 순차적으로 얕아져야 합니다.",
            "피벗 고점들은 큰 이탈 없이 비슷한 가격대에 모이는 편이 좋습니다.",
            "마지막 수축 구간의 일중 범위가 이전보다 더 타이트해야 합니다.",
            "종가가 20일선·60일선 위에 있어야 하고, 데이터가 충분하면 150일선 위(스테이지2 확인)까지 봅니다.",
        ],
        volume_conditions=[
            "수축이 진행될수록 거래량이 말라가는 흐름이 이상적입니다.",
            "피벗 돌파 시 거래량이 다시 붙으면 신뢰도가 높아집니다.",
        ],
        confirmation_conditions=[
            "피벗 고점을 종가 기준으로 돌파해야 합니다.",
            "돌파 직후 피벗 위에서 버티거나 얕은 Retest 후 재상승하면 더 좋습니다.",
            "시장 지수 대비 상대강도(RS)가 뚜렷하게 약하면 확인(confirmed/armed)으로 인정하지 않습니다.",
        ],
        invalidation_conditions=[
            "마지막 수축 저점을 종가 기준으로 이탈하면 구조가 약해집니다.",
            "돌파 후 빠르게 피벗 아래로 밀리면 가짜 돌파일 수 있습니다.",
        ],
        cautions=[
            "상승 추세 없이 횡보만 타이트한 경우는 단순 박스권일 수 있습니다.",
            "거래량이 마르지 않은 채 흔들리기만 하면 VCP보다 소음일 가능성이 큽니다.",
            "종목이 시장 지수보다 약하게 움직이고 있다면(상대강도 부진) 형태가 예뻐도 보수적으로 봐야 합니다.",
        ],
        svg_path="/patterns/vcp.svg",
    ),
    PatternLibraryEntry(
        pattern_type="momentum_breakout",
        name_kr="모멘텀 브레이크아웃",
        grade="B",
        direction="bullish",
        description="W/M/삼각형 같은 스윙 패턴과 달리 형태 완성을 기다리지 않고, 최근 저항선 근접 + 거래량 확장 + 상승 모멘텀을 직접 스캔하는 보완 트랙입니다. 고전 패턴이 confirmed될 즈음엔 이미 상당 부분 오른 뒤인 경우가 많아, 돌파 임박·직후를 더 빠르게 포착하기 위해 추가했습니다.",
        structure_conditions=[
            "최근 30봉 고가(저항선) 대비 -8% ~ +6% 범위 안에 있어야 합니다.",
            "최근 10봉 저가 대비 저항선까지 형성 높이가 30% 이내여야 합니다.",
            "최근 11봉 수익률이 양(+)이어야 합니다 — 하락 추세에서는 이 트랙으로 잡지 않습니다.",
            "종가가 자체 50일선 위에 있어야 합니다 — 장기 하락추세 중 반짝 반등은 걸러냅니다.",
        ],
        volume_conditions=[
            "당일 거래량이 최근 20일 평균 대비 1.45배 이상이면 confirmed, 1.0배 이상이면 armed로 봅니다.",
            "거래량 확장 없이 저항선 근처에서만 머무르면 forming 단계에 머뭅니다.",
        ],
        confirmation_conditions=[
            "저항선을 종가 기준 +0.5% 이상 돌파하고 거래량이 평균 1.45배 이상이어야 confirmed입니다.",
            "저항선 바로 위(5% 이내)에 더 강한 과거 고점이 남아 있으면 완전 돌파로 인정하지 않고 armed로 낮춥니다.",
            "시장 지수 대비 상대강도(RS)가 뚜렷하게 약하면 confirmed/armed로 인정하지 않습니다.",
        ],
        invalidation_conditions=[
            "최근 10봉 저가 아래로 종가 기준 이탈하면 구조가 무효화됩니다.",
        ],
        cautions=[
            "거래량 확장 없이 가격만 튄 경우 가짜 돌파일 수 있습니다.",
            "다른 스윙 패턴과 달리 대칭적인 형태 검증이 없어 상대적으로 신뢰도(grade B)가 낮게 잡혀 있습니다.",
            "아직 실거래 백테스트 표본이 적어 win_rate는 잠정치입니다.",
        ],
        svg_path=None,
    ),
    PatternLibraryEntry(
        pattern_type="cup_and_handle",
        name_kr="컵 앤 핸들",
        grade="A",
        direction="bullish",
        description="완만한 U자형 바닥(컵)을 다진 뒤 우측 상단에서 짧고 얕은 눌림(핸들)을 만들고 돌파하는 상승 지속형 패턴입니다.",
        structure_conditions=[
            "컵의 좌우 고점 높이가 비슷해야 합니다.",
            "컵 바닥은 V자보다 둥근 U자에 가까운 편이 이상적입니다.",
            "핸들 구간의 눌림 깊이는 컵 전체 깊이의 절반을 넘지 않는 편이 좋습니다.",
        ],
        volume_conditions=[
            "컵 바닥에서 거래량이 줄고, 우측 상승 구간에서 다시 늘어나면 이상적입니다.",
            "핸들 구간에서는 거래량이 잦아드는 편이 좋습니다.",
        ],
        confirmation_conditions=[
            "핸들 상단(좌측 컵 고점 부근)을 종가 기준으로 돌파해야 확인됩니다.",
            "돌파 시 거래량 증가가 동반되면 신뢰도가 높아집니다.",
        ],
        invalidation_conditions=[
            "핸들 저점을 종가 기준으로 이탈하면 구조가 무효에 가깝습니다.",
            "핸들 깊이가 컵 깊이의 절반을 크게 넘으면 신뢰도가 떨어집니다.",
        ],
        cautions=[
            "컵이 너무 뾰족(V자)하면 컵 앤 핸들보다 단순 눌림목일 수 있습니다.",
            "핸들 없이 바로 돌파하는 경우 아직 완성된 패턴으로 보기 어렵습니다.",
        ],
        svg_path=None,
    ),
    PatternLibraryEntry(
        pattern_type="rounding_bottom",
        name_kr="라운딩 바닥",
        grade="A",
        direction="bullish",
        description="장기간에 걸쳐 완만한 U자 곡선을 그리며 하락에서 상승으로 서서히 전환되는 바닥권 반전 패턴입니다.",
        structure_conditions=[
            "좌측 고점에서 바닥까지, 바닥에서 우측 고점까지 대칭적인 곡선을 그려야 합니다.",
            "컵 앤 핸들보다 형성 기간이 길고 완만한 편입니다.",
            "중간에 급격한 반등이나 급락 없이 점진적으로 방향이 바뀌어야 합니다.",
        ],
        volume_conditions=[
            "바닥 구간에서 거래량이 최소로 줄었다가, 우측 상승 구간에서 점진적으로 늘어나는 흐름이 이상적입니다.",
        ],
        confirmation_conditions=[
            "좌측 고점 부근을 종가 기준으로 돌파해야 확인됩니다.",
        ],
        invalidation_conditions=[
            "바닥권 저점을 종가 기준으로 다시 이탈하면 구조가 무효화됩니다.",
        ],
        cautions=[
            "형성 기간이 길어 확증 편향으로 아무 완만한 하락도 라운딩 바닥으로 보일 수 있어 주의가 필요합니다.",
            "우측 고점 돌파 전까지는 여전히 하락 추세의 일부일 수 있습니다.",
        ],
        svg_path=None,
    ),
    PatternLibraryEntry(
        pattern_type="rising_channel",
        name_kr="상승 채널",
        grade="A",
        direction="bullish",
        description="점점 높아지는 고점과 저점이 평행한 두 추세선 사이를 오가며 상승하는 지속형 구조입니다.",
        structure_conditions=[
            "상단 추세선과 하단 추세선이 서로 평행에 가까워야 합니다.",
            "고점·저점 각각 2회 이상 추세선에 닿아야 채널로 인정하기 좋습니다.",
        ],
        volume_conditions=[
            "채널 하단 지지 구간에서 거래량이 유지되면 신뢰도가 높아집니다.",
        ],
        confirmation_conditions=[
            "채널 하단에서 반등하며 채널 내 흐름이 이어지는지가 핵심입니다.",
            "채널 상단을 강하게 뚫고 올라가면 가속 국면, 하단을 이탈하면 추세 전환 신호로 봅니다.",
        ],
        invalidation_conditions=[
            "채널 하단을 종가 기준으로 이탈하면 상승 추세 약화 신호입니다.",
        ],
        cautions=[
            "채널 상단 근처는 이미 오른 구간이라 추격 진입 시 손익비가 나빠지기 쉽습니다.",
            "채널 폭이 너무 좁으면 사소한 변동에도 이탈 판정이 자주 발생할 수 있습니다.",
        ],
        svg_path=None,
    ),
    PatternLibraryEntry(
        pattern_type="falling_channel",
        name_kr="하락 채널",
        grade="A",
        direction="bearish",
        description="점점 낮아지는 고점과 저점이 평행한 두 추세선 사이를 오가며 하락하는 지속형 구조입니다.",
        structure_conditions=[
            "상단 추세선과 하단 추세선이 서로 평행에 가까워야 합니다.",
            "고점·저점 각각 2회 이상 추세선에 닿아야 채널로 인정하기 좋습니다.",
        ],
        volume_conditions=[
            "채널 상단 저항 구간에서 거래량이 실리면 신뢰도가 높아집니다.",
        ],
        confirmation_conditions=[
            "채널 상단에서 밀리며 채널 내 하락 흐름이 이어지는지가 핵심입니다.",
            "채널 하단을 강하게 뚫고 내려가면 가속 국면, 상단을 돌파하면 추세 전환 신호로 봅니다.",
        ],
        invalidation_conditions=[
            "채널 상단을 종가 기준으로 돌파하면 하락 추세 약화 신호입니다.",
        ],
        cautions=[
            "채널 하단 근처는 이미 내린 구간이라 추격 진입(공매도) 시 손익비가 나빠지기 쉽습니다.",
            "채널 폭이 너무 좁으면 사소한 변동에도 이탈 판정이 자주 발생할 수 있습니다.",
        ],
        svg_path=None,
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


@router.get("/stats", response_model=PatternStatsResponse)
async def get_pattern_stats() -> PatternStatsResponse:
    stats_map = await get_pattern_stats_map()
    items: list[PatternStatsEntry] = []

    for timeframe, bucket in stats_map.items():
        for pattern_type, stats in bucket.items():
            items.append(
                PatternStatsEntry(
                    pattern_type=pattern_type,
                    timeframe=timeframe,
                    timeframe_label=timeframe_label(timeframe),
                    win_rate=float(stats.get("win_rate", 0.0)),
                    sample_size=int(stats.get("sample_size", 0)),
                    wins=int(stats.get("wins", 0)),
                    total=int(stats.get("total", 0)),
                    avg_mfe_pct=float(stats.get("avg_mfe_pct", 0.0)),
                    avg_mae_pct=float(stats.get("avg_mae_pct", 0.0)),
                    avg_bars_to_outcome=float(stats.get("avg_bars_to_outcome", 0.0)),
                    historical_edge_score=float(stats.get("historical_edge_score", 0.0)),
                    timeouts=int(stats.get("timeouts", 0)),
                    resolution_rate=(
                        float(stats["resolution_rate"]) if stats.get("resolution_rate") is not None else None
                    ),
                    is_synthetic=bool(stats.get("is_synthetic", False)),
                )
            )

    items.sort(
        key=lambda item: (
            item.timeframe,
            item.historical_edge_score,
            item.win_rate,
            item.sample_size,
        ),
        reverse=True,
    )
    return PatternStatsResponse(generated_at=datetime.now(UTC).replace(tzinfo=None).isoformat(), items=items)


@router.post("/stats/refresh")
async def refresh_pattern_stats(background_tasks: BackgroundTasks) -> dict[str, str | bool]:
    background_tasks.add_task(run_backtest)
    return {
        "accepted": True,
        "message": "Pattern backtest refresh started in the background.",
        "requested_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
    }
