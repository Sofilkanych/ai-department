#!/usr/bin/env python3
"""Табло AI-департаменту: локальний сервер.

Запуск із робочої теки (там, де лежить projects/):
    python3 -I <шлях до плагіна>/skills/department/dashboard/server.py [--root .] [--port 8787]
Відкрий http://127.0.0.1:8787  (демо без проєктів: http://127.0.0.1:8787/?demo)

Віддає лише дві речі: сторінку табло і /api/state — зведений стан усіх
<root>/projects/*/state.json та docs/04-tasks.json. Слухає тільки 127.0.0.1.
"""
import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent
PROJECTS = Path.cwd() / "projects"  # перевизначається параметром --root

# Оркестратор переписує state.json під час роботи. Якщо прочитали файл
# наполовину записаним, віддаємо останню вдалу версію — і кажемо сторінці,
# від якого часу вона, щоб стара картина не видавалася за живу.
_last_good = {}  # шлях -> (дані, коли востаннє прочитали без помилок)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path):
    """(дані, стан). ok — щойно прочитано; missing — файла немає;
    stale: <час> — зараз не читається, це остання вдала версія від цього часу;
    broken — не читається, і вдалої версії ще не було."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _last_good[path] = (data, now())
        return data, "ok"
    except FileNotFoundError:
        return None, "missing"
    except (json.JSONDecodeError, UnicodeDecodeError):
        if path in _last_good:
            data, since = _last_good[path]
            return data, "stale: " + since
        return None, "broken"


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
    # Розрізані таски замінено новими, зняті прибрано разом із вимогою — у прогрес вони не входять
    statuses = [t.get("status", "todo") for t in tasks.values() if t.get("status") not in ("split", "cancelled")]
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
            state, status = read_json(state_file)
            if status == "missing":
                continue
            stale = None
            if not isinstance(state, dict):
                # Файл є, але стан проєкту з нього не дістати: показуємо проєкт із попередженням,
                # а не ховаємо його мовчки
                state, stale = {}, {"file": "state.json", "since": None}
            elif status.startswith("stale: "):
                stale = {"file": "state.json", "since": status[len("stale: "):]}
            state = dict(state)  # копія: у кеш останньої вдалої версії нічого не дописуємо
            plan, plan_status = read_json(state_file.parent / "docs" / "04-tasks.json")
            if stale is None and plan_status != "ok" and plan_status != "missing":
                since = plan_status[len("stale: "):] if plan_status.startswith("stale: ") else None
                stale = {"file": "docs/04-tasks.json", "since": since}
            state.setdefault("slug", state_file.parent.name)
            state.setdefault("active", [])
            state.setdefault("waiting", None)
            state.setdefault("history", [])
            state.setdefault("gates", {})
            state["tasks"] = summarize_tasks(plan)
            state["stale"] = stale
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
    parser.add_argument("--root", default=".", help="робоча тека, у якій лежить projects/ (за замовчуванням — поточна)")
    args = parser.parse_args()
    global PROJECTS
    PROJECTS = Path(args.root).resolve() / "projects"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as e:
        if e.errno in (48, 98):  # порт зайнятий (macOS / Linux)
            print(f"Порт {args.port} уже зайнятий — найімовірніше, табло вже запущене.")
            print(f"Відкрий http://127.0.0.1:{args.port} або запусти на іншому порту: --port {args.port + 1}")
            raise SystemExit(1)
        raise
    print(f"Табло: http://127.0.0.1:{args.port}   (демо: http://127.0.0.1:{args.port}/?demo)")
    print(f"Проєкти: {PROJECTS}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
