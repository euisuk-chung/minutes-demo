"""M1 할 일 완결 — 할 일마다 담당자(owner)가 참석자 중 한 명이고 기한(due)이 있나.

되돌아온 초안이면 앞에서 거부된 초안(draft.rejected.json)과 대 본다. 할 일이 줄었으면 거부한다
— 담당자를 못 채운 할 일을 목록에서 빼서 통과하는 길을 막는다(실제 실행에서 모델이 이렇게 했다).
"""


def check(draft: dict, rejected: dict | None = None) -> list[str]:
    people = set(draft.get("attendees", []))
    probs = []
    if rejected is not None:
        before, after = len(rejected.get("actions", [])), len(draft.get("actions", []))
        if after < before:
            probs.append(f"actions dropped {before} → {after}")
    for i, a in enumerate(draft.get("actions", [])):
        owner = (a.get("owner") or "").strip()
        if not owner:
            probs.append(f"actions[{i}] owner missing")
        elif owner not in people:
            probs.append(f"actions[{i}] owner '{owner}' is not an attendee")
        if not (a.get("due") or "").strip():
            probs.append(f"actions[{i}] due missing")
    return probs
