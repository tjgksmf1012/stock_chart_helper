# Stock Chart Helper

국내 주식 차트를 교과서형 패턴과 확률 관점으로 해석하는 분석 도구입니다.

현재 브랜치 기준 주요 기능:

- 대시보드 5개 카테고리 랭킹
- 전체 시장 스캔 상태 확인 및 수동 재실행
- 종목 검색 + 차트 분석 화면
- 패턴 라이브러리
- 스크리너 필터 / 정렬 / 프리셋

## Tech Stack

- Backend: FastAPI, Python
- Frontend: React, TypeScript, Vite
- Chart: lightweight-charts
- Data: pykrx, FinanceDataReader fallback
- Cache: Redis fallback + in-memory cache

## Run

가장 간단한 실행:

```bat
run.bat
```

또는:

```bat
실행.bat
```

직접 실행 시:

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

## URLs

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs

## Branch

현재 작업 브랜치:

- `codex/scan-status-ui`

## Notes

- 분봉 데이터는 아직 완전한 실시간/KIS 연동 전 단계입니다.
- 확률 엔진은 현재 룰 기반 MVP 버전입니다.
- 이 프로젝트는 투자 권유 서비스가 아니라 분석 보조 도구입니다.
