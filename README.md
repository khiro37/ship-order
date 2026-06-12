# 조선 수주 대시보드 공개 배포용

이 폴더는 Streamlit Community Cloud 또는 별도 서버에 올리는 공개 배포용 코드입니다.

## 실행

```bash
streamlit run app.py
```

Streamlit Community Cloud에서 이 저장소를 연결할 때는 Main file path를 `app.py`로 지정하세요.

## 포함된 것

- `app.py`: 공개용 읽기 전용 대시보드
- `ship_order_summary.csv`: 정적 수주 데이터
- `ship_order_targets.csv`: 정적 수주목표 데이터
- `ship_market_cap.csv`: 정적 시가총액 데이터
- `update_orders.py`: GitHub Actions에서 실행하는 DART 수주내역 업데이트 코드

## 포함하지 않는 것

- DART API 키
- 실적예측 탭

## 관리자 모드

Streamlit Cloud의 App settings > Secrets에 아래처럼 등록하세요.

```toml
ADMIN_PASSWORD = "원하는_관리자_비밀번호"
```

관리자 탭에서는 일간 조회수, 일간 이용자수, 요청 목록을 확인할 수 있습니다.

현재 조회 통계와 요청 목록은 앱 런타임 파일에 저장됩니다. Streamlit Cloud 재시작 또는 재배포 시 초기화될 수 있으므로, 영구 보관이 필요하면 Google Sheets, Supabase, Firebase 같은 외부 저장소를 연결하세요.

## 데이터 업데이트 방식

공개 사이트 이용자는 원본 CSV를 변경할 수 없습니다.

GitHub Actions가 평일 월~금 KST 11:30, 16:00, 20:00에 DART 수주내역을 갱신한 뒤 공개용 CSV만 다시 커밋하도록 구성되어 있습니다.

GitHub repository의 Settings > Secrets and variables > Actions > Repository secrets에 아래 값을 등록하세요.

```text
DART_API_KEY=발급받은_DART_API_KEY
```

스케줄은 GitHub Actions의 UTC 기준 cron으로 등록되어 있습니다.

- KST 11:30 = UTC 02:30
- KST 16:00 = UTC 07:00
- KST 20:00 = UTC 11:00

로컬에서 직접 갱신하려면 아래처럼 실행합니다.

```bash
export DART_API_KEY="발급받은_DART_API_KEY"
python update_orders.py --tasks orders --no-dashboard
```
