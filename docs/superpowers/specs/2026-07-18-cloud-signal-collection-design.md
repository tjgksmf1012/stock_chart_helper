# 클라우드 신호 수집 — GitHub Actions 크론

날짜: 2026-07-18
상태: 승인됨 (사용자 선택: "GitHub Actions 크론")

## 문제

신호 계산(=종이매매 기록)은 로컬 백엔드가 켜져 있어야 돈다. 컴퓨터를 안 켜는 날이
5영업일 넘게 이어지면 그 사이 신호는 영구 유실 — 실측 표본 누적(드리프트 감시의
재료)이 사용 빈도에 묶여 있다. GitHub의 서버가 매일 대신 수집하게 한다.

## 아키텍처

```
GitHub Actions (평일 16:35 KST)                     로컬 앱 (켤 때)
─────────────────────────────                      ─────────────────
collect_signals.py                                  시작 시 + 16:25
  ├ collected/lab_reports/*.json → 자격(pass/watch)   raw.githubusercontent.com에서
  ├ 유니버스 60 + 일봉 → collect_recent_signals        collected/paper_signals.jsonl 받아
  └ collected/paper_signals.jsonl에 append+커밋        DB에 dedupe 삽입 → 이후 청산 평가
```

- 단일 진실 원천: **기록(open)은 JSONL, 청산(close)·드리프트는 로컬 DB.**
  청산 평가는 과거 봉으로 소급 가능하므로 로컬만으로 충분하다.
- 저장 경로는 `backend/collected/` — `data/`는 gitignore라 커밋 불가.
- 저장소가 PUBLIC이라 로컬 동기화는 무인증 raw URL GET.

## 구성 요소

1. **`backend/collected/lab_reports/<strategy>.json`** (커밋): run_lab이 리포트 저장 시
   trades 제외 사본을 여기에도 쓴다. Actions의 자격 판정 소스. 현재 최신 5개를 즉시 커밋.
   (클라우드에는 DB가 없어 드리프트 강등은 반영하지 않는다 — 수집은 pass/watch 전부.
   이탈 전략도 실측은 계속 쌓는 게 측정에 유리하고, 노출 강등은 로컬 게이트가 담당.)
2. **`backend/collected/paper_signals.jsonl`** (커밋): 한 줄 = 신호 1건
   `{strategy_id, strategy_label, verdict, code, signal_date, reference_price,
   stop_price, target_price, max_holding_days, collected_at}`.
   dedupe 키 = (strategy_id, code, signal_date). append-only.
3. **`backend/scripts/collect_signals.py`**: 헤드리스 수집 CLI.
   순수 병합 로직 `merge_signal_records(existing_lines, new_records) -> (lines, n_added)`는
   `app/services/collected_signals.py`에 TDD로.
4. **`.github/workflows/collect-signals.yml`**: cron `35 7 * * 1-5`(=16:35 KST) +
   workflow_dispatch, permissions contents:write, python 3.12 + pip 캐시,
   스크립트 실행 후 JSONL 변경 시에만 커밋/푸시.
5. **로컬 동기화** `sync_collected_signals()` (routes/lab.py):
   설정 `collected_signals_url`(기본 = 본 저장소 raw URL, 빈 값이면 비활성)에서 JSONL을
   받아 파싱(`parse_collected_records` — 깨진 줄 무시, TDD) 후 기존 dedupe 경로로 DB 삽입.
   호출 지점: 백엔드 시작 시(백그라운드, 실패 무해) + 16:25 스케줄(청산 평가 16:30 직전).

## 하지 않는 것

- 클라우드에서 청산 평가·드리프트 판정 없음 (로컬 소급으로 충분).
- 스캔·알림·전망 등 다른 기능의 클라우드화 없음.
- 비공개 저장소 인증 처리 없음 (현재 PUBLIC).

## 리스크

- KRX/네이버가 GitHub 러너(해외 IP)를 차단하면 수집 실패 — 머지 후 workflow_dispatch로
  실측 확인, 실패 시 결과를 사실대로 보고하고 대안(Railway) 재논의.

## 검증

- 순수 로직 TDD (병합·파싱·dedupe), 백엔드 전체 그린.
- collect_signals.py 로컬 1회 실행 → JSONL 생성 확인.
- 머지 후 workflow_dispatch 실행 → 러너에서 수집 성공 여부 확인.
- 로컬 동기화: JSONL의 신규 건이 DB에 들어오고 중복은 무시되는지.
