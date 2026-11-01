#!/usr/bin/env bash
# 시연 서비스 켜기 — 준비(가상환경·라이브러리·inbox/)를 확인하고 시연 화면(app.py)을 켠 뒤 브라우저를 연다.
#
#   ./start.sh                 실제 실행 — 올린 녹취록마다 Claude Code 를 부른다 (사용량이 든다)
#   ./start.sh --replay        다시 보기 — 모델 없이 저장해 둔 초안으로 같은 흐름 (리허설용)
#   ./start.sh --port 8080     다른 포트로
#   ./start.sh --no-open       브라우저를 열지 않는다
#
# 다시 보기의 단계 사이 쉬는 시간은 REPLAY_DELAY(초, 기본 2) — 예: REPLAY_DELAY=3 ./start.sh --replay
# 끄려면 Ctrl+C. 폴더 감시(scripts/watch.sh)도 같이 꺼진다.
set -u
cd "$(dirname "$0")" || exit 64
export PATH="$HOME/.local/bin:$PATH"

OPEN=1; PORT=8000; REPLAY=0; ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --no-open) OPEN=0 ;;
    --replay) REPLAY=1; ARGS+=("$1") ;;
    --port) PORT="${2:-8000}"; ARGS+=("$1" "$PORT"); shift ;;
    *) ARGS+=("$1") ;;
  esac
  shift
done

command -v uv >/dev/null || { echo "uv 가 없다 — https://docs.astral.sh/uv/ 에서 설치한 뒤 다시"; exit 1; }
uv sync -q || { echo "가상환경·라이브러리 준비(uv sync)에 실패했다"; exit 1; }   # .venv 가 없으면 만들고 pyproject.toml 대로 맞춘다
mkdir -p inbox

if [ $REPLAY -eq 0 ]; then
  command -v claude >/dev/null || { echo "claude 가 PATH 에 없다 — 실제 실행에는 Claude Code 가 필요하다. 리허설은 ./start.sh --replay"; exit 1; }
  echo "실제 실행 모드: 녹취록을 올릴 때마다 Claude Code 가 불린다 ($(claude --version 2>/dev/null | head -1))"
fi

if command -v ss >/dev/null && ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  echo "포트 $PORT 를 이미 누가 쓰고 있다 — 이미 켜 둔 시연이 있거나, ./start.sh --port 8080 처럼 다른 포트로"; exit 1
fi

URL="http://127.0.0.1:$PORT"
if [ $OPEN -eq 1 ]; then
  (
    sleep 1.5
    for opener in wslview xdg-open open; do
      command -v "$opener" >/dev/null && { "$opener" "$URL" >/dev/null 2>&1 && exit 0; }
    done
    command -v explorer.exe >/dev/null && explorer.exe "$URL" >/dev/null 2>&1
  ) &
fi

exec uv run python app.py "${ARGS[@]}"
