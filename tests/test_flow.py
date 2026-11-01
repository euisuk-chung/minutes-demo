"""모델 없이 흐름 전체를 시험한다 — 고정 입력 판정.

    uv run python tests/test_flow.py

이 폴더를 임시 폴더에 복사한 뒤, Claude Code 가 하는 일(차단 장치에 JSON 넣기)을 이 시험이 대신 하고,
모델이 할 일(초안 쓰기)은 samples/ 의 저장된 초안을 쓰는 것으로 대신한다.
전부 기대대로면 0, 하나라도 다르면 1.

보장하지 않는 것: 실제 Claude Code 가 차단 장치를 이 순서·이 JSON 모양으로 부른다는 것,
실제 모델이 drafter 에게 맡기고 거부 이유대로 다시 쓴다는 것 — 그것은 scripts/request.sh 의 실제 실행으로 본다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
fails = 0


def ok(cond: bool, what: str) -> None:
    global fails
    print(f"{'OK  ' if cond else 'FAIL'} {what}")
    fails += 0 if cond else 1


def run(root: Path, argv: list[str], stdin: dict | str | None = None, env: dict | None = None) -> tuple[int, str]:
    e = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), PYTHONUTF8="1")
    e.pop("REQUEST_ID", None)
    e.update(env or {})
    data = stdin if isinstance(stdin, str) or stdin is None else json.dumps(stdin, ensure_ascii=False)
    p = subprocess.run([sys.executable if a == "python3" else a for a in argv], cwd=root, input=data or "",
                       capture_output=True, text=True, encoding="utf-8", env=e)
    return p.returncode, p.stdout + p.stderr


def hook(root: Path, name: str, payload: dict) -> tuple[int, str]:
    return run(root, ["python3", f".claude/hooks/{name}.py"], payload)


def write_draft(root: Path, rid: str, sample: str) -> dict:
    dst = root / "requests" / rid / "draft.json"
    time.sleep(0.01)
    shutil.copyfile(root / "samples" / sample, dst)
    return {"hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": str(dst)}, "tool_response": {"success": True}}


def rid_of(out: str) -> str:
    return next(l.split("=", 1)[1] for l in out.splitlines() if l.startswith("REQUEST_ID="))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="minutes-") as t:
        root = Path(t) / "minutes"
        shutil.copytree(SRC, root, ignore=shutil.ignore_patterns("requests", "minutes", "inbox", "__pycache__"))

        # ── 장면 2·3: 녹취록 A — 검수 통과, 회의록과 보고
        code, out = run(root, ["python3", "scripts/open_request.py", "samples/transcript-a.txt"])
        ok(code == 0 and out.startswith("event:inbox:"), f"요청 열기 → 0, 첫 줄 시작 계기 ({out.splitlines()[0]})")
        rid = rid_of(out)
        st = json.loads((root / "requests" / rid / "state.json").read_text(encoding="utf-8"))
        ok(st["at"] == "draft" and st["visits"] == {"draft": 1}, "수집을 끝내고 작성 1/3 을 맡겼다")

        c, o = hook(root, "guard", {"tool_name": "Write", "tool_input": {"file_path": str(root / "requests" / rid / "draft.json")}})
        ok(c == 0, "guard: 초안 쓰기는 허용 → 0")
        c, o = hook(root, "guard", {"tool_name": "Write", "tool_input": {"file_path": str(root / "requests" / rid / "state.json")}})
        ok(c == 2, "guard: state.json 쓰기는 막음 → 2")
        c, o = hook(root, "guard", {"tool_name": "Bash", "tool_input": {"command": "curl https://example.com"}})
        ok(c == 2, "guard: curl 은 막음 → 2")
        c, o = hook(root, "guard", {"tool_name": "ScheduleWakeup", "tool_input": {}})
        ok(c == 2, "guard: 허용 목록 밖 도구는 막음 → 2")
        c, o = hook(root, "guard", {"tool_name": "Agent", "tool_input": {"subagent_type": "drafter", "run_in_background": True}})
        ok(c == 2, "guard: 하위 에이전트를 백그라운드로 띄우면 막음 → 2")
        agent = {"tool_name": "Agent", "tool_input": {"subagent_type": "drafter"}}
        guard = ["python3", ".claude/hooks/guard.py"]
        c, o = run(root, guard, agent, env={"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": ""})
        ok(c == 2, "guard: run_in_background 를 비운 부름(기본이 뒤에 띄우기)은 끄기 값이 없으면 막음 → 2")
        c, o = run(root, guard, {**agent, "tool_input": {**agent["tool_input"], "run_in_background": False}},
                   env={"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": ""})
        ok(c == 0, "guard: run_in_background 를 false 로 적은 부름은 들임 → 0")
        c, o = run(root, guard, agent, env={"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"})
        ok(c == 0, "guard: 끄기 값(settings.json 의 env)이 있으면 비운 부름도 들임 → 0")
        c, o = hook(root, "protect_sources", {"tool_name": "Bash", "tool_input": {"command": "echo x > inbox/a.txt"}})
        ok(c == 2, "protect_sources: Bash 로 원문 쓰기 막음 → 2")
        c, o = hook(root, "protect_sources", "not json")
        ok(c == 0, "protect_sources: 깨진 입력은 조용히 통과 → 0 (7차시에서 보이는 길)")

        c, o = hook(root, "run_review", write_draft(root, rid, "draft-a.json"))
        ok(c == 0 and '"decision"' not in o and "끝: done" in o, "run_review: 검수 통과 → 전달 → done")
        c, o = hook(root, "next_step", {"hook_event_name": "Stop", "stop_hook_active": False})
        ok(c == 0 and o.strip() == "", "next_step: 끝났으니 막지 않음")
        c, o = run(root, ["python3", "scripts/open_request.py", "--finish", rid])
        ok(c == 0 and "collect → draft → review → deliver → done" in o, f"마무리 → 0, 지나온 길 ({o.strip()})")
        meet = root / "minutes" / "기술-블로그-주간-회의"
        rep = json.loads((meet / f"2026-09-21_{rid}.report.json").read_text(encoding="utf-8"))
        ok(list(rep) == ["M1", "M2", "M3"] and all(v["pass"] for v in rep.values()) and (meet / f"2026-09-21_{rid}.md").is_file(),
           "회의 폴더 minutes/기술-블로그-주간-회의/ 에 <날짜>_<id>.md 와 report.json — M1·M2·M3 pass, 지난 회의록이 없으니 M4 없음")

        # ── 장면 4: 같은 녹취록을 이름만 바꿔 다시
        shutil.copyfile(root / "samples" / "transcript-a.txt", root / "samples" / "copy-of-a.txt")
        c, o = run(root, ["python3", "scripts/open_request.py", "samples/copy-of-a.txt"])
        ok(c == 10 and o.startswith("skip: already processed inbox:"), f"같은 내용 → 건너뜀 10 ({o.strip()})")

        # ── 장면 5: 녹취록 B(결제 서비스 개발 회의, 담당자 빠짐) — 세 번 작성해도 거부, 사람에게
        code, out = run(root, ["python3", "scripts/open_request.py", "samples/transcript-b.txt"])
        rid2 = rid_of(out)
        c, o = hook(root, "run_review", write_draft(root, rid2, "draft-b.json"))
        ok('"decision"' not in o, "run_review: 검수만 하고 막지 않는다")
        c, o = hook(root, "next_step", {"hook_event_name": "Stop", "stop_hook_active": False})
        ok('"decision": "block"' in o and "actions[0] owner missing" in o and "작성 2/3" in o,
           "next_step: M1 거부 → 작성 2/3 을 이유와 함께 되돌림")
        c, o = hook(root, "next_step", {"hook_event_name": "Stop", "stop_hook_active": True})
        ok('"decision": "block"' in o and "작성 2/3" in o, "next_step: 새 초안 없이 멈추려 하면 같은 안내로 막음(횟수 그대로)")
        hook(root, "run_review", write_draft(root, rid2, "draft-b.json"))
        c, o = hook(root, "next_step", {"hook_event_name": "Stop", "stop_hook_active": False})
        ok("작성 3/3" in o, "같은 내용을 다시 써도 한 번의 작성으로 센다 → 작성 3/3")
        hook(root, "run_review", write_draft(root, rid2, "draft-b.json"))
        c, o = hook(root, "next_step", {"hook_event_name": "Stop", "stop_hook_active": False})
        st2 = json.loads((root / "requests" / rid2 / "state.json").read_text(encoding="utf-8"))
        ok('"decision"' not in o and st2.get("terminal") == "needs_human", "세 번째도 거부 → needs_human, 더 막지 않음")
        c, o = run(root, ["python3", "scripts/open_request.py", "--finish", rid2])
        lines = o.strip().splitlines()
        ok(c == 3, f"마무리 → 3 (사람에게)")
        ok(lines[:1] == ["collect → draft → review"] and "review: M1 rejected — actions[0] owner missing" in lines
           and any(l.startswith("draft (retry 1/2)") for l in lines) and any(l.startswith("draft (retry 2/2)") for l in lines)
           and lines[-1].startswith("done: needs_human — 'draft' 를 3번 했는데도 안 됐다"), "지나온 길:\n    " + "\n    ".join(lines))
        ok(not list((root / "minutes").glob(f"*/*_{rid2}.md")), "사람에게 간 요청은 회의록 파일이 없다")

        # ── 걸린 할 일을 빼서 통과하려는 초안 — 실제 실행에서 모델이 이렇게 했다
        src = root / "samples" / "transcript-b.txt"
        (root / "samples" / "v2-again.txt").write_text(src.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        code, out = run(root, ["python3", "scripts/open_request.py", "samples/v2-again.txt"])
        rid3 = rid_of(out)
        hook(root, "run_review", write_draft(root, rid3, "draft-b.json"))
        hook(root, "next_step", {"hook_event_name": "Stop", "stop_hook_active": False})
        d = json.loads((root / "samples" / "draft-b.json").read_text(encoding="utf-8"))
        d["actions"] = [a for a in d["actions"] if a["owner"]]
        (root / "samples" / "draft-dropped.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        hook(root, "run_review", write_draft(root, rid3, "draft-dropped.json"))
        c, o = hook(root, "next_step", {"hook_event_name": "Stop", "stop_hook_active": False})
        ok("actions dropped 5 → 4" in o and '"decision": "block"' in o, "M1: 되돌아온 초안이 할 일을 빼면 거부(actions dropped 5 → 4)")

        # ── 장면 6: 처음부터(회의 폴더와 A 의 요청을 비움) → 회의 폴더에 지난주(09-14) 회의록 A' 를 놓고 → 같은 A
        shutil.rmtree(root / "minutes")
        shutil.rmtree(root / "requests" / rid)
        meet.mkdir(parents=True)
        for f in sorted((root / "samples" / "last-week").iterdir()):
            shutil.copyfile(f, meet / f.name)
        rec = json.loads(next(meet.glob("2026-09-14_*.minutes.json")).read_text(encoding="utf-8"))
        ok(len(rec["open_actions"]) == 3, "견본 회의록 A'(09-14) 에 열린 할 일 3")

        code, out = run(root, ["python3", "scripts/open_request.py", "samples/transcript-a.txt"])
        rr = rid_of(out)
        ok(rr == rid, "같은 A 라 요청 id 도 장면 2 와 같다(처음부터로 비웠으니 건너뛰지 않는다)")
        col = json.loads((root / "requests" / rr / "collected.json").read_text(encoding="utf-8"))
        ok(col["previous"] and col["previous"]["date"] == "2026-09-14" and len(col["previous"]["actions"]) == 3
           and "정하늘" in col["roster"] and "정하늘" not in col["speakers"],
           "수집: 같은 회의 폴더에서 09-14 회의록의 열린 할 일 3 을 꺼냄, 정하늘은 명단에만")

        # 거부되는 초안 셋 — 흐름(작성 세 번 상한) 밖에서 검수만 따로 불러 본다
        d = json.loads((root / "samples" / "draft-a-with-prev.json").read_text(encoding="utf-8"))

        def review_only(draft: dict) -> dict:
            (root / "requests" / rr / "draft.json").write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
            run(root, ["python3", "review.py", rr])
            return json.loads((root / "requests" / rr / "review.json").read_text(encoding="utf-8"))

        rv = review_only(dict(d, attendees=[a for a in d["attendees"] if a != "정하늘"]))
        ok(rv["M3"]["problems"] == ["roster member '정하늘' missing from attendees"],
           f"M3: 명단에 있는데 참석자에서 빠지면 거부 ({rv['M3']['problems']})")
        rv = review_only(dict(d, carryover=d["carryover"][:2]))
        ok(not rv["M4"]["pass"] and any("previous minutes have 3" in x for x in rv["M4"]["problems"]),
           f"M4: 지난 할 일을 빼면 거부 ({rv['M4']['problems'][:1]})")
        rv = review_only(dict(d, pending=[{"text": "영상 제작은 다음 분기로", "evidence": "영상은 다음 분기에 꼭 만듭시다."}]))
        ok(rv["M2"]["problems"] == ["pending[0] evidence not found in transcript"],
           f"M2: 녹취에 없는 미결사항 근거는 거부 ({rv['M2']['problems']})")
        bad = json.loads(json.dumps(d))
        bad["carryover"][2] = dict(bad["carryover"][2], status="완료", evidence="구독 버튼은 달았어요.")   # 녹취에 없는 말
        rv = review_only(bad)
        ok(rv["M4"]["problems"] == ["carryover[2] evidence not found in transcript"],
           f"M4: 녹취에 없는 '완료' 근거는 거부 ({rv['M4']['problems']})")
        (root / "requests" / rr / "draft.json").unlink()

        c, o = hook(root, "run_review", write_draft(root, rr, "draft-a-with-prev.json"))
        ok("끝: done" in o, "제대로 쓴 초안 → done (언급 없음은 거부가 아니다)")
        rv = json.loads((meet / f"2026-09-21_{rr}.report.json").read_text(encoding="utf-8"))
        ok(list(rv) == ["M1", "M2", "M3", "M4"] and all(v["pass"] for v in rv.values())
           and rv["M4"]["notes"] == ["carryover[0] '이번 주 글 발행' not mentioned — 확인 필요",
                                     "carryover[2] '글 위쪽에 구독 버튼 추가' not mentioned — 확인 필요"],
           "검사 넷 통과, M4 notes 에 언급 없는 지난 할 일 둘")
        md = (meet / f"2026-09-21_{rr}.md").read_text(encoding="utf-8")
        ok("- 정하늘 (발언 없음)" in md and "## 지난 할 일" in md and "**언급 없음 — 확인 필요**" in md
           and "| 태그 정리 | 박도윤 | 이월 |" in md, "회의록: 정하늘 (발언 없음), 지난 할 일 표에 이월·언급 없음")
        rec = json.loads((meet / f"2026-09-21_{rr}.minutes.json").read_text(encoding="utf-8"))
        ok([a["task"] for a in rec["open_actions"]][-2:] == ["이번 주 글 발행", "글 위쪽에 구독 버튼 추가"] and len(rec["open_actions"]) == 10,
           "다음 회의로 넘길 열린 할 일 = 이번 할 일 8 + 언급 없던 지난 할 일 2")

        # ── 상한: 도구 호출 21번째는 막는다
        stp = root / "requests" / rid2 / "state.json"
        st = json.loads(stp.read_text(encoding="utf-8"))
        st["terminal"] = None; st["tool_calls"] = 20
        stp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        c, o = run(root, ["python3", ".claude/hooks/guard.py"], {"tool_name": "Read", "tool_input": {}}, {"REQUEST_ID": rid2})
        ok(c == 2 and "상한" in o, "guard: 21번째 도구 호출 → 2")
    print("\n흐름 시험: " + ("통과" if not fails else f"{fails}건 다름"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
