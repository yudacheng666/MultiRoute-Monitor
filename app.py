"""Local-only MultiRoute-Monitor server. AMap is disabled unless explicitly verified."""
from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from amap_client import Disabled, LiveGateway, ProviderError, RateLimited, RouteInputError
from map_proxy import PREFIX as MAP_PREFIX, prepare_proxy_path, proxy_get
from setup_amap import disable_private_authorization, save_private_authorization

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
ASSETS = {
    "/": (WEB / "index.html", "text/html; charset=utf-8"),
    "/index.html": (WEB / "index.html", "text/html; charset=utf-8"),
    "/style.css": (WEB / "style.css", "text/css; charset=utf-8"),
    "/app.js": (WEB / "app.js", "text/javascript; charset=utf-8"),
    "/core.js": (WEB / "core.js", "text/javascript; charset=utf-8"),
    "/amap_map.js": (WEB / "amap_map.js", "text/javascript; charset=utf-8"),
}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; "
       "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
       "form-action 'self'; frame-ancestors 'none'; object-src 'none'")


# The AMap runtime is never loaded without explicit opt-in. When enabled, permit
# its JS/tiles/worker domains without allowing arbitrary external scripts.
MAP_CSP = ("default-src 'none'; "
           "script-src 'self' https://webapi.amap.com https://*.amap.com https://*.autonavi.com; "
           "style-src 'self' 'unsafe-inline' https://*.amap.com; "
           "img-src 'self' data: blob: https://*.amap.com https://*.autonavi.com; "
           "connect-src 'self' https://*.amap.com https://*.autonavi.com; "
           "font-src 'self' data: https://*.amap.com; "
           "worker-src blob:; base-uri 'none'; form-action 'self'; "
           "frame-ancestors 'none'; object-src 'none'")

