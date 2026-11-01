#!/usr/bin/env bash
# 폴더 감시 — inbox/ 에 녹취록이 새로 생기면 요청을 하나 만든다(사람이 시작을 누르지 않는다).
#
#   scripts/watch.sh [--interval 5]
#
# 같은 내용의 녹취록은 request.sh 가 지문으로 알아보고 건너뛴다. 여기서는 파일 이름만 기억한다.
set -u
cd "$(dirname "$0")/.." || exit 64
INTERVAL=5
[ "${1:-}" = "--interval" ] && INTERVAL="${2:-5}"
mkdir -p inbox
declare -A SEEN
echo "watching inbox/ every ${INTERVAL}s"
while true; do
  for f in inbox/*.txt; do
    [ -e "$f" ] || continue
    key="$f:$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f")"
    [ -n "${SEEN[$key]:-}" ] && continue
    SEEN[$key]=1
    scripts/request.sh "$f"
  done
  sleep "$INTERVAL"
done
