"""M4 지난 할 일 대조 — 지난 회의록의 열린 할 일이 하나도 빠지지 않고 이번 회의와 맞춰졌나.

지난 회의록은 수집(scripts/collect.py)이 같은 회의 폴더에서 찾아 collected.json 의 previous 에 넣는다.
초안의 carryover 는 지난 할 일 하나에 한 줄씩, 같은 순서로 쓴다.

  - 할 일 이름은 지난 회의록 그대로 — 바꿔 쓰거나 빼면 거부한다(줄 수와 글자를 대 본다)
  - 상태는 완료 · 이월 · 언급 없음 가운데 하나
  - 완료·이월이면 근거 발화가 녹취에 글자 그대로 있어야 한다(M2 와 같은 방법)
  - 언급 없음이면 근거를 비운다 — 거부하지 않고 회의록에 "확인 필요" 로 남긴다(notes)

지난 회의록이 없으면 carryover 는 비어 있어야 한다. 근거 문장이 "완료" 를 뜻하는지는 보지 않는다 — 뜻은 사람이 본다.
"""

from checks.m2_evidence import _n

STATUSES = ("완료", "이월", "언급 없음")


def check(draft: dict, previous: list[dict], said: str) -> list[str]:
    carry = draft.get("carryover") or []
    if not previous:
        return [f"carryover has {len(carry)} items but there are no previous minutes"] if carry else []
    probs = []
    if len(carry) != len(previous):
        probs.append(f"carryover has {len(carry)} items, previous minutes have {len(previous)}")
    hay = _n(said)
    for i, p in enumerate(previous):
        if i >= len(carry):
            probs.append(f"carryover[{i}] missing for previous action '{p.get('task', '')}'")
            continue
        c = carry[i] if isinstance(carry[i], dict) else {}
        if _n(c.get("task") or "") != _n(p.get("task") or ""):
            probs.append(f"carryover[{i}] task does not match previous action '{p.get('task', '')}'")
        status = (c.get("status") or "").strip()
        ev = _n(c.get("evidence") or "")
        if status not in STATUSES:
            probs.append(f"carryover[{i}] status '{status}' is not one of {' · '.join(STATUSES)}")
        elif status == "언급 없음":
            if ev:
                probs.append(f"carryover[{i}] is '언급 없음' but has evidence")
        elif not ev:
            probs.append(f"carryover[{i}] evidence missing")
        elif ev not in hay:
            probs.append(f"carryover[{i}] evidence not found in transcript")
    return probs


def notes(draft: dict, previous: list[dict]) -> list[str]:
    """거부는 아니지만 사람이 볼 것 — 이번 회의에서 아무도 말하지 않은 지난 할 일."""
    return [f"carryover[{i}] '{c.get('task', '')}' not mentioned — 확인 필요"
            for i, c in enumerate((draft.get("carryover") or [])[:len(previous or [])])
            if isinstance(c, dict) and (c.get("status") or "").strip() == "언급 없음"]