class Handler(BaseHTTPRequestHandler):
    server_version = "MultiRouteMonitor/0.2"

    def _base_headers(self, status, content_type, size):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", MAP_CSP if self.server.gateway.map_enabled() else CSP)
        self.end_headers()

    def _send(self, status, body, mime="text/plain; charset=utf-8", head=False):
        self._base_headers(status, mime, len(body))
        if not head:
            self.wfile.write(body)

    def _json(self, status, payload, head=False):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", head)

    def _host_allowed(self):
        host = self.headers.get("Host", "")
        port = self.server.server_port
        return host in ("127.0.0.1", "localhost",
                        "127.0.0.1:%s" % port, "localhost:%s" % port)

    def _serve(self, head=False):
        if not self._host_allowed():
            self._send(403, b"Host not allowed", head=head)
            return
        path = urlsplit(self.path).path
        if path in ("/api/status", "/api/amap/status"):
            status = self.server.gateway.status()
            if path == "/api/status":
                result = {"mode": status["mode"], "live_enabled": status["live_enabled"],
                          "external_requests": status["live_enabled"],
                          "version": "0.2.0-m1b-candidate"}
            else:
                result = status
            self._json(200, result, head)
            return
        if path.startswith(MAP_PREFIX):
            if head:
                self._send(405, b"Not allowed", head=head)
                return
            if not self.server.gateway.map_enabled():
                self._send(403, b"Map not enabled")
                return
            # Refuse cross-site browser requests to a local trusted proxy.
            fetch_site = self.headers.get("Sec-Fetch-Site")
            origin = self.headers.get("Origin")
            allowed_origins = ("http://127.0.0.1:%s" % self.server.server_port,
                               "http://localhost:%s" % self.server.server_port)
            if (fetch_site not in ("same-origin", "none")
                    or (origin is not None and origin not in allowed_origins)):
                self._send(403, b"Cross-site denied")
                return
            try:
                upstream = prepare_proxy_path(self.path, self.server.gateway.js_security)
            except (ValueError, Disabled):
                self._send(400, b"Map proxy request rejected")
                return
            try:
                self.server.gateway.reserve_map_proxy()
                body, mime = proxy_get(upstream)
            except RateLimited:
                self._send(429, b"Map budget exceeded")
                return
            except (Disabled, ProviderError):
                self._send(502, b"Map request unavailable")
                return
            self._send(200, body, mime)
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
        if not self._host_allowed():
            self._send(403, b"Host not allowed")
            return
        path = urlsplit(self.path).path
        allowed_paths = ("/api/amap/drive", "/api/amap/map-init",
                         "/api/amap/authorize", "/api/amap/disable")
        if path not in allowed_paths:
            self._send(405, b"Not allowed")
            return
        # Fail closed on local cross-site requests, including browser forms.
        port = self.server.server_port
        allowed_origins = ("http://127.0.0.1:%s" % port, "http://localhost:%s" % port)
        if (self.headers.get("Origin") not in allowed_origins
                or self.headers.get("X-MRM-Request") != "1"
                or self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json"):
            self._json(403, {"error": "请求来源或类型不允许"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > 4096 or (path == "/api/amap/drive" and length < 1):
            self._json(413, {"error": "请求内容长度不合法"})
            return
        if path in ("/api/amap/authorize", "/api/amap/disable"):
            payload = {}
            if length:
                try:
                    payload = json.loads(self.rfile.read(length))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._json(400, {"error": "设置内容格式错误"})
                    return
            if not isinstance(payload, dict):
                self._json(400, {"error": "设置内容格式错误"})
                return
            try:
                if path == "/api/amap/disable":
                    disable_private_authorization(self.server.root)
                else:
                    if not (self.server.gateway.key and self.server.gateway.js_key
                            and self.server.gateway.js_security):
                        self._json(400, {"error": "请先在本机配置 Web服务 Key、JS API Key 和 JS安全密钥"})
                        return
                    save_private_authorization(self.server.root, payload)
                self.server.gateway = LiveGateway(self.server.root)
                status = self.server.gateway.status()
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            except OSError:
                self._json(503, {"error": "本机授权设置无法保存"})
                return
            self._json(200, {
                "ok": True,
                "live_enabled": status["live_enabled"],
                "js_map_enabled": status["js_map_enabled"],
                "remaining_app_budget": status["remaining_app_budget"],
                "remaining_monthly_app_budget": status["remaining_monthly_app_budget"],
            })
            return
        if path == "/api/amap/map-init":
            if length:
                try:
                    payload = json.loads(self.rfile.read(length))
                    if payload != {}:
                        raise ValueError()
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    self._json(400, {"error": "地图初始化请求格式错误"})
                    return
            try:
                self.server.gateway.reserve_map_initialization()
                status = self.server.gateway.status()
            except RateLimited:
                self._json(429, {"error": "地图初始化已达到本机日/月预算"})
            except Disabled:
                self._json(403, {"error": "高德地图尚未授权启用"})
            except Exception:
                self._json(503, {"error": "地图预算状态不可用"})
            else:
                self._json(200, {
                    "ok": True,
                    "remaining_map_initializations": status["remaining_map_initializations"],
                    "remaining_monthly_map_initializations": status["remaining_monthly_map_initializations"],
                })
            return
        if not self.server.gateway.status()["live_enabled"]:
            self._json(403, {"error": "真实高德模式未启用或已达到额度限制"})
            return
        if length < 1:
            self._json(413, {"error": "请求内容长度不合法"})
            return
        try:
            data = json.loads(self.rfile.read(length))
            response = self.server.gateway.drive(data)
        except (UnicodeDecodeError, json.JSONDecodeError, RouteInputError) as exc:
            self._json(400, {"error": str(exc) if isinstance(exc, RouteInputError) else "路线数据格式错误"})
        except RateLimited:
            self._json(429, {"error": "请求频率或日/月额度已达内部限制"})
        except Disabled:
            self._json(403, {"error": "真实模式暂不可用"})
        except ProviderError:
            self._json(502, {"error": "高德路线查询失败；请检查网络、配额或接口权限"})
        except Exception:
            self._json(503, {"error": "服务暂时不可用"})
        else:
            self._json(200, response)

    def log_message(self, format, *args):
        # Never log live requests, private coordinates, credentials or URLs.
        pass


def make_server(port=8876, gateway=None, root=ROOT):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.root = Path(root).resolve()
    server.gateway = gateway if gateway is not None else LiveGateway(server.root)
    return server


def main():
    parser = argparse.ArgumentParser(description="Local-only MultiRoute-Monitor server")
    parser.add_argument("--port", type=int, default=8876)
    parser.add_argument("--open-browser", action="store_true",
                        help="open the local dashboard after startup")
    args = parser.parse_args()
    with make_server(args.port) as server:
        enabled = server.gateway.status()["live_enabled"]
        url = "http://127.0.0.1:%s/" % server.server_port
        print(url + " · " + ("高德候选（已授权）" if enabled else "模拟模式（默认，非真实路况）"),
              flush=True)
        print("按 Ctrl+C 停止", flush=True)
        if args.open_browser:
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
