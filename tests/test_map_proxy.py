"""Offline AMap same-origin proxy validation: rejects SSRF and secret overrides."""
import unittest
from amap_client import Disabled
from map_proxy import prepare_proxy_path


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

    def test_missing_security_code_fails_closed(self):
        with self.assertRaises(Disabled):
            prepare_proxy_path("/_AMapService/v4/map/styles?key=abc", "")


if __name__ == "__main__":
    unittest.main()
