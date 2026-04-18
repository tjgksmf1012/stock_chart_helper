# Stock Chart Helper

국내 주식 차트를 교과서형 패턴과 확률 관점으로 해석하는 분석 도구입니다.

현재 포함된 주요 기능:

- 대시보드 5개 카테고리 스캔
- 전체 시장 스캔 상태 확인 및 수동 재실행
- 종목 검색 및 차트 분석 화면
- 월봉 / 주봉 / 일봉 / 60분 / 30분 / 15분 / 1분 차트 조회
- 패턴 라이브러리
- 스크리너 필터 / 정렬 / 프리셋
- 멀티 타임프레임 합산 점수
- 표본 신뢰도 / 데이터 품질 / 데이터 상태 기반 해석

## Tech Stack

- Backend: FastAPI, Python
- Frontend: React, TypeScript, Vite
- Chart: lightweight-charts
- Data:
  - Daily: pykrx, FinanceDataReader fallback
  - Intraday: Yahoo Finance fallback + local intraday store
  - Optional: KIS API
- Cache: Redis fallback + in-memory cache

## Run

가장 간단한 실행:

```bat
run.bat
```

`run.bat`은 다음 순서로 동작합니다.

- 백엔드 `8001` 포트 실행
- 프론트 `5173` 포트 실행
- 두 서버가 실제로 준비될 때까지 대기
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

## KIS Setup

실시간 분봉 정확도를 높이려면 `backend/.env`에 KIS API 키를 넣어주세요.

```env
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_NO=12345678-01
KIS_BASE_URL=https://openapi.koreainvestment.com:9443
```

현재 연동 방식:

- 당일 1분 데이터는 KIS 우선 사용
- 15분 / 30분 / 60분 차트는 1분 데이터를 리샘플링
- KIS가 없으면 공개 분봉 소스와 저장 캐시 fallback 사용

## URLs

- Frontend: http://localhost:5173
- API docs: http://localhost:8001/docs

## Notes

- 월봉 / 주봉 / 일봉은 KRX 기준 해석이 중심입니다.
- 분봉은 공개 소스와 저장 캐시에 의존하므로 더 보수적으로 해석합니다.
- 확률 엔진은 표본 수, 표본 신뢰도, 데이터 품질, 멀티 타임프레임 정렬을 함께 반영합니다.
- 이 프로젝트는 투자 권유 서비스가 아니라 분석 보조 도구입니다.
