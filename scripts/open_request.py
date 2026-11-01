"""요청 열기·마무리 — 모델을 부르지 않는다.

    uv run python scripts/open_request.py <녹취록 경로>     요청을 연다(같은 녹취록이면 건너뜀)
    uv run python scripts/open_request.py <요청 id>          이미 연 요청의 지금 안내를 다시 보인다
    uv run python scripts/open_request.py --finish <요청 id> claude 가 끝난 뒤 흐름을 마무리하고 지나온 길을 찍는다

요청 id 는 녹취록 **내용**의 지문(sha256 앞 12자리)으로 짓는다 — inbox-<지문>.
파일 이름을 바꿔 넣어도 내용이 같으면 같은 요청이라, 요청 폴더를 먼저 만드는 쪽(mkdir) 하나만 이긴다.

끝날 때 신호
  열기     0 작성이 필요하다(claude 를 부른다) · 10 이미 처리한 녹취록(건너뜀) · 64 녹취록을 읽을 수 없다
  마무리   0 done · 3 needs_human · 1 failed
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude" / "hooks"))
from _state import REQ, advance, event, load, rdir, save, utf8  # noqa: E402

SKIP = 10


def open_new(path: Path) -> int:
    try:
        data = path.read_bytes()
    except OSError:
        print(f"녹취록을 읽을 수 없다: {path}")
        return 64
    fp = hashlib.sha256(data).hexdigest()[:12]
    rid = f"inbox-{fp}"
    REQ.mkdir(exist_ok=True)
    try:
        rdir(rid).mkdir()          # 먼저 만드는 쪽 하나만 이긴다
    except FileExistsError:
        print(f"skip: already processed inbox:{fp}")
        return SKIP
    shutil.copyfile(path, rdir(rid) / "transcript.txt")
    trigger = f"event:inbox:{fp}:created"
    st = {"id": rid, "trigger": trigger, "source": str(path.name), "at": "collect",
          "visits": {}, "history": [], "tool_calls": 0, "terminal": None, "reason": ""}
    save(rid, st)
    event(rid, "triggered", trigger=trigger)
    (REQ / ".current").write_text(rid, encoding="utf-8")
    print(trigger)
    r = advance(rid, "open")
    print(f"REQUEST_ID={rid}")
    return 0 if r["need"] else finish_code(load(rid))


def reopen(rid: str) -> int:
    if not load(rid):
        print(f"그런 요청이 없다: {rid}")
        return 64
    (REQ / ".current").write_text(rid, encoding="utf-8")
    r = advance(rid, "open")
    print(r["message"])
    return 0 if r["need"] else finish_code(load(rid))


def finish_code(st: dict) -> int:
    return {"done": 0, "needs_human": 3}.get(st.get("terminal"), 1)


def path_lines(st: dict) -> list[str]:
    """지나온 길을 화면 줄로. 검수가 거부한 뒤 다시 작성한 것은 retry n/m 으로 적는다."""
    hist = st.get("history", [])
    out, first, retry = [], [], 0
    cap = 3
    i = 0
    while i < len(hist) and not (hist[i]["step"] == "review" and hist[i]["signal"] != 0):
        first.append(hist[i]["step"])
        i += 1
    if i < len(hist):  # 첫 거부
        first.append("review")
        out.append(" → ".join(first))
        out.append(f"review: {hist[i]['note'].replace('review: ', '')}")
        i += 1
        while i < len(hist):
            h = hist[i]
            if h["step"] == "draft":
                retry += 1
                nxt = hist[i + 1] if i + 1 < len(hist) else None
                tail = ""
                if nxt and nxt["step"] == "review":
                    tail = " → review: " + ("pass" if nxt["signal"] == 0 else nxt["note"].replace("review: ", ""))
                    i += 1
                out.append(f"draft (retry {retry}/{cap - 1}){tail}")
            else:
                out.append(h["step"])
            i += 1
    else:
        out.append(" → ".join(first + [st.get("terminal") or "?"]))
        return out
    out.append(f"done: {st.get('terminal')}" + (f" — {st['reason']}" if st.get("reason") else ""))
    return out


def finish(rid: str) -> int:
    st = load(rid)
    if not st:
        print(f"그런 요청이 없다: {rid}")
        return 1
    if not st.get("terminal"):
        advance(rid, "finish")
        st = load(rid)
    for line in path_lines(st):
        print(line)
    cur = REQ / ".current"
    if cur.is_file() and cur.read_text(encoding="utf-8").strip() == rid:
        cur.unlink()
    return finish_code(st)


def main() -> int:
    utf8()
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 64
    if a[0] == "--finish" and len(a) == 2:
        return finish(a[1])
    p = Path(a[0])
    if p.is_file():
        return open_new(p)
    return reopen(a[0])


if __name__ == "__main__":
    sys.exit(main())
