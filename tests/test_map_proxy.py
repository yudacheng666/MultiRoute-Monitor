"""Offline AMap same-origin proxy validation: rejects SSRF and secret overrides."""
import unittest
from amap_client import Disabled, ProviderError
from unittest.mock import patch
from map_proxy import prepare_proxy_path, proxy_get, select_upstream


class MapProxyTests(unittest.TestCase):
    def test_map_style_endpoint_rewrites_with_secret(self):
        result = prepare_proxy_path("/_AMapService/v4/map/styles?key=PUBLIC_JS_KEY&style=dark",
                                    "PRIVATE_TEST_SECURITY")
        self.assertTrue(result.startswith("/v4/map/styles?"))
        self.assertIn("jscode=PRIVATE_TEST_SECURITY", result)
        self.assertIn("key=PUBLIC_JS_KEY", result)

    def test_limited_v3_service(self):
        value = prepare_proxy_path("/_AMapService/v3/assistant/inputtips?keywords=x",
                                   "PRIVATE_TEST_SECURITY")
        self.assertTrue(value.startswith("/v3/assistant/inputtips?"))

    def test_reject_unlisted_paths_and_forwarded_urls(self):
        paths = [
            "/_AMapService/https://evil.example/",
            "/_AMapService/v1/arbitrary/action",
            "/_AMapService/v4/secret/admin",
            "/_AMapService/v3/../../secret",
            "/_AMapService/v3/assistant/../../secret",
            "/_AMapService/%2e%2e/v3/assistant/inputtips",
            "/_AMapService/v3/assistant/../inputtips",
            "https://evil.example/_AMapService/v3/assistant/inputtips",
            "/_AMapService/v3/assistant/inputtips?callback=foo",
            "/_AMapService/v3/assistant/inputtips?jscode=OVERRIDE",
        ]
        for path in paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    prepare_proxy_path(path, "PRIVATE_TEST_SECURITY")

    def test_fixed_upstream_selection_matches_official_proxy_routes(self):
        style = prepare_proxy_path("/_AMapService/v4/map/styles?key=PUBLIC_KEY",
                                   "SERVER_ONLY_SECURITY")
        service = prepare_proxy_path("/_AMapService/v3/assistant/inputtips?keywords=road",
                                     "SERVER_ONLY_SECURITY")
        self.assertEqual(select_upstream(style), "webapi.amap.com")
        self.assertEqual(select_upstream(service), "restapi.amap.com")
        for attack in ("https://example.com/v4/map/styles", "//example.com/v4/map/styles",
                       "/v2/maps", "/v4/map/styles/../admin"):
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                select_upstream(attack)

    def test_transport_uses_two_pinned_https_hosts_without_real_network(self):
        calls = []
        class FakeResponse:
            status = 200
            def read(self, n):
                return b'{"status":"1"}'
            def getheader(self, name, default=None):
                return "application/json" if name == "Content-Type" else None
        class FakeHTTPS:
            def __init__(self, host, timeout):
                calls.append(("connect", host, timeout))
            def request(self, method, path, headers):
                calls.append(("request", method, path))
            def getresponse(self):
                return FakeResponse()
            def close(self):
                pass
        with patch("map_proxy.http.client.HTTPSConnection", FakeHTTPS):
            for url, expected in (
                ("/_AMapService/v4/map/styles?key=PUBLIC_KEY", "webapi.amap.com"),
                ("/_AMapService/v3/assistant/inputtips?keywords=road", "restapi.amap.com")
            ):
                prepared = prepare_proxy_path(url, "SERVER_ONLY_SECURITY")
                body, kind = proxy_get(prepared)
                self.assertEqual(body, b'{"status":"1"}')
                self.assertEqual(kind, "application/json")
                self.assertEqual(calls[-2], ("connect", expected, 8))
                self.assertTrue(calls[-1][2].endswith("jscode=SERVER_ONLY_SECURITY"))

    def test_invalid_upstream_never_constructs_connection(self):
        with patch("map_proxy.http.client.HTTPSConnection") as connection:
            with self.assertRaises(ValueError):
                proxy_get("https://evil.example/v4/map/styles")
            connection.assert_not_called()

    def test_missing_security_code_fails_closed(self):
        with self.assertRaises(Disabled):
            prepare_proxy_path("/_AMapService/v4/map/styles?key=abc", "")


    def test_official_web_service_catch_all_accepts_versioned_jsapi_paths_only(self):
        for path in (
            "/_AMapService/v3/assistant/inputtips?keywords=x",
            "/_AMapService/v3/place/text?keywords=x",
            "/_AMapService/v3/config/district?keywords=x",
            "/_AMapService/v4/grasproad/driving",
        ):
            with self.subTest(path=path):
                prepared = prepare_proxy_path(path, "PRIVATE_TEST_SECURITY")
                self.assertEqual(select_upstream(prepared), "restapi.amap.com")
        for path in (
            "/_AMapService/v2/place/text",
            "/_AMapService/v3/../secret",
            "/_AMapService/v3/%2e%2e/secret",
            "/_AMapService/v3//place/text",
            "/_AMapService/v3/place\\text",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                prepare_proxy_path(path, "PRIVATE_TEST_SECURITY")

    def test_proxy_rejects_oversized_response_without_returning_partial_body(self):
        class FakeResponse:
            status = 200
            def getheader(self, name, default=None):
                return "application/json" if name == "Content-Type" else None
            def read(self, size):
                return b"x" * size
        class FakeHTTPS:
            def __init__(self, host, timeout):
                pass
            def request(self, method, path, headers):
                pass
            def getresponse(self):
                return FakeResponse()
            def close(self):
                pass
        with patch("map_proxy.MAX_BYTES", 8), patch(
                "map_proxy.http.client.HTTPSConnection", FakeHTTPS):
            with self.assertRaises(ProviderError):
                proxy_get("/v4/map/styles?jscode=PRIVATE_TEST_SECURITY")

    def test_proxy_rejects_unsafe_content_type(self):
        class FakeResponse:
            status = 200
            def getheader(self, name, default=None):
                return "text/html; charset=utf-8" if name == "Content-Type" else None
            def read(self, size):
                return b"<html>fixture</html>"
        class FakeHTTPS:
            def __init__(self, host, timeout):
                pass
            def request(self, method, path, headers):
                pass
            def getresponse(self):
                return FakeResponse()
            def close(self):
                pass
        with patch("map_proxy.http.client.HTTPSConnection", FakeHTTPS):
            with self.assertRaises(ProviderError):
                proxy_get("/v4/map/styles?jscode=PRIVATE_TEST_SECURITY")

    def test_proxy_does_not_follow_redirects(self):
        calls = []
        class FakeResponse:
            status = 302
            def getheader(self, name, default=None):
                return "https://evil.example/" if name == "Location" else None
            def read(self, size):
                calls.append("read")
                return b""
        class FakeHTTPS:
            def __init__(self, host, timeout):
                calls.append(("connect", host))
            def request(self, method, path, headers):
                calls.append(("request", method, path))
            def getresponse(self):
                return FakeResponse()
            def close(self):
                calls.append("close")
        with patch("map_proxy.http.client.HTTPSConnection", FakeHTTPS):
            with self.assertRaises(ProviderError):
                proxy_get("/v4/map/styles?jscode=PRIVATE_TEST_SECURITY")
        self.assertNotIn("read", calls)
        self.assertEqual(sum(1 for x in calls if isinstance(x, tuple) and x[0] == "connect"), 1)

    def test_proxy_rejects_declared_oversized_content_length(self):
        class FakeResponse:
            status = 200
            def getheader(self, name, default=None):
                return "application/json" if name == "Content-Type" else "9999999"
            def read(self, size):
                raise AssertionError("must reject from Content-Length before reading")
        class FakeHTTPS:
            def __init__(self, host, timeout):
                pass
            def request(self, method, path, headers):
                pass
            def getresponse(self):
                return FakeResponse()
            def close(self):
                pass
        with patch("map_proxy.http.client.HTTPSConnection", FakeHTTPS):
            with self.assertRaises(ProviderError):
                proxy_get("/v4/map/styles?jscode=PRIVATE_TEST_SECURITY")


if __name__ == "__main__":
    unittest.main()
