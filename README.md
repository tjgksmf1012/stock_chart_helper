# Stock Chart Helper

국내 주식 차트를 교과서형 패턴과 확률 관점으로 해석하는 분석 도구입니다.

현재 브랜치 기준 주요 기능:

- 대시보드 5개 카테고리 스캔
- 전체 시장 스캔 상태 확인 및 수동 재실행
- 종목 검색 + 차트 분석 화면
- 일봉 / 60분 / 15분 차트 조회
- 패턴 라이브러리
- 스크리너 필터 / 정렬 / 프리셋

## Tech Stack

- Backend: FastAPI, Python
- Frontend: React, TypeScript, Vite
- Chart: lightweight-charts
- Data:
  - Daily: pykrx, FinanceDataReader fallback
  - Intraday: KIS API (today minute bars) + Yahoo Finance fallback
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

직접 실행:

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

## KIS Setup

실시간 분봉 정확도를 높이려면 `backend/.env`에 KIS API 키를 넣어주세요.

```env
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_NO=12345678-01
KIS_BASE_URL=https://openapi.koreainvestment.com:9443
```

현재 연동 방식은 다음과 같습니다.

- 오늘 장중 1분 데이터: KIS API 우선 사용
- 15분 / 60분 차트: KIS 1분 데이터를 리샘플링
- 과거 장중 히스토리: Yahoo Finance fallback 유지
- KIS 미설정 또는 호출 실패 시: 기존 Yahoo fallback 유지

## URLs

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs

## Branch

현재 작업 브랜치:

- `codex/kis-api-integration`

## Notes

- 15분 / 60분 차트는 KIS 오늘 분봉 + Yahoo Finance 히스토리를 합쳐서 보여줍니다.
- KIS 분봉 API는 당일 데이터 중심이라, 오래된 분봉 히스토리는 fallback 소스에 의존합니다.
- 확률 엔진은 현재 룰 기반 MVP 버전입니다.
- 이 프로젝트는 투자 권유 서비스가 아니라 분석 보조 도구입니다.
