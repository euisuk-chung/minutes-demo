"""시연 화면을 모델 없이 시험한다 — 이 폴더를 임시 폴더에 복사해 `app.py --replay` 를 켜고 브라우저 대신 HTTP 로 올린다.

    uv run python tests/test_app.py

장면 셋: 녹취록 A → 회의록(done) · 녹취록 B(담당자 빠짐) → 사람에게(needs_human, 작성 3/3) ·
같은 A 를 다시 → 폴더 감시 화면에 `skip:` 한 줄. 끝에 PATH 앞의 가짜 claude 가 불리지 않았는지 본다.
전부 기대대로면 0, 하나라도 다르면 1.

보장하지 않는 것: 브라우저 화면이 제대로 그려진다는 것(HTML 은 받아지는지만 본다), 실제 실행 모드의 흐름.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
fails = 0


def ok(cond: bool, what: str) -> None:
    global fails
    print(f"{'OK  ' if cond else 'FAIL'} {what}")
    fails += 0 if cond else 1


def call(base: str, path: str, data: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(base + path, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        body = r.read()
        return json.loads(body) if r.headers.get_content_type() == "application/json" else body.decode("utf-8")


def wait(base: str, pred, what: str, limit: float = 60):
    end = time.time() + limit
    s = None
    while time.time() < end:
        s = call(base, "/api/state")
        hit = pred(s)
        if hit:
            return hit
        time.sleep(0.3)
    ok(False, f"{what} — {limit:.0f}초 안에 안 됨")
    return None


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="minutes-app-") as t:
        root = Path(t) / "minutes"
        shutil.copytree(SRC, root, ignore=shutil.ignore_patterns("requests", "minutes", "inbox", "__pycache__", "watch.log"),
                        symlinks=True)
        fakebin = Path(t) / "fakebin"
        fakebin.mkdir()
        calls = Path(t) / "claude-calls.log"
        (fakebin / "claude").write_text(f'#!/bin/sh\necho "$*" >> "{calls}"\nexit 97\n', encoding="utf-8")
        (fakebin / "claude").chmod(0o755)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = dict(os.environ, PATH=f"{fakebin}{os.pathsep}{os.environ.get('PATH', '')}", REPLAY_DELAY="0.2", PYTHONUTF8="1")
        env.pop("CLAUDE_BIN", None)
        app = subprocess.Popen([sys.executable, "app.py", "--replay", "--port", str(port), "--interval", "1"], cwd=root, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        base = f"http://127.0.0.1:{port}"
        try:
            up = wait(base, lambda s: s, "서버가 켜짐", 15) if _up(base) else None
            ok(bool(up) and up["mode"] == "replay" and up["watching"], "app.py --replay → 다시 보기 · 폴더 감시 켜짐")
            ok("<title>회의록 자동화 시연</title>" in call(base, "/"), "GET / → 시연 화면 HTML")

            saved = call(base, "/api/sample/a", b"")["saved"]
            ok(saved == "transcript-a.txt", f"녹취록 A 올리기 → inbox/{saved}")
            r = wait(base, lambda s: next((x for x in s["requests"] if x["terminal"]), None), "녹취록 A 가 끝남")
            if r:
                ok(r["terminal"] == "done" and r["minutes"] and r["minutes"].startswith("# 회의록"), "A → done, 회의록 내용이 화면 상태에 있다")
                ok(r["report"] and all(v["pass"] for v in r["report"].values()), "A → 검사 보고 M1·M2·M3 통과")
                ok([e["event"] for e in r["events"]][:2] == ["triggered", "step"], "지나온 길이 시작 계기부터 쌓인다")

            text = (root / "samples" / "transcript-b.txt").read_bytes()
            saved = call(base, "/api/upload", text, {"X-Filename": "%EB%8B%B4%EB%8B%B9%EC%9E%90%EC%97%86%EC%9D%8C.txt"})["saved"]
            ok(saved == "담당자없음.txt", f"파일 올리기(한글 이름) → inbox/{saved}")
            r = wait(base, lambda s: next((x for x in s["requests"] if x["source"] == saved and x["terminal"]), None),
                     "녹취록 B(담당자 빠짐)가 끝남", 90)
            if r:
                ok(r["terminal"] == "needs_human" and r["visits"].get("draft") == 3 and not r["minutes"],
                   "담당자 없음 → needs_human, 작성 3/3, 회의록 없음")
                ok(r["review"] and not r["review"]["M1"]["pass"] and "actions[0] owner missing" in r["review"]["M1"]["problems"],
                   "검수 M1 거부 이유가 화면 상태에 있다")

            call(base, "/api/sample/a", b"")
            hit = wait(base, lambda s: any(l.startswith("skip: already processed") for l in s["log"]), "같은 A 를 다시 → skip", 30)
            ok(bool(hit), "같은 녹취록을 다시 → 폴더 감시 화면에 skip 한 줄, 요청은 늘지 않는다")
            ok(len(call(base, "/api/state")["requests"]) == 2, "요청은 둘 그대로")

            call(base, "/api/reset", b"")
            saved = call(base, "/api/sample/a-carry", b"")["saved"]
            ok(saved == "transcript-a.txt" and list((root / "minutes" / "기술-블로그-주간-회의").glob("2026-09-14_*.minutes.json")),
               f"회의록 A' 를 회의 폴더에 놓고 녹취록 A → inbox/{saved}")
            r = wait(base, lambda s: next((x for x in s["requests"] if x["source"] == "transcript-a.txt" and x["terminal"]), None),
                     "지난 회의록이 있는 A 가 끝남", 90)
            if r:
                ok(r["terminal"] == "done" and r["minutes_path"].startswith("minutes/기술-블로그-주간-회의/2026-09-21_"),
                   f"지난 회의록이 있는 A → done, 회의록은 회의 폴더에 ({r['minutes_path']})")
                ok(r["context"]["previous"]["date"] == "2026-09-14" and "정하늘" in r["context"]["roster"],
                   "화면 상태에 지난 회의록(09-14)과 명단")
                ok(list(r["report"]) == ["M1", "M2", "M3", "M4"] and all(v["pass"] for v in r["report"].values())
                   and len(r["report"]["M4"]["notes"]) == 2, "검사 넷 통과, 확인 필요 두 줄")
                ok("정하늘 (발언 없음)" in r["minutes"] and "**언급 없음 — 확인 필요**" in r["minutes"], "회의록에 발언 없음·확인 필요")

            call(base, "/api/reset", b"")
            s = call(base, "/api/state")
            ok(not s["requests"] and not s["inbox"] and s["watching"], "처음부터 → requests·inbox 빔, 폴더 감시는 그대로")
        finally:
            os.killpg(app.pid, 15)
            app.wait(timeout=10)
        n = len(calls.read_text(encoding="utf-8").splitlines()) if calls.exists() else 0
        ok(n == 0, f"가짜 claude 호출 {n}회 (다시 보기는 진짜 claude 를 부르지 않는다)")
    print("\n시연 화면 시험: " + ("통과" if not fails else f"{fails}건 다름"))
    return 1 if fails else 0


def _up(base: str) -> bool:
    end = time.time() + 15
    while time.time() < end:
        try:
            call(base, "/api/state")
            return True
        except OSError:
            time.sleep(0.2)
    return False


if __name__ == "__main__":
    sys.exit(main())
