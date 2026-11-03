"""Offline HTTP integration tests including cross-origin and disabled endpoint."""
import http.client
import inspect
import json
import threading
import unittest
from pathlib import Path

from amap_client import LiveGateway
from app import ASSETS, make_server


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


if __name__ == "__main__":
    unittest.main()
