# Stock Chart Helper

국내 주식 차트를 패턴, 확률, 거래 준비도 관점에서 분석하는 웹 앱입니다.

현재 포함된 핵심 기능:

- 대시보드 다중 섹션 분석
- 종목 검색 및 차트 상세 분석
- 월봉 / 주봉 / 일봉 / 60분 / 30분 / 15분 / 1분 차트 조회
- 패턴 라이브러리
- 스크리너 필터 / 정렬 / 빠른 시작 프리셋
- 멀티 타임프레임 정렬 점수
- 거래 준비도 / 진입 구간 / 신선도 / 재진입 구조 점수
- 관심종목, 성과 추적, 운영 상태 확인

## Tech Stack

- Backend: FastAPI, Python
- Frontend: React, TypeScript, Vite
- Chart: `lightweight-charts`
- Daily data: `pykrx`, `FinanceDataReader` fallback
- Intraday data: Yahoo fallback + local intraday store + optional KIS API
- Cache: Redis fallback + in-memory cache

## Local Run

가장 간단한 실행:

```bat
run.bat
```

`run.bat`은 다음 순서로 동작합니다.

- 백엔드 `8001` 포트 실행
- 프론트 `5173` 포트 실행
- 두 서버가 실제로 뜰 때까지 대기
- 준비 완료 후 브라우저 열기

직접 실행:

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8001
```

```bash
cd frontend
npm install
npm run dev
```

## Deployment

현재 배포 구조:

- Frontend: Vercel
- Backend: Render

예시 운영 URL:

- Frontend: [https://frontend-mu-sooty-i4662dxm4r.vercel.app/](https://frontend-mu-sooty-i4662dxm4r.vercel.app/)
- Backend: [https://stock-chart-helper-api.onrender.com](https://stock-chart-helper-api.onrender.com)

프론트 환경 변수:

```env
VITE_API_BASE_URL=https://stock-chart-helper-api.onrender.com
```

백엔드 CORS 환경 변수:

```env
ALLOWED_ORIGINS=https://frontend-mu-sooty-i4662dxm4r.vercel.app,http://localhost:5173
```

## KIS Setup

실시간 분봉 정확도를 높이려면 `backend/.env` 또는 Render 환경 변수에 KIS 값을 넣어야 합니다.

```env
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_NO=12345678-01
KIS_ENV=auto
```

현재 연동 방식:

- 당일 1분 데이터는 KIS 우선 사용
- 15분 / 30분 / 60분 차트는 1분 데이터를 리샘플링하거나 저장 분봉을 재사용
- KIS가 없으면 공개 분봉 소스와 저장 캐시 fallback 사용

## Useful URLs

- Frontend: [http://localhost:5173](http://localhost:5173)
- API docs: [http://localhost:8001/docs](http://localhost:8001/docs)
- Health: [http://localhost:8001/health](http://localhost:8001/health)

## Notes

- 월봉 / 주봉 / 일봉은 KRX 기준 분석을 우선합니다.
- 분봉은 데이터 소스 상태와 저장 캐시 수준에 따라 품질 차이가 날 수 있습니다.
- 확률 점수는 표본 수, 표본 신뢰도, 데이터 품질, 멀티 타임프레임 정렬을 함께 반영합니다.
- 이 프로젝트는 투자 권유 서비스가 아니라 분석 보조 도구입니다.
