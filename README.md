# Alert Bot (Safe Clone)

이 저장소는 원본 Alert Bot을 기반으로 한 안전한 복제본입니다. 원본의 많은 기능을 유지하지만, 사이트의 접근 제어를 우회하거나 자동 차단을 회피하는 동작(예: 403 대응을 위한 의도적인 헤더 변경 또는 반복적 우회 시도)은 포함하지 않습니다.

이 프로젝트는 제로월드 홍대점 예약 페이지에서 2026년 6월 3일, 테마 `[홍대] 층간소음`의 예약 가능 시간이 열리면 텔레그램으로 알림을 보내는 용도로 설계되었습니다. 라즈베리파이 Zero 2에서 동작하도록 가볍게 구성되어 있습니다.

## 중요: 윤리/법적 주의
- 공식 API가 제공된다면 API 사용을 우선하세요.

## 설정
환경변수를 사용해 구성합니다.

필수 환경 변수:
- `TARGET_URL`: 모니터링할 웹사이트 주소
- `TELEGRAM_BOT_TOKEN`: 텔레그램 봇 토큰
- `TELEGRAM_CHAT_ID`: 알림을 받을 채팅 ID

선택 환경 변수:
- `RESERVATION_YEAR`: 감시할 연도, 기본값은 `2026`
- `RESERVATION_MONTH`: 감시할 월, 기본값은 `6`
- `RESERVATION_DAY`: 감시할 일, 기본값은 `3`
- `RESERVATION_THEME`: 감시할 테마명, 기본값은 `[홍대] 층간소음`
- `POLL_INTERVAL_SECONDS`: 폴링 간격(초)
- `HEADLESS`: 브라우저를 headless로 실행할지 여부(true/false)
- `BROWSER_TIMEOUT_MS`: 페이지 이동/클릭 타임아웃
- `INTERACTION_WAIT_MS`: 각 클릭 사이 대기 시간
- `ALERT_ON_START`: 첫 검사에서 이미 열려 있으면 바로 알릴지 여부(true/false)
- `STATE_DB_PATH`: 상태를 저장할 JSON 파일 경로
- `VERIFY_SSL`, `CA_BUNDLE_PATH`: 인증서 설정
- `HTTP_PROXY`, `HTTPS_PROXY`: 프록시 설정(회사 네트워크 등 합법적 목적)
- `USER_AGENT`, `ACCEPT_LANGUAGE`, `REFERER`, `COOKIE`: 요청 헤더(정상적이고 합법적인 목적에 한정)

## 실행
- `.env.example`을 복사해 `.env`를 만든 뒤 값을 채웁니다.
- 의존성을 설치한 뒤, Chromium과 chromedriver를 설치합니다.

라즈베리파이 Zero 2 W에서는 Selenium + 시스템 Chromium 조합을 권장합니다.

```
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.txt -i https://pypi.org/simple
sudo apt install -y chromium chromium-driver
python -m alertbot
```

## 동작 방식
대상 페이지를 주기적으로 연 뒤, 2026년 6월 3일과 테마 `[홍대] 층간소음`을 선택합니다. 그 상태에서 시간 슬롯 중 하나라도 활성화되면 텔레그램으로 알림을 전송합니다.

## 권장 사항
- 사이트가 공개 API를 제공하면 API를 사용하세요.
- 접근이 금지된 페이지나 데이터는 수집하지 마세요.
