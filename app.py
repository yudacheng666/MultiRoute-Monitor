"""MultiRoute-Monitor M1-A local-only simulation server (stdlib only)."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
ASSETS = {
    "/": (WEB / "index.html", "text/html; charset=utf-8"),
    "/index.html": (WEB / "index.html", "text/html; charset=utf-8"),
    "/style.css": (WEB / "style.css", "text/css; charset=utf-8"),
    "/app.js": (WEB / "app.js", "text/javascript; charset=utf-8"),
    "/core.js": (WEB / "core.js", "text/javascript; charset=utf-8"),
}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; "
       "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
       "form-action 'self'; frame-ancestors 'none'; object-src 'none'")

class Handler(BaseHTTPRequestHandler):
    server_version = "MultiRouteMonitor/0.1"

    def _base_headers(self, status, content_type, size):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()

    def _send(self, status, body, mime="text/plain; charset=utf-8", head=False):
        self._base_headers(status, mime, len(body))
        if not head:
            self.wfile.write(body)

    def _serve(self, head=False):
        host = self.headers.get("Host", "")
        host_name = host.split(":")[0].lower()
        # Reject DNS-rebinding aliases and malformed hosts; localhost is explicit.
        if host_name not in ("127.0.0.1", "localhost") or "@" in host or host.startswith("["):
            self._send(403, b"Host not allowed", head=head)
            return
        path = urlsplit(self.path).path
        if path == "/api/status":
            payload = json.dumps({"mode": "simulation", "live_enabled": False,
                                  "external_requests": False, "version": "0.1.0-m1a"},
                                 ensure_ascii=False).encode("utf-8")
            self._send(200, payload, "application/json; charset=utf-8", head)
            return
        asset = ASSETS.get(path)
        if asset is None:
            self._send(404, b"Not found", head=head)
            return
        try:
            body = asset[0].read_bytes()
        except OSError:
            self._send(500, b"Asset unavailable", head=head)
            return
        self._send(200, body, asset[1], head)

    def do_GET(self):
        self._serve(False)

    def do_HEAD(self):
        self._serve(True)

    def do_POST(self):
        self._send(405, b"Read-only simulation server")

    def log_message(self, format, *args):
        # Do not log user-supplied URLs or headers.
        pass


def make_server(port=8765):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="MultiRoute-Monitor mock-only local server")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with make_server(args.port) as server:
        print("模拟模式（非真实路况）：http://127.0.0.1:%s/" % server.server_port, flush=True)
        print("按 Ctrl+C 停止", flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
