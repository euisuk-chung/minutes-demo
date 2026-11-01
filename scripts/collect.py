"""수집 — 녹취록에서 발화자와 발화 줄을 뽑고, 머리줄에 적힌 회의 정보와 지난 회의록을 모은다. 모델을 부르지 않는다.

    uv run python scripts/collect.py <요청 id>

녹취록 머리(첫 발화 줄 앞)에서 읽는 줄 — 셋 다 없어도 된다.
  회의: 기술 블로그 주간 회의        이 이름으로 회의 폴더 minutes/<회의 이름>/ 를 정한다
  일시: 2026-09-21(월) 10:00~10:25   날짜(YYYY-MM-DD)로 지난 회의록을 고른다
  참석: 김지현, 박도윤, 이서연        참석자 명단 — 말하지 않은 참석자도 검수(M3)가 알 수 있다

지난 회의록은 같은 회의 폴더에서 이번 날짜보다 앞선 것 가운데 가장 늦은 것이다.
회의 폴더 안의 파일 이름이 날짜로 시작해서(2026-09-14_<요청 id>.minutes.json) 이름 순서가 곧 날짜 순서다.
가장 늦은 회의록에 적힌 '열린 할 일'(open_actions)을 이번 요청으로 가져온다 — 대조(M4)는 이것만 본다.
열린 할 일에는 그 회의에서 언급 없던 더 앞의 할 일도 이어져 있어서, 하나만 읽어도 몇 주 전 할 일이 따라온다.

몇 개를 읽을지(LOOKBACK)는 바꿀 수 있는 값이다. 늘리면 그만큼 앞선 회의록의 경로가 previous.files 에 더 담겨
작성 담당이 맥락(지난 결정 같은 것)으로 읽을 수 있다. 읽는 양은 늘고, 대조 대상은 그대로 가장 늦은 회의록 하나다.

결과는 requests/<id>/collected.json. 녹취록이 없으면 64(실행 환경 문제)로 끝난다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINUTES = ROOT / "minutes"
LINE = re.compile(r"^\[(\d\d:\d\d:\d\d)\]\s*([^:]+):\s*(.*)$")
HEAD = re.compile(r"^(회의|일시|참석)\s*:\s*(.*)$")
DATE = re.compile(r"\d{4}-\d\d-\d\d")
LOOKBACK = 1      # 지난 회의록을 몇 개 넘길까 — 바꿀 수 있는 값(위 설명)


def folder_name(meeting: str) -> str:
    """회의 이름 → 폴더 이름. 글자·숫자는 두고 나머지는 '-' 로."""
    return re.sub(r"[^\w]+", "-", meeting, flags=re.UNICODE).strip("-")


def header(text: str) -> dict:
    head = {}
    for l in text.splitlines():
        l = l.strip()
        if LINE.match(l):
            break
        m = HEAD.match(l)
        if m:
            head[m.group(1)] = m.group(2).strip()
    date = DATE.search(head.get("일시", ""))
    roster = [n.strip() for n in re.split(r"[,，、·]", head.get("참석", "")) if n.strip()]
    meeting = head.get("회의", "")
    return {"meeting": meeting, "project": folder_name(meeting) if meeting else "",
            "date": date.group(0) if date else "", "roster": list(dict.fromkeys(roster))}


def previous(project: str, date: str) -> dict | None:
    """같은 회의 폴더에서 이번 날짜보다 앞선 회의록 — 가장 늦은 것의 열린 할 일과, 늦은 순서로 LOOKBACK 개의 경로."""
    if not project or not date:
        return None
    files = sorted(p for p in (MINUTES / project).glob("????-??-??_*.minutes.json") if p.name[:10] < date)
    if not files:
        return None
    p = files[-1]
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"file": p.relative_to(ROOT).as_posix(), "date": p.name[:10], "actions": m.get("open_actions", []),
            "files": [f.relative_to(ROOT).as_posix() for f in reversed(files[-LOOKBACK:])]}


def main() -> int:
    rid = sys.argv[1]
    d = ROOT / "requests" / rid
    try:
        text = (d / "transcript.txt").read_text(encoding="utf-8")
    except OSError:
        print("collect: 녹취록이 없다")
        return 64
    lines = [m.groups() for m in (LINE.match(l.strip()) for l in text.splitlines()) if m]
    speakers = list(dict.fromkeys(s.strip() for _, s, _ in lines))
    head = header(text)
    prev = previous(head["project"], head["date"])
    (d / "collected.json").write_text(json.dumps(
        {**head, "previous": prev, "speakers": speakers,
         "lines": [{"at": t, "speaker": s.strip(), "said": w} for t, s, w in lines]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    msg = f"collect: 발화 {len(lines)}줄, 발화자 {len(speakers)}명"
    if head["roster"]:
        msg += f", 명단 {len(head['roster'])}명"
    if prev:
        msg += f", 지난 회의록 {prev['date']}(열린 할 일 {len(prev['actions'])})"
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
