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

## Local Run (권장 — 데스크톱 모드)

Render/Vercel 없이 이 컴퓨터에서만 돌리는 게 기본 실행 방식입니다. Postgres/Redis 서버도
필요 없습니다 (SQLite 파일 하나 + 메모리 캐시로 자동 대체). 하루 4번 자동 스캔이나
10분마다 관심종목 체크 같은, 상시 서버에서만 의미 있는 백그라운드 작업은 기본적으로
꺼져 있고, 화면을 열 때와 새로고침 버튼으로만 갱신합니다.

macOS / Linux:

```bash
./scripts/run_local.sh
```

Windows:

```bat
run.bat
```

처음 실행하면 `backend/.env`가 없을 때 `backend/.env.local.example`(SQLite, 스케줄러 꺼짐)을
자동으로 복사해서 씁니다. 직접 커스터마이즈하려면 미리 복사해서 값을 바꿔두면 됩니다:

```bash
cp backend/.env.local.example backend/.env
```

직접 실행하려면:

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

## Deployment (선택 사항 — 상시 서버로 돌리고 싶을 때)

자동 스캔이나 관심종목 알림처럼 컴퓨터를 꺼도 계속 동작해야 하는 기능이 필요할 때만
고려하면 됩니다. 이 경우 `backend/.env.local.example` 대신 `backend/.env.example`
(Postgres/Redis 기반)을 쓰고, `ENABLE_SCHEDULER=true`로 설정하세요.

Railway를 예로 든 참고 설정입니다 (이 저장소는 특정 플랫폼에 실제로 배포되어 있지
않습니다 — 필요할 때 아래 config를 참고해 직접 연결하면 됩니다):

- Railway config file: [backend/railway.toml](backend/railway.toml)
- Backend Dockerfile: [backend/Dockerfile](backend/Dockerfile)

권장 설정:

- Service Root Directory: `/backend`
- Railway config file path: `/backend/railway.toml`
- Healthcheck path: `/health`
- PORT: Railway 기본 주입값 사용

프론트엔드를 별도로 호스팅한다면 백엔드 주소를 아래처럼 지정하면 됩니다.

```env
VITE_API_BASE_URL=https://your-railway-domain.up.railway.app
```

Railway로 배포할 때는 백엔드 환경 변수도 아래처럼 맞추는 것을 권장합니다.

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

## Toss Securities Open API Setup

토스증권 Open API(시세/캔들 조회, OAuth2 client_credentials)를 KIS와 나란히 쓸 수 있습니다.
발급: [corp.tossinvest.com/ko/open-api](https://corp.tossinvest.com/ko/open-api)

```env
TOSS_CLIENT_ID=your_client_id
TOSS_CLIENT_SECRET=your_client_secret
# 실시간 분봉/현재가 소스 우선순위. 기본값은 토스 우선.
LIVE_INTRADAY_PROVIDER_ORDER=toss,kis
```

현재 연동 방향:

- 실시간 1분 데이터는 `LIVE_INTRADAY_PROVIDER_ORDER`에 설정된 순서대로 토스/KIS를 시도 (기본: 토스 우선, 실패 시 KIS)
- 15분 / 30분 / 60분 차트는 1분 데이터를 리샘플링하거나 저장 분봉을 재사용
- 둘 다 없으면 공개 분봉 소스와 로컬 저장 캐시를 fallback으로 사용
- 토스는 계좌 조회·매매(Account/Asset/Order)는 사용하지 않음 — 이 앱은 시세 조회 전용
- `/system/status`에서 두 소스의 설정/토큰 캐시 상태를 확인할 수 있습니다.

## Useful URLs

- Frontend: [http://localhost:5173](http://localhost:5173)
- API docs: [http://localhost:8001/docs](http://localhost:8001/docs)
- Health: [http://localhost:8001/health](http://localhost:8001/health)

## Notes

- 월봉 / 주봉 / 일봉은 KRX 기준 분석을 우선합니다.
- 분봉은 데이터 소스 상태와 저장 캐시 여부에 따라 정확도 차이가 있을 수 있습니다.
- 이 프로젝트는 투자 권유 서비스가 아니라 분석 보조 도구입니다.
