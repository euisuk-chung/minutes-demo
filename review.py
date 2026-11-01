"""검수 — 초안이 녹취 원문과 맞는지 검사 셋(M1~M3)으로 본다. 모델을 부르지 않는다.

    uv run python review.py <요청 id>

  M1 할 일 완결   할 일마다 담당자가 참석자 중 한 명이고 기한이 있나(되돌아온 초안이면 할 일을 빼지 않았나)
  M2 결정사항·미결사항 근거  결정사항·미결사항마다 붙인 근거 문장이 녹취 원문에 그대로 있나(띄어쓰기 여러 칸은 한 칸으로)
  M3 참석자 실재  참석자 이름이 녹취나 명단에 나오나, 녹취의 발화자와 명단의 이름이 빠지지 않았나
  M4 지난 할 일   지난 회의록의 열린 할 일마다 완료·이월·언급 없음과 근거가 있나 — 지난 회의록이 있을 때만

모두 통과면 0, 하나라도 거부면 1, 초안이 형식을 어기면 2 로 끝난다.
결과는 requests/<id>/review.json 에 남고, 거부 이유는 화면 마지막 줄들에 찍힌다.
거부는 아니지만 사람이 볼 것(언급 없는 지난 할 일, 명단에 없는 발화자)은 검사마다 notes 에 남는다.
명단과 지난 회의록은 수집이 만든 collected.json 에서 읽는다.
모범 회의록(정답표) 없이 녹취 원문과만 대 본다 — 뜻이 맞는지는 여전히 사람이 읽어야 한다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
from _state import utf8  # noqa: E402
from checks import m1_actions, m2_evidence, m3_attendees, m4_carryover  # noqa: E402

LINE = re.compile(r"^\[(\d\d:\d\d:\d\d)\]\s*([^:]+):\s*(.*)$")


def parse(transcript: str) -> tuple[list[str], str]:
    speakers, said = [], []
    for line in transcript.splitlines():
        m = LINE.match(line.strip())
        if m:
            if m.group(2).strip() not in speakers:
                speakers.append(m.group(2).strip())
            said.append(m.group(3))
    return speakers, " ".join(said)


def shape_ok(d: object) -> str | None:
    if not isinstance(d, dict):
        return "초안이 JSON 객체가 아니다"
    for k, t in (("attendees", list), ("agenda", list), ("decisions", list), ("actions", list)):
        if not isinstance(d.get(k), t):
            return f"'{k}' 칸이 없거나 목록이 아니다"
    for i, a in enumerate(d["actions"]):
        if not isinstance(a, dict) or "task" not in a:
            return f"actions[{i}] 에 task 가 없다"
    for i, x in enumerate(d["decisions"]):
        if not isinstance(x, dict) or "text" not in x or "evidence" not in x:
            return f"decisions[{i}] 에 text·evidence 가 없다"
    carry = d.get("carryover", [])
    if not isinstance(carry, list) or not all(isinstance(c, dict) for c in carry):
        return "'carryover' 칸이 목록이 아니다"
    return None


def main() -> int:
    utf8()
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    rid = sys.argv[1]
    d = ROOT / "requests" / rid
    try:
        draft = json.loads((d / "draft.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"review: 형식 위반 — draft.json 을 읽을 수 없다 ({type(e).__name__})")
        return 2
    bad = shape_ok(draft)
    if bad:
        print(f"review: 형식 위반 — {bad}")
        return 2
    speakers, said = parse((d / "transcript.txt").read_text(encoding="utf-8"))
    rej = d / "draft.rejected.json"
    try:
        rejected = json.loads(rej.read_text(encoding="utf-8")) if rej.is_file() else None
    except ValueError:
        rejected = None
    try:
        col = json.loads((d / "collected.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        col = {}
    roster = col.get("roster") or []
    prev = (col.get("previous") or {}).get("actions") or []
    results = [("M1", m1_actions.check(draft, rejected), []), ("M2", m2_evidence.check(draft, said), []),
               ("M3", m3_attendees.check(draft, speakers, roster), m3_attendees.notes(draft, speakers, roster))]
    if prev or draft.get("carryover"):
        results.append(("M4", m4_carryover.check(draft, prev, said), m4_carryover.notes(draft, prev)))
    report = {name: {"pass": not probs, "problems": probs, "notes": notes} for name, probs, notes in results}
    (d / "review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for n, r in report.items():          # 사람이 볼 것을 먼저 — 마지막 줄은 늘 판정 요약이나 거부 이유다
        for note in r["notes"]:
            print(f"note: {n} — {note}")
    print(" · ".join(f"{n} {'pass' if r['pass'] else 'rejected'}" for n, r in report.items()))
    rejected = [(n, p) for n, probs, _ in results for p in probs]
    for n, p in rejected:
        print(f"review: {n} rejected — {p}")
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
