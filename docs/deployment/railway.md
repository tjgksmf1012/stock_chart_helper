# Railway Backend Migration

이 문서는 `stock_chart_helper` 백엔드를 Render에서 Railway로 옮길 때 필요한 최소 설정을 정리합니다.

## Why Railway

- Render Free의 15분 idle sleep 문제를 피할 수 있습니다.
- 이 프로젝트는 이미 Docker 기반 백엔드가 있어 Railway persistent service에 올리기 쉽습니다.
- 프론트는 Vercel을 그대로 유지하고, 백엔드만 교체하면 됩니다.

## Repository Files

- Railway config: [backend/railway.toml](/C:/Users/tjgks/OneDrive/Desktop/stock_chart_helper/backend/railway.toml)
- Backend Dockerfile: [backend/Dockerfile](/C:/Users/tjgks/OneDrive/Desktop/stock_chart_helper/backend/Dockerfile)
- Env example: [backend/.env.example](/C:/Users/tjgks/OneDrive/Desktop/stock_chart_helper/backend/.env.example)

## Railway Service Settings

1. 새 Railway project 생성
2. GitHub repo 연결
3. Backend service 생성
4. Root Directory를 `/backend`로 설정
5. Config-as-Code file path를 `/backend/railway.toml`로 설정
6. Healthcheck path를 `/health`로 유지

## Required Environment Variables

최소 권장값:

```env
SECRET_KEY=generate-a-long-random-secret
ALLOWED_ORIGINS=https://frontend-mu-sooty-i4662dxm4r.vercel.app,http://localhost:5173
DEPLOYMENT_PLATFORM=railway
SELF_HEALTHCHECK_URL=
ENABLE_PLATFORM_KEEPALIVE=false
DEBUG=false
REDIS_URL=
```

선택값:

```env
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=
KIS_ENV=auto
```

## Database / Cache Notes

- 지금 구조는 `DATABASE_URL`이 없으면 기본 로컬 Postgres 값을 바라봅니다.
- Railway에서 실제 운영하려면 Postgres service를 추가하고 `DATABASE_URL`을 Railway Postgres 연결 문자열로 넣는 것을 권장합니다.
- `REDIS_URL`은 비워 두면 in-memory fallback cache를 사용합니다.
- 런타임 로컬 파일은 영속 저장소로 가정하면 안 됩니다.

## Frontend Change

Vercel 환경 변수:

```env
VITE_API_BASE_URL=https://your-railway-domain.up.railway.app
```

변경 후 프론트 재배포 필요

## Verification Checklist

- Railway 배포 후 `/health`가 200을 반환하는지 확인
- `/api/v1/dashboard/overview?timeframe=1d&limit=3` 응답 확인
- 프론트에서 검색, 대시보드, 차트 상세 진입 확인
- CORS 오류 없는지 브라우저 콘솔 확인
