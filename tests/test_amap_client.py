"""All tests are offline: the transport is injected, no AMap account or requests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amap_client import (
    LiveGateway, Disabled, ProviderError, RateLimited, RouteInputError,
    coord, parse_driving, query_path, validate_request,
)

EXAMPLE = {
    "status": "1", "infocode": "10000",
    "route": {"paths": [{
        "distance": "12500", "cost": {"duration": "1337"},
        "steps": [
            {"polyline": "116.100000,39.900000;116.200000,39.910000",
             "tmcs": [
                {"tmc_status": "畅通", "tmc_polyline": "116.100000,39.900000,116.150000,39.905000"},
                {"tmc_status": "拥堵", "tmc_polyline": "116.150000,39.905000,116.200000,39.910000"},
            ]}
        ],
    }]},
}
COORDS = {"origin": "116.100000,39.900000", "destination": "116.200000,39.910000"}


class DriverTests(unittest.TestCase):
    def test_coord_validation(self):
        self.assertEqual(coord("116.12, 39.9"), "116.12,39.9")
        for bad in ("", "116", "116,abc", "999,20", "100,91", "1e999,39", "116.1234567,39"):
            with self.subTest(bad=bad):
                with self.assertRaises(RouteInputError):
                    coord(bad)

    def test_validate_route(self):
        req = validate_request({**COORDS, "waypoints": ["116.15,39.91"]})
        self.assertEqual(req["waypoints"], ["116.15,39.91"])
        for req in ({**COORDS, "waypoints": ["1,2", "3,4"]},
                    {**COORDS, "destination": COORDS["origin"]},
                    {"origin": "bad", "destination": "1,2"}):
            with self.assertRaises(RouteInputError):
                validate_request(req)

    def test_documented_query_fields(self):
        req = validate_request(COORDS)
        path = query_path(req, "FICTIONAL_NOT_REAL_KEY")
        self.assertIn("show_fields=cost%2Ctmcs%2Cpolyline", path)
        self.assertIn("strategy=32", path)
        self.assertTrue(path.startswith("/v5/direction/driving?"))

    def test_parse_realistic_fixture(self):
        result = parse_driving(EXAMPLE)
        self.assertEqual(result["source"], "AMAP")
        self.assertEqual(result["eta_minutes"], 23)
        self.assertEqual(result["distance_km"], 12.5)
        self.assertEqual([x["status"] for x in result["segments"]], ["畅通", "拥堵"])
        self.assertTrue(result["traffic_available"])

    def test_tmc_polyline_accepts_legacy_semicolon_and_rejects_odd_flat_list(self):
        payload = json.loads(json.dumps(EXAMPLE))
        tmcs = payload["route"]["paths"][0]["steps"][0]["tmcs"]
        tmcs[0]["tmc_polyline"] = "116.100000,39.900000;116.150000,39.905000"
        result = parse_driving(payload)
        self.assertEqual(result["segments"][0]["points"],
                         [[116.1,39.9],[116.15,39.905]])
        payload["route"]["paths"][0]["steps"][0]["tmcs"][0]["tmc_polyline"] = "116.1,39.9,116.2"
        with self.assertRaises(ProviderError):
            parse_driving(payload)

    def test_unknown_traffic_not_faked(self):
        payload = json.loads(json.dumps(EXAMPLE))
        payload["route"]["paths"][0]["steps"][0]["tmcs"] = []
        result = parse_driving(payload)
        self.assertFalse(result["traffic_available"])
        self.assertEqual(result["segments"][0]["status"], "未知")

    def test_fail_closed_provider(self):
        for data in ({}, {"status": "0"}, {"status": "1", "route": {"paths": []}}):
            with self.assertRaises(ProviderError):
                parse_driving(data)

    def test_disabled_default_no_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            gw = LiveGateway(tmp, env={}, transport=lambda p: calls.append(p))
            self.assertFalse(gw.status()["live_enabled"])
            with self.assertRaises(Disabled):
                gw.drive(COORDS)
            self.assertEqual(calls, [])
            self.assertFalse((Path(tmp) / "local").exists())

    def test_optional_map_keys_do_not_enable_unverified_live_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MRM_AMAP_JS_KEY": "LOCAL_EXAMPLE_JS_KEY",
                   "MRM_AMAP_JS_SECURITY": "LOCAL_EXAMPLE_SECURITY",
                   "MRM_AMAP_MAP_OPT_IN": "YES"}
            gw = LiveGateway(tmp, env=env)
            self.assertFalse(gw.map_enabled())
            self.assertFalse(gw.status()["js_map_enabled"])
            self.assertIsNone(gw.status()["js_map_key"])

    def test_map_proxy_attempt_counter_without_supplier_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MRM_AMAP_WEB_KEY": "LOCAL_FAKE_WEB_KEY",
                   "MRM_USAGE_AUTHORIZED": "YES",
                   "MRM_FREE_QUOTA_VERIFIED": "YES",
                   "MRM_EXPLICIT_LIVE_OPT_IN": "YES",
                   "MRM_AMAP_JS_KEY": "LOCAL_FAKE_JS_KEY",
                   "MRM_AMAP_JS_SECURITY": "LOCAL_FAKE_SECURITY",
                   "MRM_AMAP_MAP_OPT_IN": "YES"}
            gateway = LiveGateway(tmp, env=env, transport=lambda _: EXAMPLE)
            self.assertTrue(gateway.map_enabled())
            self.assertEqual(gateway.status()["js_map_key"], "LOCAL_FAKE_JS_KEY")
            self.assertEqual(gateway.status()["remaining_map_proxy_budget"], 500)
            gateway.reserve_map_proxy()
            self.assertEqual(gateway.status()["remaining_map_proxy_budget"], 499)
            usage = (Path(tmp) / "local" / "amap_map_proxy_attempts.json").read_text()
            self.assertNotIn("LOCAL_FAKE_SECURITY", usage)
            self.assertNotIn("116.", usage)
            again = LiveGateway(tmp, env=env)
            self.assertEqual(again.status()["remaining_map_proxy_budget"], 499)

    def test_map_initialization_has_independent_qps_guard(self):
        now=[100.0]
        env={"MRM_AMAP_WEB_KEY":"LOCAL_FAKE_WEB_KEY","MRM_USAGE_AUTHORIZED":"YES",
             "MRM_FREE_QUOTA_VERIFIED":"YES","MRM_EXPLICIT_LIVE_OPT_IN":"YES",
             "MRM_AMAP_JS_KEY":"LOCAL_FAKE_JS_KEY","MRM_AMAP_JS_SECURITY":"LOCAL_FAKE_SECURITY",
             "MRM_AMAP_MAP_OPT_IN":"YES"}
        with tempfile.TemporaryDirectory() as tmp:
            gateway=LiveGateway(tmp,env=env,clock=lambda:now[0])
            gateway.reserve_map_initialization()
            with self.assertRaises(RateLimited):
                gateway.reserve_map_initialization()
            now[0]+=1.1
            gateway.reserve_map_initialization()
            self.assertEqual(gateway.status()["remaining_map_initializations"],28)

    def test_last_map_initialization_does_not_block_its_proxy_resources(self):
        env = {"MRM_AMAP_WEB_KEY":"LOCAL_FAKE_WEB_KEY",
               "MRM_USAGE_AUTHORIZED":"YES","MRM_FREE_QUOTA_VERIFIED":"YES",
               "MRM_EXPLICIT_LIVE_OPT_IN":"YES","MRM_AMAP_JS_KEY":"LOCAL_FAKE_JS_KEY",
               "MRM_AMAP_JS_SECURITY":"LOCAL_FAKE_SECURITY","MRM_AMAP_MAP_OPT_IN":"YES",
               "MRM_MAP_INIT_DAILY_CAP":"1","MRM_MAP_INIT_MONTHLY_CAP":"1"}
        with tempfile.TemporaryDirectory() as tmp:
            gateway=LiveGateway(tmp,env=env)
            self.assertTrue(gateway.status()["js_map_enabled"])
            gateway.reserve_map_initialization()
            self.assertFalse(gateway.status()["js_map_enabled"])
            # The one allowed map must still be able to fetch its style/resources.
            self.assertTrue(gateway.map_enabled())
            gateway.reserve_map_proxy()
            self.assertEqual(gateway.status()["remaining_map_proxy_budget"],499)

    def test_needs_all_three_authorization_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MRM_AMAP_WEB_KEY": "FAKE", "MRM_USAGE_AUTHORIZED": "YES",
                   "MRM_FREE_QUOTA_VERIFIED": "YES"}
            gateway = LiveGateway(tmp, env=env, transport=lambda p: EXAMPLE)
            self.assertFalse(gateway.enabled)
            env["MRM_EXPLICIT_LIVE_OPT_IN"] = "YES"
            self.assertTrue(LiveGateway(tmp, env=env, transport=lambda p: EXAMPLE).enabled)

    def test_daily_cap_survives_restart(self):
        env = {"MRM_AMAP_WEB_KEY": "FAKE", "MRM_USAGE_AUTHORIZED": "YES",
               "MRM_FREE_QUOTA_VERIFIED": "YES", "MRM_EXPLICIT_LIVE_OPT_IN": "YES",
               "MRM_DAILY_REQUEST_CAP": "1"}
        with tempfile.TemporaryDirectory() as tmp:
            requests = []
            gw = LiveGateway(tmp, env=env, transport=lambda p: (requests.append(p), EXAMPLE)[1],
                             clock=lambda: 1000.0)
            self.assertEqual(gw.drive(COORDS)["eta_minutes"], 23)
            self.assertEqual(len(requests), 1)
            self.assertEqual(gw.status()["remaining_app_budget"], 0)
            again = LiveGateway(tmp, env=env, transport=lambda p: requests.append(p),
                                clock=lambda: 2000.0)
            with self.assertRaises(RateLimited):
                again.drive({**COORDS, "destination": "116.201000,39.910000"})
            self.assertEqual(len(requests), 1)

    def test_rapid_repeat_blocked(self):
        env = {"MRM_AMAP_WEB_KEY": "FAKE", "MRM_USAGE_AUTHORIZED": "YES",
               "MRM_FREE_QUOTA_VERIFIED": "YES", "MRM_EXPLICIT_LIVE_OPT_IN": "YES",
               "MRM_DAILY_REQUEST_CAP": "100"}
        with tempfile.TemporaryDirectory() as tmp:
            now = [1000.0]
            gw = LiveGateway(tmp, env=env, transport=lambda p: EXAMPLE, clock=lambda: now[0])
            gw.drive(COORDS)
            now[0] += 3
            with self.assertRaises(RateLimited):
                gw.drive(COORDS)
            self.assertEqual(gw.status()["remaining_app_budget"], 99)

    def test_provider_error_attempt_still_counts(self):
        env = {"MRM_AMAP_WEB_KEY": "FAKE", "MRM_USAGE_AUTHORIZED": "YES",
               "MRM_FREE_QUOTA_VERIFIED": "YES", "MRM_EXPLICIT_LIVE_OPT_IN": "YES",
               "MRM_DAILY_REQUEST_CAP": "100"}
        with tempfile.TemporaryDirectory() as tmp:
            gw = LiveGateway(tmp, env=env, transport=lambda p: {"status": "0"},
                             clock=lambda: 1000.0)
            with self.assertRaises(ProviderError):
                gw.drive(COORDS)
            self.assertEqual(gw.status()["remaining_app_budget"], 99)

    def test_monthly_cap_survives_restart_and_daily_reset(self):
        env = {"MRM_AMAP_WEB_KEY":"FAKE", "MRM_USAGE_AUTHORIZED":"YES",
               "MRM_FREE_QUOTA_VERIFIED":"YES", "MRM_EXPLICIT_LIVE_OPT_IN":"YES",
               "MRM_DAILY_REQUEST_CAP":"2", "MRM_MONTHLY_REQUEST_CAP":"2"}
        with tempfile.TemporaryDirectory() as tmp:
            gw = LiveGateway(tmp, env=env, transport=lambda _: EXAMPLE, clock=lambda: 1000.0)
            gw.drive(COORDS)
            self.assertEqual(gw.status()["remaining_app_budget"], 1)
            self.assertEqual(gw.status()["remaining_monthly_app_budget"], 1)
            gw2 = LiveGateway(tmp, env=env, transport=lambda _: EXAMPLE, clock=lambda: 2000.0)
            gw2.drive({**COORDS, "destination":"116.201,39.91"})
            self.assertEqual(gw2.status()["remaining_monthly_app_budget"], 0)
            gw3 = LiveGateway(tmp, env=env, transport=lambda _: EXAMPLE, clock=lambda: 3000.0)
            with self.assertRaises(RateLimited):
                gw3.drive({**COORDS, "destination":"116.202,39.91"})

    def test_legacy_daily_counter_migrates_into_month_counter(self):
        env = {"MRM_AMAP_WEB_KEY":"FAKE", "MRM_USAGE_AUTHORIZED":"YES",
               "MRM_FREE_QUOTA_VERIFIED":"YES", "MRM_EXPLICIT_LIVE_OPT_IN":"YES",
               "MRM_MONTHLY_REQUEST_CAP":"50"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local" / "amap_request_attempts.json"
            path.parent.mkdir()
            gw = LiveGateway(tmp, env=env)
            path.write_text(json.dumps({"day":gw._day(),"count":7}))
            self.assertEqual(gw.status()["remaining_monthly_app_budget"], 43)

    def test_map_initialization_has_separate_daily_and_monthly_hard_cap(self):
        env = {"MRM_AMAP_WEB_KEY":"FAKE", "MRM_USAGE_AUTHORIZED":"YES",
               "MRM_FREE_QUOTA_VERIFIED":"YES", "MRM_EXPLICIT_LIVE_OPT_IN":"YES",
               "MRM_AMAP_JS_KEY":"FAKE_JS_KEY", "MRM_AMAP_JS_SECURITY":"FAKE_SECURITY",
               "MRM_AMAP_MAP_OPT_IN":"YES"}
        with tempfile.TemporaryDirectory() as tmp:
            gw = LiveGateway(tmp, env=env)
            self.assertTrue(gw.map_enabled())
            self.assertEqual(gw.status()["remaining_map_initializations"], 30)
            gw.reserve_map_initialization()
            self.assertEqual(gw.status()["remaining_map_initializations"], 29)
            again = LiveGateway(tmp, env=env)
            self.assertEqual(again.status()["remaining_map_initializations"], 29)

    def test_corrupt_monthly_counter_fails_closed(self):
        env = {"MRM_AMAP_WEB_KEY":"FAKE", "MRM_USAGE_AUTHORIZED":"YES",
               "MRM_FREE_QUOTA_VERIFIED":"YES", "MRM_EXPLICIT_LIVE_OPT_IN":"YES"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local" / "amap_request_attempts.json"
            path.parent.mkdir()
            path.write_text('{"day":"not-a-date","day_count":0,"month":"2026-11","month_count":0}')
            gw = LiveGateway(tmp, env=env)
            self.assertFalse(gw.status()["live_enabled"])
            with self.assertRaises(Disabled):
                gw.drive(COORDS)


if __name__ == "__main__":
    unittest.main()
