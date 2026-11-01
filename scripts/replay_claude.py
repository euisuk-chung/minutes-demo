"""다시 보기 모드의 가짜 claude — 모델을 부르지 않고, 저장해 둔 초안으로 Claude Code 가 하는 일을 흉내 낸다.

    CLAUDE_BIN=scripts/replay_claude.sh scripts/request.sh inbox/녹취록.txt

`scripts/request.sh` 가 진짜 claude 대신 이것을 부른다(`app.py --replay` 가 그렇게 켠다). 하는 일은
`tests/test_flow.py` 와 같다 — 초안 쓰기는 `samples/draft-*.json` 복사로, Claude Code 가 부르는 차단 장치는
같은 JSON 을 직접 넣어서. 그래서 요청 폴더의 기록(state.json · events.jsonl · review.json)은 실제 실행과 같은 모양으로 쌓인다.
화면에서 단계가 차례로 보이게 단계 사이를 `REPLAY_DELAY` 초(기본 2) 쉰다.

저장해 둔 초안은 견본 녹취록 둘(`samples/transcript-*.txt`)에만 있다.
다른 녹취록이면 작성하지 못하고 1 로 끝난다 — 그 녹취록은 실제 실행 모드에서만 된다.
견본 초안은 모두 실제 실행에서 drafter 가 쓴 것을 저장해 둔 것이다.
녹취록 A 는 초안이 둘이다. 같은 회의 폴더에 지난 회의록이 없으면 `draft-a.json`, 있으면(수집이 `previous` 를
찾았으면 — 견본 버튼이 놓는 2026-09-14 회의록 A', `samples/last-week/`) 지난 할 일 세 줄을 대 본
`draft-a-with-prev.json` 을 쓴다.

보장하지 않는 것: 실제 모델이 같은 순서로 도구를 부르고 거부 이유대로 다시 쓴다는 것.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 녹취록 → 저장해 둔 초안. 둘이면 (지난 회의록 없을 때, 있을 때)
DRAFTS = {"transcript-a.txt": ("draft-a.json", "draft-a-with-prev.json"), "transcript-b.txt": "draft-b.json"}


def hook(name: str, payload: dict, rid: str) -> str:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT), REQUEST_ID=rid, PYTHONUTF8="1")
    p = subprocess.run([sys.executable, str(ROOT / ".claude" / "hooks" / f"{name}.py")], input=json.dumps(payload),
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)
    return p.stdout + p.stderr


def main() -> int:
    args = sys.argv[1:]
    prompt = args[args.index("-p") + 1] if "-p" in args else ""
    rid = os.environ.get("REQUEST_ID") or prompt.removeprefix("/handle-request").strip()
    req = ROOT / "requests" / rid
    transcript = (req / "transcript.txt").read_text(encoding="utf-8").strip()
    sample = next((d for t, d in DRAFTS.items()
                   if (ROOT / "samples" / t).read_text(encoding="utf-8").strip() == transcript), None)
    if not sample:
        print(json.dumps({"type": "result", "is_error": True, "result": "(다시 보기) 이 녹취록에는 저장해 둔 초안이 없다"},
                         ensure_ascii=False))
        return 1
    if isinstance(sample, tuple):
        col = json.loads((req / "collected.json").read_text(encoding="utf-8"))
        sample = sample[1] if col.get("previous") else sample[0]
    delay = float(os.environ.get("REPLAY_DELAY", "2"))
    draft = req / "draft.json"
    active = False
    for _ in range(5):
        time.sleep(delay)                                   # drafter 가 쓰는 동안
        hook("guard", {"tool_name": "Write", "tool_input": {"file_path": str(draft)}}, rid)
        shutil.copyfile(ROOT / "samples" / sample, draft)
        hook("run_review", {"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": str(draft)},
                            "tool_response": {"success": True}}, rid)
        time.sleep(delay / 2)
        out = hook("next_step", {"hook_event_name": "Stop", "stop_hook_active": active}, rid)
        if '"decision": "block"' not in out:
            break
        active = True
    print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0,
                      "result": f"(다시 보기) 저장해 둔 초안 {sample} 로 흐름을 끝까지 따라갔다"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
