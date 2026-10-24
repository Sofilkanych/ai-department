#!/usr/bin/env python3
"""Табло AI-департаменту: локальний сервер.

Запуск з кореня департаменту:  python3 -I dashboard/server.py [--port 8787]
Відкрий http://127.0.0.1:8787  (демо без проєктів: http://127.0.0.1:8787/?demo)

Віддає лише дві речі: сторінку табло і /api/state — зведений стан усіх
projects/*/state.json та docs/04-tasks.json. Слухає тільки 127.0.0.1.
"""
import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent
ROOT = DASHBOARD.parent
PROJECTS = ROOT / "projects"

# Оркестратор переписує state.json під час роботи. Якщо прочитали файл
# наполовину записаним, віддаємо останню вдалу версію.
_last_good = {}


def read_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _last_good[path] = data
        return data
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _last_good.get(path)


def summarize_tasks(plan):
    if not plan:
        return None
    tasks = {t.get("id"): t for t in plan.get("tasks", [])}
    waves = []
    for wave in plan.get("waves", []):
        waves.append([
            {
                "id": tid,
                "title": tasks.get(tid, {}).get("title", ""),
                "status": tasks.get(tid, {}).get("status", "todo"),
                "attempts": tasks.get(tid, {}).get("attempts", 0),
            }
            for tid in wave
        ])
    # Розрізані таски замінено новими — у прогрес вони не входять
    statuses = [t.get("status", "todo") for t in tasks.values() if t.get("status") != "split"]
    return {
        "total": len(statuses),
        "done": statuses.count("done"),
        "in_progress": statuses.count("in_progress"),
        "blocked": statuses.count("blocked"),
        "waves": waves,
    }


def collect():
    projects = []
    if PROJECTS.exists():
        for state_file in sorted(PROJECTS.glob("*/state.json")):
            state = read_json(state_file)
            if not isinstance(state, dict):
                continue
            plan = read_json(state_file.parent / "docs" / "04-tasks.json")
            state.setdefault("slug", state_file.parent.name)
            state.setdefault("active", [])
            state.setdefault("waiting", None)
            state.setdefault("history", [])
            state.setdefault("gates", {})
            state["tasks"] = summarize_tasks(plan)
            projects.append(state)
    return {"generated_at": datetime.now().isoformat(timespec="seconds"), "projects": projects}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, (DASHBOARD / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/state":
            body = json.dumps(collect(), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="Табло AI-департаменту")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as e:
        if e.errno in (48, 98):  # порт зайнятий (macOS / Linux)
            print(f"Порт {args.port} уже зайнятий — найімовірніше, табло вже запущене.")
            print(f"Відкрий http://127.0.0.1:{args.port} або запусти на іншому порту: --port {args.port + 1}")
            raise SystemExit(1)
        raise
    print(f"Табло: http://127.0.0.1:{args.port}   (демо: http://127.0.0.1:{args.port}/?demo)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
