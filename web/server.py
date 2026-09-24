"""Tiny JSON API + static file server. Standard library only (plus `fsrs`).

    python server.py [--port 8000] [--db progress.db] [--deck decks/et-en]
"""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from store import Store

HERE = Path(__file__).parent


def make_handler(store: Store):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(HERE / "static"), **kwargs)

        def log_message(self, fmt, *args):  # quieter: only log API errors
            if args and str(args[1])[0] in "45":
                super().log_message(fmt, *args)

        def end_headers(self):
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def _json(self, data, status=HTTPStatus.OK):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self):
            url = urlparse(self.path)
            if not url.path.startswith("/api/"):
                return super().do_GET()
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            tz = int(q.get("tz", 0))
            routes = {
                "/api/next": lambda: store.next_card(tz, exclude=q.get("exclude")),
                "/api/stats": lambda: store.stats(tz),
                "/api/words": store.word_list,
                "/api/settings": store.settings,
                "/api/export": store.export,
            }
            if url.path not in routes:
                return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            self._json(routes[url.path]())

        def do_POST(self):
            url = urlparse(self.path)
            try:
                body = self._body()
                if url.path == "/api/review":
                    return self._json(store.review(
                        body["word_id"], int(body["example_idx"]), body["outcome"],
                        answer=str(body.get("answer", "")), duration_ms=body.get("duration_ms")))
                if url.path == "/api/settings":
                    return self._json(store.update_settings(body))
                if url.path == "/api/learn-more":
                    store.learn_more(int(body.get("tz", 0)), int(body.get("amount", 10)))
                    return self._json({"ok": True})
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
                return self._json({"error": f"bad request: {e}"}, HTTPStatus.BAD_REQUEST)
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--db", default=str(HERE / "progress.db"))
    ap.add_argument("--deck", default=str(HERE / "decks" / "et-en"))
    args = ap.parse_args()
    store = Store(args.db, args.deck)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store))
    print(f"{len(store.words)} words loaded. Open http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
