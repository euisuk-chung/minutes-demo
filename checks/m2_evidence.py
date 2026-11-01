"""M2 결정사항·미결사항 근거 — 결정사항과 미결사항마다 붙인 근거 문장(evidence)이 녹취 원문에 그대로 있나.

띄어쓰기 여러 칸은 한 칸으로 접어 대 본다. 글자를 바꿔 쓴 인용은 거부한다.
"""

import re

_WS = re.compile(r"\s+")


def _n(t: str) -> str:
    return _WS.sub(" ", t).strip()


def check(draft: dict, said: str) -> list[str]:
    hay = _n(said)
    probs = []
    for key in ("decisions", "pending"):
        for i, x in enumerate(draft.get(key, [])):
            ev = _n(x.get("evidence") or "")
            if not ev:
                probs.append(f"{key}[{i}] evidence missing")
            elif ev not in hay:
                probs.append(f"{key}[{i}] evidence not found in transcript")
    return probs
