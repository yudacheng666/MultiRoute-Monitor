"""HTTP integration tests: genuine local server, no provider networking."""
import http.client
import json
import threading
import unittest

from app import ASSETS, make_server
import inspect


class LocalServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, path="/", host=None, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request(method, path, headers={"Host": host or ("127.0.0.1:%s" % self.port)})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_default_port_is_not_srm_port(self):
        self.assertEqual(inspect.signature(make_server).parameters["port"].default, 8876)
        self.assertNotEqual(inspect.signature(make_server).parameters["port"].default, 8765)

    def test_assets(self):
        for path in ASSETS:
            with self.subTest(path=path):
                code, headers, body = self.request(path)
                self.assertEqual(code, 200)
                self.assertTrue(body)
                self.assertIn("no-store", headers["Cache-Control"])

    def test_status_is_explicitly_simulated(self):
        code, _, body = self.request("/api/status")
        data = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual(data["mode"], "simulation")
        self.assertFalse(data["live_enabled"])
        self.assertFalse(data["external_requests"])

    def test_host_rebinding_blocked(self):
        for bad in ("evil.example:8876", "127.0.0.1.evil.example", "example.org"):
            self.assertEqual(self.request("/", host=bad)[0], 403)

    def test_unknown_and_traversal_paths(self):
        for bad in ("/.env", "/../app.py", "/%2e%2e/app.py", "/api/route", "/not-real"):
            self.assertEqual(self.request(bad)[0], 404)

    def test_no_writes(self):
        self.assertEqual(self.request("/", method="POST")[0], 405)

    def test_security_headers(self):
        _, headers, _ = self.request("/")
        self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
