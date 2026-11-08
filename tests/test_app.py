"""Offline HTTP integration tests including cross-origin and disabled endpoint."""
import http.client
import inspect
import json
import threading
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch, MagicMock, ANY

from amap_client import LiveGateway, ProviderError, RateLimited
from app import ASSETS, main, make_server
from setup_amap import authorization_path, save_private_keys


class LocalServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0, gateway=LiveGateway(Path("."), env={}))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, path="/", host=None, method="GET", body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        hdr = {"Host": host or ("127.0.0.1:%s" % self.port)}
        if headers:
            hdr.update(headers)
        conn.request(method, path, body=body, headers=hdr)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_default_port_is_not_srm_port(self):
        self.assertEqual(inspect.signature(make_server).parameters["port"].default, 8876)

    def test_assets(self):
        for path in ASSETS:
            with self.subTest(path=path):
                code, headers, body = self.request(path)
                self.assertEqual(code, 200)
                self.assertTrue(body)
                self.assertIn("no-store", headers["Cache-Control"])

    def test_status_disabled_by_default(self):
        for path in ("/api/status", "/api/amap/status"):
            code, _, body = self.request(path)
            self.assertEqual(code, 200)
            data = json.loads(body)
            self.assertFalse(data["live_enabled"])
            self.assertEqual(data["mode"], "simulation")

    def test_host_rebinding_blocked(self):
        for bad in ("evil.example:8876", "127.0.0.1.evil.example", "example.org",
                    "localhost:9999", "127.0.0.1:8765"):
            self.assertEqual(self.request("/", host=bad)[0], 403)

    def test_unknown_and_traversal_paths(self):
        for bad in ("/.env", "/../app.py", "/%2e%2e/app.py", "/api/route", "/not-real"):
            self.assertEqual(self.request(bad)[0], 404)

    def test_unrecognized_post_blocked(self):
        self.assertEqual(self.request("/", method="POST")[0], 405)

    def test_cross_site_post_rejected(self):
        payload = json.dumps({"origin": "116,39", "destination": "116.1,39.1"})
        good = {"Origin": "http://127.0.0.1:%s" % self.port,
                "X-MRM-Request": "1", "Content-Type": "application/json"}
        bad = {**good, "Origin": "https://evil.example"}
        self.assertEqual(self.request("/api/amap/drive", method="POST", body=payload,
                                      headers=bad)[0], 403)
        self.assertEqual(self.request("/api/amap/drive", method="POST", body=payload,
                                      headers={k:v for k,v in good.items() if k!="X-MRM-Request"})[0], 403)
        self.assertEqual(self.request("/api/amap/drive", method="POST", body=payload,
                                      headers=good)[0], 403)  # Live off!

    def test_map_proxy_denied_when_not_authorized(self):
        code, _, body = self.request("/_AMapService/v4/map/styles?key=FAKE")
        self.assertEqual(code, 403)
        self.assertNotIn(b"PRIVATE_TEST_SECURITY", body)

    def test_optional_map_loader_is_local_asset(self):
        code, headers, body = self.request("/amap_map.js")
        self.assertEqual(code, 200)
        self.assertIn(b"serviceHost", body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])

    def test_security_headers(self):
        _, headers, _ = self.request("/")
        self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")


class EnabledMapGateway:
    """Synthetic gateway used only by offline HTTP integration tests."""
    js_security = "PRIVATE_TEST_SECURITY"

    def __init__(self, fail_budget=False):
        self.reservations = 0
        self.fail_budget = fail_budget

    def map_enabled(self):
        return True

    def reserve_map_proxy(self):
        if self.fail_budget:
            raise RateLimited("fixture budget exhausted")
        self.reservations += 1


class MapProxyHTTPIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.gateway = EnabledMapGateway()
        self.server = make_server(0, gateway=self.gateway)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, path, headers=None, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        values = {"Host": "127.0.0.1:%s" % self.port}
        values.update(headers or {})
        conn.request(method, path, headers=values)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_enabled_style_route_injects_server_secret_and_returns_safe_response(self):
        fixture = b'{"style":"fixture-only"}'
        with patch("app.proxy_get", return_value=(fixture, "application/json")) as transport:
            code, headers, body = self.request(
                "/_AMapService/v4/map/styles?key=PUBLIC_JS_KEY&style=dark",
                {"Sec-Fetch-Site": "same-origin"},
            )
        self.assertEqual(code, 200)
        self.assertEqual(body, fixture)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.gateway.reservations, 1)
        prepared = transport.call_args.args[0]
        self.assertTrue(prepared.startswith("/v4/map/styles?"))
        self.assertIn("jscode=PRIVATE_TEST_SECURITY", prepared)
        self.assertIn("key=PUBLIC_JS_KEY", prepared)
        self.assertNotIn(b"PRIVATE_TEST_SECURITY", body)
        self.assertNotIn("PRIVATE_TEST_SECURITY", str(headers))

    def test_enabled_web_service_route_uses_same_backend_integration(self):
        with patch("app.proxy_get", return_value=(b"{}", "application/json")) as transport:
            code, _, body = self.request(
                "/_AMapService/v3/assistant/inputtips?keywords=fixture",
                {"Sec-Fetch-Site": "same-origin"},
            )
        self.assertEqual(code, 200)
        self.assertEqual(body, b"{}")
        self.assertIn("jscode=PRIVATE_TEST_SECURITY", transport.call_args.args[0])
        self.assertEqual(self.gateway.reservations, 1)

    def test_cross_site_map_request_is_rejected_before_budget_or_transport(self):
        with patch("app.proxy_get") as transport:
            code, _, _ = self.request(
                "/_AMapService/v4/map/styles?key=PUBLIC",
                {"Sec-Fetch-Site": "cross-site"},
            )
        self.assertEqual(code, 403)
        self.assertEqual(self.gateway.reservations, 0)
        transport.assert_not_called()

    def test_invalid_path_or_caller_supplied_secret_is_rejected_before_transport(self):
        for path in (
            "/_AMapService/v3/assistant/../inputtips",
            "/_AMapService/v3/assistant/inputtips?jscode=ATTACKER",
            "/_AMapService/https://evil.example/path",
        ):
            with self.subTest(path=path), patch("app.proxy_get") as transport:
                code, _, body = self.request(path, {"Sec-Fetch-Site": "same-origin"})
                self.assertEqual(code, 400)
                self.assertNotIn(b"PRIVATE_TEST_SECURITY", body)
                transport.assert_not_called()
        self.assertEqual(self.gateway.reservations, 0)

    def test_budget_exhaustion_returns_429_without_upstream_request(self):
        self.gateway.fail_budget = True
        with patch("app.proxy_get") as transport:
            code, _, body = self.request(
                "/_AMapService/v4/map/styles?key=PUBLIC",
                {"Sec-Fetch-Site": "same-origin"},
            )
        self.assertEqual(code, 429)
        self.assertNotIn(b"PRIVATE_TEST_SECURITY", body)
        transport.assert_not_called()

    def test_upstream_failure_returns_generic_502_without_secret(self):
        with patch("app.proxy_get", side_effect=ProviderError("fixture failure")):
            code, _, body = self.request(
                "/_AMapService/v4/map/styles?key=PUBLIC",
                {"Sec-Fetch-Site": "same-origin"},
            )
        self.assertEqual(code, 502)
        self.assertNotIn(b"PRIVATE_TEST_SECURITY", body)

    def test_head_map_proxy_is_not_allowed(self):
        with patch("app.proxy_get") as transport:
            code, _, _ = self.request(
                "/_AMapService/v4/map/styles?key=PUBLIC",
                {"Sec-Fetch-Site": "same-origin"},
                method="HEAD",
            )
        self.assertEqual(code, 405)
        self.assertEqual(self.gateway.reservations, 0)
        transport.assert_not_called()

    def test_map_initialization_endpoint_denied_by_default(self):
        self.server.gateway = LiveGateway(Path("."), env={})
        headers = {"Origin":"http://127.0.0.1:%s" % self.port,
                   "X-MRM-Request":"1", "Content-Type":"application/json"}
        code, _, _ = self.request("/api/amap/map-init", method="POST",
                                  headers=headers)
        self.assertEqual(code, 403)

    def test_map_initialization_endpoint_counts_only_authorized_local_request(self):
        class Gateway:
            js_security = "PRIVATE_TEST_SECURITY"
            def __init__(self):
                self.count = 0
            def map_enabled(self):
                return True
            def reserve_map_initialization(self):
                self.count += 1
            def status(self):
                return {"remaining_map_initializations":30-self.count,
                        "remaining_monthly_map_initializations":900-self.count}
        server = make_server(0, gateway=Gateway())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            body = json.dumps({})
            conn.request("POST", "/api/amap/map-init", body=body, headers={
                "Host":"127.0.0.1:%s" % server.server_port,
                "Origin":"http://127.0.0.1:%s" % server.server_port,
                "X-MRM-Request":"1", "Content-Type":"application/json"})
            response = conn.getresponse()
            payload = json.loads(response.read())
            conn.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["remaining_map_initializations"],29)
            self.assertEqual(server.gateway.count,1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class AuthorizationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        save_private_keys(self.root,{
            "MRM_AMAP_WEB_KEY":"EXAMPLE_WEB_KEY_123",
            "MRM_AMAP_JS_KEY":"EXAMPLE_JS_KEY_456",
            "MRM_AMAP_JS_SECURITY":"EXAMPLE_JS_SECURITY_789",
        })
        self.server=make_server(0,root=self.root)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.port=self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.tmp.cleanup()

    def post(self,path,payload):
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=3)
        body=json.dumps(payload)
        conn.request("POST",path,body=body,headers={
            "Host":"127.0.0.1:%s" % self.port,
            "Origin":"http://127.0.0.1:%s" % self.port,
            "X-MRM-Request":"1",
            "Content-Type":"application/json"})
        response=conn.getresponse()
        data=json.loads(response.read())
        conn.close()
        return response.status,data

    def test_authorization_endpoint_requires_all_user_confirmations(self):
        payload={"ticket_id":"AMAP-2026-001","route_quota_remaining":150000,
                 "map_quota_remaining":1500000,"approved_by_amap":False,
                 "quota_verified":True,"account_exclusive":True,"zero_cost_ack":True}
        code,data=self.post("/api/amap/authorize",payload)
        self.assertEqual(code,400)
        self.assertFalse(self.server.gateway.status()["live_enabled"])
        self.assertFalse(authorization_path(self.root).exists())

    def test_authorization_endpoint_enables_only_after_confirmation_and_never_stores_keys(self):
        payload={"ticket_id":"AMAP-2026-001","route_quota_remaining":150000,
                 "map_quota_remaining":1500000,"personal_developer_verified":True,"approved_by_amap":True,
                 "quota_verified":True,"account_exclusive":True,"zero_cost_ack":True}
        code,data=self.post("/api/amap/authorize",payload)
        self.assertEqual(code,200)
        self.assertTrue(data["live_enabled"])
        self.assertTrue(data["js_map_enabled"])
        self.assertEqual(data["remaining_monthly_app_budget"],30000)
        saved=authorization_path(self.root).read_text(encoding="utf-8")
        self.assertNotIn("EXAMPLE_WEB_KEY_123",saved)
        self.assertNotIn("EXAMPLE_JS_SECURITY_789",saved)
        self.assertTrue(self.server.gateway.status()["live_enabled"])

    def test_disable_endpoint_immediately_turns_live_off(self):
        payload={"ticket_id":"AMAP-2026-001","route_quota_remaining":150000,
                 "map_quota_remaining":1500000,"personal_developer_verified":True,"approved_by_amap":True,
                 "quota_verified":True,"account_exclusive":True,"zero_cost_ack":True}
        self.assertEqual(self.post("/api/amap/authorize",payload)[0],200)
        code,data=self.post("/api/amap/disable",{})
        self.assertEqual(code,200)
        self.assertFalse(data["live_enabled"])
        self.assertFalse(self.server.gateway.status()["live_enabled"])


class LauncherTests(unittest.TestCase):
    def test_open_browser_flag_uses_only_local_dashboard_url(self):
        fake=MagicMock()
        fake.server_port=8876
        fake.gateway.status.return_value={"live_enabled":False}
        fake.__enter__.return_value=fake
        fake.serve_forever.side_effect=KeyboardInterrupt
        with patch("app.make_server",return_value=fake), \
             patch("app.threading.Timer") as timer, \
             patch("app.argparse.ArgumentParser.parse_args",
                   return_value=type("Args",(),{"port":8876,"open_browser":True})()):
            main()
        timer.assert_called_once_with(1.0,ANY)
        callback=timer.call_args.args[1]
        with patch("app.webbrowser.open") as open_browser:
            callback()
            open_browser.assert_called_once_with("http://127.0.0.1:8876/")


if __name__ == "__main__":
    unittest.main()
