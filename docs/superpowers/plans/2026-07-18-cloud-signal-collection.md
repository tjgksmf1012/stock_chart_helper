# 클라우드 신호 수집 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** GitHub Actions가 평일 16:35에 신호를 수집해 저장소에 커밋하고, 로컬 앱이 켤 때 동기화한다.

**Architecture:** 스펙 `2026-07-18-cloud-signal-collection-design.md` 그대로. 순수 로직은 `app/services/collected_signals.py`(TDD), IO는 스크립트/라우트.

**Tech Stack:** Python + GitHub Actions. 테스트: `./.venv/Scripts/python.exe -m pytest tests/lab/ -q` (backend/).

### Task 1: collected_signals 서비스 (TDD)

**Files:** Create `backend/app/services/collected_signals.py` / Test `backend/tests/lab/test_collected_signals.py`

- [ ] 실패 테스트: `merge_signal_records` — 신규 append·중복 무시·기존 순서 보존·(strategy,code,date) 키 / `parse_collected_records` — 정상 파싱·깨진 줄 무시·빈 텍스트
- [ ] 구현:
  - `record_key(rec) -> tuple[str,str,str]`
  - `merge_signal_records(existing_lines: list[str], new_records: list[dict]) -> tuple[list[str], int]` — 기존 줄 파싱해 키 수집, 새 레코드 중 미존재만 json.dumps(ensure_ascii=False)로 append
  - `parse_collected_records(text: str) -> list[dict]` — 줄 단위 json.loads, 실패 줄 skip, 필수 키(strategy_id/code/signal_date/stop_price) 없으면 skip
- [ ] 통과 + 커밋 `feat(lab): collected_signals 병합·파싱 로직`

### Task 2: run_lab 리포트 사본 발행 + 현재 리포트 커밋

**Files:** Modify `backend/scripts/run_lab.py` / Create `backend/collected/lab_reports/*.json`

- [ ] run_lab 저장부에서 trades 제외 사본을 `backend/collected/lab_reports/<strategy>.json`에도 저장 (덮어쓰기)
- [ ] 일회성: 현재 최신 리포트 5개를 같은 형식으로 복사하는 인라인 파이썬 실행 → 커밋
- [ ] 커밋 `feat(lab): 검증 리포트 공개 사본 — Actions 자격 판정 소스`

### Task 3: collect_signals.py 스크립트

**Files:** Create `backend/scripts/collect_signals.py`

- [ ] 헤드리스 CLI: collected/lab_reports 로드 → eligible_strategy_ids(pass/watch) → fetch_current_universe_biased(60) → 일봉 420 로드 → 전략별 collect_recent_signals(패널 지원 포함) → verdict/label 부착 → merge_signal_records로 `collected/paper_signals.jsonl` 갱신 → 추가 건수 출력. cp949 가드 포함(run_lab과 동일).
- [ ] 로컬 1회 실행으로 JSONL 생성 확인 (신호 12건 예상) → 커밋 `feat(lab): 헤드리스 신호 수집 CLI + 첫 수집분`

### Task 4: 워크플로

**Files:** Create `.github/workflows/collect-signals.yml`

- [ ] cron `35 7 * * 1-5` + workflow_dispatch, permissions contents:write, setup-python 3.12 + pip cache, `pip install -r backend/requirements.txt`, `python scripts/collect_signals.py` (cwd backend), 변경 시에만 git commit/push (`github-actions[bot]`)
- [ ] 커밋 `feat(lab): 매일 16:35 신호 수집 워크플로`

### Task 5: 로컬 동기화 + 마무리

**Files:** Modify `backend/app/core/config.py`, `backend/app/api/routes/lab.py`, `backend/app/main.py`

- [ ] config: `collected_signals_url: str = "https://raw.githubusercontent.com/tjgksmf1012/stock_chart_helper/main/backend/collected/paper_signals.jsonl"`
- [ ] lab.py: `async def sync_collected_signals()` — url 비면 no-op; httpx GET(10s) → parse_collected_records → 기존 `_record_paper_trades`와 같은 dedupe 삽입 경로 재사용(레코드 dict 형태가 신호 dict와 호환되게 Task 3에서 필드 맞춤); 예외는 warning 로그만
- [ ] main.py: startup에서 `asyncio.create_task(sync_collected_signals())` + 스케줄 16:25 job `id="collected_signals_sync"`
- [ ] 전체 pytest 그린 → 커밋 → PR → 머지 → **workflow_dispatch 실행해 러너에서 KRX 접근 가능 여부 실측** → 결과 보고 (실패 시 사실대로 + Railway 재논의)
