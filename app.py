"""시연 화면 — 녹취록을 올리면 회의록과 검사 보고가 나오는 과정을 브라우저로 보여 준다.

    uv run python app.py              실제 실행: 올린 녹취록마다 Claude Code 를 부른다 (사용량이 든다)
    uv run python app.py --replay     다시 보기: 모델 없이 저장해 둔 초안으로 같은 흐름을 보여 준다 (리허설용)

브라우저에서 http://127.0.0.1:8000 을 연다. 이 서버는 흐름을 직접 돌리지 않는다.

- 켜질 때 `scripts/watch.sh` 를 뒤에서 켠다. 올린 파일은 `inbox/` 에 저장될 뿐이고, 요청을 시작하는 것은 늘
  폴더 감시다 — 사람이 시작을 누르지 않는다.
- 흐름은 지금처럼 `scripts/request.sh` → `claude -p "/handle-request …"` 안에서 차단 장치가 이끈다.
- 화면은 차단 장치가 요청 폴더에 남기는 기록(`state.json` · `events.jsonl` · `review.json`)과 `minutes/` 를 읽어 그린다.

127.0.0.1 에만 열린다. 누구나 올릴 수 있게 공개하면 올릴 때마다 이 컴퓨터의 Claude 사용량이 든다.
표준 라이브러리만 쓴다(차단 장치가 쓰는 PyYAML 은 pyproject.toml).
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
INBOX, REQUESTS, MINUTES = ROOT / "inbox", ROOT / "requests", ROOT / "minutes"
LOG = ROOT / "watch.log"
# 견본 버튼 하나가 넣는 녹취록들 — 여럿이면 이 순서로 넣는다(폴더 감시도 이름 순서로 집는다)
SAMPLES = {"a": ["transcript-a.txt"], "b": ["transcript-b.txt"], "a-carry": ["transcript-a.txt"]}
# 견본 버튼이 녹취록을 넣기 전에 회의 폴더에 놓는 회의록 — 지난주(09-14)에 이 흐름이 만들어 둔 회의록 A'
# (`samples/last-week/` 의 파일들. 녹취록이 아니라 이미 기록된 회의록이라 흐름을 다시 지나지 않는다)
SEEDS = {"a-carry": ("기술-블로그-주간-회의", ROOT / "samples" / "last-week")}
MAX_UPLOAD = 200_000

MODE = {"replay": False, "interval": 2}
WATCH: dict[str, subprocess.Popen | None] = {"proc": None}


# ── 폴더 감시 ──────────────────────────────────────────────────

def start_watch() -> None:
    env = dict(os.environ, PYTHONUTF8="1")
    if MODE["replay"]:
        env["CLAUDE_BIN"] = str(ROOT / "scripts" / "replay_claude.sh")
    INBOX.mkdir(exist_ok=True)
    log = open(LOG, "a", encoding="utf-8")
    log.write(f"--- {time.strftime('%H:%M:%S')} 시연 화면이 폴더 감시를 켰다 ({'다시 보기' if MODE['replay'] else '실제 실행'})\n")
    log.flush()
    WATCH["proc"] = subprocess.Popen(["bash", "scripts/watch.sh", "--interval", str(MODE["interval"])], cwd=ROOT, env=env,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def stop_watch() -> None:
    proc = WATCH["proc"]
    if proc and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)     # watch.sh 와 그 아래 request.sh 까지
        except ProcessLookupError:
            pass


# ── 화면에 줄 상태 ─────────────────────────────────────────────

def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def request_view(d: Path) -> dict:
    st = read_json(d / "state.json") or {}
    events = []
    try:
        events = [json.loads(l) for l in (d / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        pass
    claude = read_json(d / "claude.json") or {}
    col = read_json(d / "collected.json") or {}
    md = next(MINUTES.glob(f"*/*_{d.name}.md"), None) if MINUTES.is_dir() else None
    report = md.with_name(md.name[:-3] + ".report.json") if md else None
    return {
        "id": d.name,
        "source": st.get("source"),
        "trigger": st.get("trigger"),
        "at": st.get("at"),
        "terminal": st.get("terminal"),
        "reason": st.get("reason"),
        "visits": st.get("visits", {}),
        "history": st.get("history", []),
        "tool_calls": st.get("tool_calls", 0),
        "last_reject": st.get("last_reject"),
        "events": events,
        "review": read_json(d / "review.json"),
        "report": read_json(report) if report else None,
        "minutes": md.read_text(encoding="utf-8") if md else None,
        "minutes_path": md.relative_to(ROOT).as_posix() if md else None,
        "context": {"meeting": col.get("meeting"), "date": col.get("date"), "roster": col.get("roster") or [],
                    "previous": col.get("previous")} if col else None,
        "transcript": (d / "transcript.txt").read_text(encoding="utf-8") if (d / "transcript.txt").is_file() else None,
        "draft": read_json(d / "draft.json"),
        "cost": claude.get("total_cost_usd"),
        "started": (d / "transcript.txt").stat().st_mtime if (d / "transcript.txt").exists() else d.stat().st_mtime,
    }


def request_views() -> list[dict]:
    views = []
    for d in REQUESTS.iterdir() if REQUESTS.is_dir() else []:
        try:
            if d.is_dir():
                views.append(request_view(d))
        except OSError:  # 요청 폴더가 읽는 사이에 지워지거나 바뀜 — 다음 폴링에서 다시 본다
            continue
    return sorted(views, key=lambda r: r["started"], reverse=True)


def state() -> dict:
    reqs = request_views()
    try:
        lines = LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    proc = WATCH["proc"]
    return {
        "mode": "replay" if MODE["replay"] else "live",
        "interval": MODE["interval"],
        "watching": bool(proc and proc.poll() is None),
        "log": lines[-60:],
        "log_total": len(lines),
        "inbox": sorted(p.name for p in INBOX.glob("*.txt")) if INBOX.is_dir() else [],
        "requests": reqs,
    }


def save_inbox(name: str, data: bytes) -> str:
    stem = re.sub(r"[^\w.-]+", "_", Path(name).stem, flags=re.UNICODE).strip("._") or "transcript"
    dst = INBOX / f"{stem}.txt"
    n = 2
    while dst.exists():
        dst = INBOX / f"{stem}-{n}.txt"
        n += 1
    INBOX.mkdir(exist_ok=True)
    tmp = INBOX / f".{dst.name}.part"          # 감시가 반쯤 쓴 파일을 집지 않게 다 쓴 뒤 이름을 바꾼다
    tmp.write_bytes(data)
    tmp.rename(dst)
    return dst.name


def reset() -> None:
    for d in (REQUESTS, MINUTES, INBOX):
        if d.is_dir():
            shutil.rmtree(d)
    INBOX.mkdir()
    LOG.write_text("", encoding="utf-8")


# ── HTTP ───────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:      # 화면 새로고침(1초마다)으로 터미널이 차지 않게
        pass

    def send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj, code: int = 200) -> None:
        self.send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self.send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/state":
            self.json(state())
        else:
            self.json({"error": "없는 주소"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        url = urlparse(self.path)
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_UPLOAD:
            self.json({"error": f"파일이 너무 크다 ({size:,} 바이트, 최대 {MAX_UPLOAD:,})"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        body = self.rfile.read(size) if size else b""
        if url.path == "/api/upload":
            try:
                body.decode("utf-8")
            except UnicodeDecodeError:
                self.json({"error": "UTF-8 글 파일(.txt)만 올릴 수 있다"}, HTTPStatus.BAD_REQUEST)
                return
            if not body.strip():
                self.json({"error": "빈 파일이다"}, HTTPStatus.BAD_REQUEST)
                return
            name = unquote(self.headers.get("X-Filename") or "transcript.txt")
            self.json({"saved": save_inbox(name, body.replace(b"\r\n", b"\n"))})
        elif url.path.startswith("/api/sample/"):
            key = url.path.rsplit("/", 1)[-1]
            if key not in SAMPLES:
                self.json({"error": "없는 녹취록"}, HTTPStatus.NOT_FOUND)
                return
            if key in SEEDS:
                folder, src = SEEDS[key]
                (MINUTES / folder).mkdir(parents=True, exist_ok=True)
                for f in sorted(src.iterdir()):
                    shutil.copyfile(f, MINUTES / folder / f.name)
            saved = [save_inbox(n, (ROOT / "samples" / n).read_bytes()) for n in SAMPLES[key]]
            self.json({"saved": ", ".join(saved)})
        elif url.path == "/api/reset":
            reset()
            self.json({"ok": True})
        else:
            self.json({"error": "없는 주소"}, HTTPStatus.NOT_FOUND)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--replay", action="store_true", help="모델 없이 저장해 둔 초안으로 (리허설용)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--interval", type=int, default=2, help="inbox/ 를 몇 초마다 볼까 (기본 2)")
    a = p.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    MODE.update(replay=a.replay, interval=a.interval)
    if not a.replay and not shutil.which("claude"):
        print("claude 가 PATH 에 없다 — 실제 실행 모드는 Claude Code 가 필요하다. 리허설은 --replay", file=sys.stderr)
    start_watch()
    atexit.register(stop_watch)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    server = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"시연 화면: http://127.0.0.1:{a.port}  ({'다시 보기 — 모델 없음' if a.replay else '실제 실행 — Claude 사용량이 든다'})")
    print("끄려면 Ctrl+C", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        stop_watch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
