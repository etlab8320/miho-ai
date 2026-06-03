---
name: server-watchdog-html-monitor
description: SSH로 여러 서버 상태를 수집해 세로형 HTML 카드를 만들고 PNG로 렌더링한 뒤, 빨간불일 때만 Discord에 알리는 Miho 감시 패턴.
version: 1.0.0
platforms: [macos, linux]
---

# Server Watchdog HTML Monitor

여러 서버를 계속 감시하면서 **사람이 한눈에 보는 가로형 이미지 리포트**가 필요할 때 쓴다. 현재 기본 레이아웃은 Discord 공유용 가로형 카드다.

핵심 흐름은 이거다.

1. 로컬 + 원격 서버 상태 수집
2. 상태를 green / amber / red로 판정
3. 가로형 HTML 카드 생성
4. Chrome headless로 PNG 렌더링
5. 메모리 상위 점유 / CPU 상위 / 좀비 프로세스를 카드에 포함
6. **red가 하나라도 있으면** Discord로 이미지를 보냄
7. red가 없으면 조용히 종료

## 권장 저장 위치

- 스크립트: `~/.miho/scripts/server_watchdog.py`
- 산출물: `~/.miho/media_cache/server-watchdog/`
  - `latest.json`
  - `latest.html`
  - `latest.png`

## 수집 방식

- 로컬 맥: `sysctl`, `vm_stat`, `df`, `ps`
- 원격 리눅스: `ssh`, `free`, `df`, `ps`, `os.getloadavg()`
- SSH alias는 `~/.ssh/config`를 사용하면 깔끔하다.

예시 alias:
- `etserver`
- `n100`
- `vultr`
- `cafe24`

## 판정 기준 예시

### Red
- `load1 / cpu_cores >= 1.0`
- 메모리 available 비율 `<= 10%`
- 디스크 사용률 `>= 90%`
- 좀비 프로세스 감지
- SSH/수집 실패

### Amber
- `load1 / cpu_cores >= 0.7`
- 메모리 available 비율 `<= 20%`
- 디스크 사용률 `>= 80%`
- swap 사용이 있고 메모리 여유가 같이 낮을 때

### 예외
- 로컬 맥미니에서 메모리 부족이 보여도, 상위 메모리 점유가 **게임/Steam/iTerm** 계열이면 메모리 경보는 눌러서 false positive를 줄인다.
- 대신 카드 안에는 메모리 상위 점유 원인을 계속 적어준다.

## HTML/PNG 렌더링

밝은 배경, 한국어 우선, 세로형 카드로 만든다.

Chrome headless 예시:

```bash
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --headless=new --disable-gpu --hide-scrollbars \
  --window-size=1080,3600 \
  --screenshot=/path/output.png \
  file:///path/input.html
```

렌더 뒤에는 **하단 빈 여백 자동 crop**을 넣는 편이 좋다. Discord 카드 전달감이 확 좋아진다.

더 좋은 1차 해법은 **HTML 내용에 맞춰 Chrome viewport 높이를 먼저 추정**하는 것이다. 3열 카드 그리드라면 서버 수를 보고 행 수를 계산해 window height를 조절하면 된다. crop은 마지막 미세 보정용으로만 두는 게 안전하다.

단, crop 단계는 **Pillow가 있을 때만** 돌리고, 없으면 이미지 생성 자체를 실패시키지 마라. cron 환경과 로컬 터미널의 Python site-packages가 다를 수 있어서, 시스템 Python에는 PIL이 있어도 Miho venv에는 없을 수 있다.

## 수동 테스트

전체 카드 생성:

```bash
python3 ~/.miho/scripts/server_watchdog.py
```

빨간불일 때만 Discord용 메시지 출력:

```bash
python3 ~/.miho/scripts/server_watchdog.py --emit-alert-only
```

출력 예시:

```text
🚨 서버 경고 감지
- 경고 대상: 맥미니
- 생성 시각: 2026-05-26 23:17:59 KST
MEDIA:/Users/.../.miho/media_cache/server-watchdog/latest.png
```

## Miho 크론 등록

script-only watchdog가 가장 가볍다.

```bash
miho cron create \
  --name server-watchdog-red-alert \
  --schedule 'every 15m' \
  --deliver origin \
  --script 'server_watchdog.py --emit-alert-only' \
  --no-agent
```

의미:
- `--no-agent`: LLM 없이 스크립트 stdout만 보냄
- stdout이 비면 조용함
- red가 있으면 메시지 + `MEDIA:` 이미지 전달

## 검증 체크리스트

1. `latest.png`가 실제로 생성되는가
2. 한국어가 깨지지 않는가
3. 마지막 카드와 푸터가 잘리지 않는가
4. 하단에 과한 빈 공간이 없는가
5. red 없음 → 아무 알림도 안 감
6. red 있음 → Discord에 이미지 첨부 알림 감

## 운영 판단

이 방식은 **가볍다**.

이유:
- 4~5대 SSH 조회는 짧고 단발성
- 상태 수집은 텍스트 명령 몇 개 수준
- PNG 렌더는 red일 때만 돌리면 더 가벼움
- 15분 간격이면 맥/서버 둘 다 부담이 거의 없다

다만 너무 촘촘하게 돌리면 불필요하다.
권장 시작점은:
- 일반 운영: `every 15m`
- 더 민감하게 보고 싶으면: `every 10m`
- 아주 보수적으로는: `every 30m`

## 함정

- `ps` 상위 프로세스에 **상태 수집용 python/ssh 자체**가 섞이지 않게 필터링해라.
- macOS `comm` 값은 경로가 잘리거나 애매하게 나올 수 있으니 `args`에서 앱 이름을 보정해라.
- 카드에는 최소한 **메모리 상위 / CPU 상위 / 좀비 프로세스 수 / 원인 문구**가 들어가야 한다.
- Chrome viewport가 너무 크면 아래 공백이 길어진다. crop으로 정리해라.
- 하단 여백 crop은 운영 필수 기능이 아니라 후처리다. `PIL/Pillow` 같은 이미지 후처리 의존성이 없다고 watchdog 전체가 실패하면 안 된다. `auto_crop_png()`는 `ModuleNotFoundError`를 잡아 crop만 건너뛰게 만들고, crop을 꼭 살리고 싶을 때만 Pillow 설치를 안내해라.
- SSH 실패는 그냥 무시하지 말고 **red**로 올려라. 감시가 끊긴 것도 장애다.
