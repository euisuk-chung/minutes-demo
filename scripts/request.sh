#!/usr/bin/env bash
# 요청 하나를 처리한다 — cron 이나 watch.sh 가 부른다.
#
#   scripts/request.sh <녹취록 경로>            요청을 열고, 작성이 필요하면 Claude Code 를 헤드리스로 부른다
#   scripts/request.sh --dry-run <녹취록 경로>  부를 명령만 찍는다(요청도 열지 않는다)
#
# 순서: 요청 열기(같은 녹취록이면 건너뜀) → claude -p "/handle-request <요청 id>" → 마무리(지나온 길·끝 상태).
# 끝날 때 신호: 0 회의록이 나옴 · 3 사람에게 넘어옴 · 1 실패 · 건너뛰면 0.
#
# cron 에는 터미널도 로그인한 사람의 PATH 도 없다. 그래서 첫 줄에서 이 프로젝트 폴더로 들어가고
# (이 폴더의 .claude/ 만 걸리게), claude 를 찾을 곳을 PATH 에 채운다.
# --bare 는 붙이지 않는다 — 차단 장치(보호·검수·다음 단계)가 모두 꺼진다.
set -u
cd "$(dirname "$0")/.." || exit 64
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
# -p 실행에서는 하위 에이전트가 기본으로 백그라운드에서 돈다(공식 문서). 끝날 때까지 기다리게 끈다 — guard.py 도 막는다.
export CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1
CLAUDE_BIN="${CLAUDE_BIN:-claude}"

DRY=0
if [ "${1:-}" = "--dry-run" ]; then DRY=1; shift; fi
[ $# -eq 1 ] || { echo "쓰는 법: scripts/request.sh [--dry-run] <녹취록 경로>"; exit 64; }

CMD=handle-request
# Claude 를 부르는 옵션은 이 함수 한 곳에 둔다(네 프로젝트가 같은 모양). CMD 는 부를 명령 이름이다.
claude_args() {
  # 본 에이전트의 모델: 구독에 맞춰 환경 변수 ANTHROPIC_MODEL 로 고른다(Pro 는 sonnet, Max 는 opus). 없으면 sonnet.
  # 자동 실행은 --setting-sources project 라 대화 창에서 /model 로 저장한 값을 읽지 않는다 — 그래서 여기서 따로 받는다.
  # 하위 에이전트 drafter 는 .claude/agents/drafter.md 의 model: sonnet(가벼운 일은 가벼운 모델)을 그대로 쓴다.
  MODEL="${ANTHROPIC_MODEL:-sonnet}"
  # 계정에 연결한 커넥터(MCP — 메일·캘린더 같은)는 설정 파일이 아니라 계정에 붙어 있어 --setting-sources 로 빠지지 않는다.
  # 이 실행은 쓰지 않는데 도구 목록이 부를 때마다 문맥에 통째로 실리니 --strict-mcp-config 로 뺀다.
  CLAUDE_ARGS=(-p "/$CMD $1" --model "$MODEL" --setting-sources project --strict-mcp-config --permission-mode dontAsk
    --tools "Read,Write,Agent,Bash"
    --allowedTools "Read,Write,Agent,Task,Bash(uv run python scripts/open_request.py:*)"
    --output-format json)
}

if [ $DRY -eq 1 ]; then
  echo "(dry-run) 요청 열기: uv run python scripts/open_request.py $1"
  claude_args '<요청 id>'
  echo "(dry-run) 작성이 필요하면: REQUEST_ID=<요청 id> uv run python scripts/limited.py 600 $CLAUDE_BIN ${CLAUDE_ARGS[*]}"
  exit 0
fi

out=$(uv run python scripts/open_request.py "$1"); code=$?
echo "$out" | grep -v '^REQUEST_ID='
[ $code -eq 10 ] && exit 0                       # 이미 처리한 녹취록
rid=$(echo "$out" | sed -n 's/^REQUEST_ID=//p')
[ -n "$rid" ] || exit "$code"

if [ $code -eq 0 ]; then
  claude_args "$rid"
  REQUEST_ID="$rid" uv run python scripts/limited.py 600 "$CLAUDE_BIN" "${CLAUDE_ARGS[@]}" \
    > "requests/$rid/claude.json" 2> "requests/$rid/claude.err"
fi
uv run python scripts/open_request.py --finish "$rid"
