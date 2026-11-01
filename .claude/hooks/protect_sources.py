"""PreToolUse — 원문 보호. 녹취록(inbox/·samples/·요청 폴더의 transcript.txt)은 고칠 수 없다.

guard.py 의 쓸 곳 목록과 겹치지만 따로 둔다. 원문을 지키는 규칙은 하나가 꺼져도 남아야 해서다.
Bash 로 쓰는 길(echo … > 파일)도 본다.
입력 JSON 이 깨졌으면 0 으로 통과한다 — 7차시에서 일부러 보이는 "조용히 통과하는 길" 이다.
"""

from __future__ import annotations

import json
import re
import sys

PROTECTED = ("inbox/", "samples/", "transcript.txt")


def hits(text: str) -> bool:
    return any(p in text for p in PROTECTED)


def main() -> int:
    try:
        inp = json.load(sys.stdin)
    except ValueError:
        return 0
    tool = inp.get("tool_name", "")
    ti = inp.get("tool_input") or {}
    target = ""
    if tool in ("Write", "Edit", "MultiEdit"):
        target = ti.get("file_path", "")
    elif tool == "Bash":
        cmd = ti.get("command", "")
        m = re.search(r"(>>?|\btee\b|\bmv\b|\bcp\b|\brm\b|\bsed -i\b)\s*(\S+)", cmd)
        target = cmd if m and hits(cmd) else ""
    if target and hits(target):
        print(f"{target} 는 원문이라 고칠 수 없다.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
