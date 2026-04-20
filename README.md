# Stock Chart Helper

국내 주식 차트를 패턴, 확률, 거래 준비도 관점에서 분석하는 프로젝트입니다.

현재 포함된 주요 기능:

- 대시보드 섹션형 후보 탐색
- 종목 검색 및 차트 상세 분석
- 월봉 / 주봉 / 일봉 / 60분 / 30분 / 15분 / 1분 차트 조회
- 패턴 라이브러리와 백테스트 통계
- 거래 준비도 / 진입 구간 / 신선도 / 재진입 구조 점수
- 관심종목, 신호 저장, 결과 추적, 오탐 신고 흐름

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

운영 URL:

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

## Railway Migration

Render Free는 15분 동안 inbound traffic이 없으면 슬립 상태로 들어가므로, 실제 사용성까지 생각하면 백엔드를 Railway persistent service로 옮기는 구성이 더 무난합니다.

이 저장소에는 Railway용 config-as-code 파일이 이미 포함되어 있습니다:

- Railway config file: [backend/railway.toml](backend/railway.toml)
- Backend Dockerfile: [backend/Dockerfile](backend/Dockerfile)

권장 설정:

- Service Root Directory: `/backend`
- Railway config file path: `/backend/railway.toml`
- Healthcheck path: `/health`
- PORT: Railway 기본 주입값 사용

Vercel에서는 백엔드 주소만 Railway 도메인으로 바꾸면 됩니다.

```env
VITE_API_BASE_URL=https://your-railway-domain.up.railway.app
```

Railway로 이전할 때는 백엔드 환경 변수도 아래처럼 맞추는 것을 권장합니다.

```env
DEPLOYMENT_PLATFORM=railway
SELF_HEALTHCHECK_URL=
ENABLE_PLATFORM_KEEPALIVE=false
```

## KIS Setup

실시간 분봉 정확도를 높이려면 `backend/.env` 또는 배포 환경 변수에 KIS 값을 넣어주세요.

```env
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_NO=12345678-01
KIS_ENV=auto
```

현재 연동 방향:

- 당일 1분 데이터는 KIS 우선 사용
- 15분 / 30분 / 60분 차트는 1분 데이터를 리샘플링하거나 저장 분봉을 재사용
- KIS가 없으면 공개 분봉 소스와 로컬 저장 캐시를 fallback으로 사용

## Useful URLs

- Frontend: [http://localhost:5173](http://localhost:5173)
- API docs: [http://localhost:8001/docs](http://localhost:8001/docs)
- Health: [http://localhost:8001/health](http://localhost:8001/health)

## Notes

- 월봉 / 주봉 / 일봉은 KRX 기준 분석을 우선합니다.
- 분봉은 데이터 소스 상태와 저장 캐시 여부에 따라 정확도 차이가 있을 수 있습니다.
- 이 프로젝트는 투자 권유 서비스가 아니라 분석 보조 도구입니다.
