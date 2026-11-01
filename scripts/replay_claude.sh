#!/usr/bin/env bash
# 다시 보기 모드의 가짜 claude — scripts/request.sh 가 CLAUDE_BIN 으로 부른다. 내용은 replay_claude.py
cd "$(dirname "$0")/.." || exit 64
exec uv run python scripts/replay_claude.py "$@"
