"""전달 — 검수를 통과한 초안으로 회의록 파일과 검사 보고를 만든다. 모델을 부르지 않는다.

    uv run python scripts/deliver.py <요청 id>

회의마다 폴더가 따로 있다 — 녹취록 머리의 `회의:` 이름으로 minutes/<회의 이름>/ (없으면 minutes/미분류/).
파일 이름은 회의 날짜로 시작해서, 다음 회의의 수집이 "이번 날짜보다 앞선 가장 늦은 회의록" 을 이름 순서만으로 찾는다.

  <날짜>_<id>.md             사람이 읽는 회의록
  <날짜>_<id>.report.json    검사 보고
  <날짜>_<id>.minutes.json   다음 회의가 읽는 기록 — 열린 할 일(open_actions)이 들어 있다

열린 할 일 = 이번 회의의 할 일 + 이번에 아무도 말하지 않은 지난 할 일(언급 없음).
이월한 지난 할 일은 이번 회의의 할 일로 다시 적혀 있어야 이어진다(작성 담당에게 그렇게 맡긴다).
같은 요청이면 덮어쓴다(두 번 해도 같다).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    rid = sys.argv[1]
    d = ROOT / "requests" / rid
    try:
        m = json.loads((d / "draft.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("deliver: 초안을 읽을 수 없다")
        return 64
    try:
        col = json.loads((d / "collected.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        col = {}
    out = ROOT / "minutes" / (col.get("project") or "미분류")
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{col.get('date') or '0000-00-00'}_{rid}"
    speakers = set(col.get("speakers") or [])
    prev = col.get("previous") or {}
    carry = m.get("carryover") or []

    md = [f"# 회의록 — {rid}", "", "## 참석자", ""]
    md += [f"- {a}" + ("" if not col.get("roster") or a in speakers else " (발언 없음)") for a in m["attendees"]]
    md += ["", "## 안건", ""] + [f"- {a}" for a in m["agenda"]]
    md += ["", "## 결정사항", ""] + [f"- {x['text']}  \n  근거: \"{x['evidence']}\"" for x in m["decisions"]]
    pending = m.get("pending") or []
    md += ["", "## 미결사항", ""] + ([f"- {x['text']}  \n  근거: \"{x['evidence']}\"" for x in pending] or ["- 없음"])
    md += ["", "## 할 일", "", "| 할 일 | 담당 | 기한 |", "|---|---|---|"]
    md += [f"| {a['task']} | {a.get('owner', '')} | {a.get('due', '')} |" for a in m["actions"]]
    if prev:
        md += ["", "## 지난 할 일", "", f"지난 회의록 {prev.get('date', '')} 의 열린 할 일과 맞춰 본 결과입니다.", "",
               "| 지난 할 일 | 담당 | 이번 회의에서 | 근거 |", "|---|---|---|---|"]
        for c in carry:
            st = "**언급 없음 — 확인 필요**" if c.get("status") == "언급 없음" else c.get("status", "")
            ev = f'"{c["evidence"]}"' if c.get("evidence") else ""
            md.append(f"| {c.get('task', '')} | {c.get('owner', '')} | {st} | {ev} |")
    (out / f"{stem}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    shutil.copyfile(d / "review.json", out / f"{stem}.report.json")

    still_open = [{"task": c.get("task", ""), "owner": c.get("owner", ""), "due": c.get("due", "")}
                  for c in carry if c.get("status") == "언급 없음"]
    record = {"request": rid, "meeting": col.get("meeting", ""), "date": col.get("date", ""),
              "attendees": m["attendees"], "agenda": m["agenda"], "decisions": m["decisions"], "pending": pending,
              "actions": m["actions"], "carryover": carry, "previous": prev.get("file"),
              "open_actions": m["actions"] + still_open}
    (out / f"{stem}.minutes.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    rep = json.loads((d / "review.json").read_text(encoding="utf-8"))
    rel = (out / f"{stem}.md").relative_to(ROOT).as_posix()
    print(f"deliver: {rel} — " + " · ".join(f"{k} {'pass' if v['pass'] else 'rejected'}" for k, v in rep.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
