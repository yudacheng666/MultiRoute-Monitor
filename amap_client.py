"""AMap v5 driving route adapter. No network call until explicit, verified local opt-in.

No provider route geometry, ETA, or traffic status is stored on disk.
Only cumulative request attempts are persisted to enforce a conservative daily cap.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import math
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode
from setup_amap import read_private_keys
CHINA_TZ = timezone(timedelta(hours=8))

ENDPOINT = "restapi.amap.com"
PATH = "/v5/direction/driving"
KNOWN_STATUS = frozenset({"未知", "畅通", "缓行", "拥堵", "严重拥堵"})
DAILY_CAP = 1000
MONTHLY_CAP = 30000
MAP_INIT_DAILY_CAP = 30
MAP_INIT_MONTHLY_CAP = 900
MAP_PROXY_DAILY_CAP = 500
MAP_PROXY_MONTHLY_CAP = 15000
MIN_GLOBAL_SECONDS = 2
MIN_ROUTE_SECONDS = 300
MAX_RESPONSE_BYTES = 1_000_000


class RouteInputError(ValueError):
    pass


class ProviderError(RuntimeError):
    pass


class RateLimited(RuntimeError):
    pass


class Disabled(RuntimeError):
    pass


def coord(value):
    """Validate lng,lat string without silently inventing coordinates."""
    if not isinstance(value, str):
        raise RouteInputError("坐标必须填写经度,纬度")
    parts = value.strip().split(",")
    if len(parts) != 2:
        raise RouteInputError("坐标格式应为 经度,纬度")
    numbers = []
    for i, raw in enumerate(parts):
        raw = raw.strip()
        if not raw or len(raw) > 20:
            raise RouteInputError("坐标格式错误")
        try:
            d = Decimal(raw)
        except InvalidOperation as exc:
            raise RouteInputError("坐标应为有限数字") from exc
        if not d.is_finite() or abs(d) > (180 if i == 0 else 90):
            raise RouteInputError("经纬度超出范围")
        if d.as_tuple().exponent < -6:
            raise RouteInputError("经纬度最多6位小数")
        numbers.append(format(d, "f"))
    return ",".join(numbers)


def validate_request(data):
    if not isinstance(data, dict):
        raise RouteInputError("路线参数应为对象")
    start = coord(data.get("origin"))
    end = coord(data.get("destination"))
    if start == end:
        raise RouteInputError("起终点不能相同")
    waypoints = data.get("waypoints", [])
    if waypoints is None:
        waypoints = []
    if not isinstance(waypoints, list) or len(waypoints) > 1:
        raise RouteInputError("首版最多支持1个途经点")
    return {"origin": start, "destination": end,
            "waypoints": [coord(p) for p in waypoints]}


def query_path(request, key):
    if not isinstance(key, str) or not key or len(key) > 256:
        raise Disabled("未配置有效的 Web 服务 Key")
    fields = {
        "key": key, "origin": request["origin"], "destination": request["destination"],
        "strategy": "32", "show_fields": "cost,tmcs,polyline", "output": "json",
    }
    if request["waypoints"]:
        fields["waypoints"] = ";".join(request["waypoints"])
    return PATH + "?" + urlencode(fields)


def parse_polyline(raw):
    if not isinstance(raw, str) or not raw:
        return []
    parts = raw.split(";")
    if len(parts) > 1500:
        raise ProviderError("道路数据过长")
    try:
        return [list(map(float, coord(point).split(","))) for point in parts]
    except RouteInputError as exc:
        raise ProviderError("地图线路坐标无效") from exc


def parse_driving(payload):
    if not isinstance(payload, dict) or payload.get("status") != "1":
        raise ProviderError("高德路径规划返回失败")
    routes = payload.get("route")
    paths = routes.get("paths") if isinstance(routes, dict) else None
    if not isinstance(paths, list) or not paths or not isinstance(paths[0], dict):
        raise ProviderError("高德返回的路线为空")
    path = paths[0]
    cost = path.get("cost")
    duration_raw = cost.get("duration") if isinstance(cost, dict) else None
    try:
        seconds = float(duration_raw)
        distance = float(path.get("distance"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProviderError("缺少有效耗时或距离") from exc
    if not all(math.isfinite(x) and x > 0 for x in (seconds, distance)):
        raise ProviderError("返回的距离或耗时无效")
    steps = path.get("steps")
    if not isinstance(steps, list):
        raise ProviderError("缺少路线道路分段")
    segments = []
    for step in steps[:500]:
        if not isinstance(step, dict):
            continue
        tmcs = step.get("tmcs") or []
        if not isinstance(tmcs, list):
            raise ProviderError("路况分段格式错误")
        for tmc in tmcs[:500]:
            if not isinstance(tmc, dict):
                continue
            geom = parse_polyline(tmc.get("tmc_polyline"))
            if len(geom) < 2:
                continue
            segments.append({"status": tmc.get("tmc_status") if tmc.get("tmc_status") in KNOWN_STATUS
                             else "未知", "points": geom})
            if len(segments) >= 500:
                break
        if len(segments) >= 500:
            break
    if not segments:
        # Never invent a traffic status. Geometry can still be displayed as '未知'.
        for step in steps[:500]:
            if isinstance(step, dict):
                geom = parse_polyline(step.get("polyline"))
                if len(geom) >= 2:
                    segments.append({"status": "未知", "points": geom})
    return {
        "source": "AMAP", "eta_minutes": math.ceil(seconds / 60),
        "distance_km": round(distance / 1000, 2),
        "segments": segments,
        "traffic_available": any(x["status"] != "未知" for x in segments),
        "fetched_at": datetime.now(CHINA_TZ).isoformat(timespec="seconds"),
    }


def fixed_host_fetch(path):
    """Never follow redirects or accept caller-supplied URLs; no API key in exceptions."""
    conn = http.client.HTTPSConnection(ENDPOINT, timeout=8)
    try:
        conn.request("GET", path, headers={"Accept": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise ProviderError("高德服务暂时不可用")
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ProviderError("高德响应超过安全限制")
        try:
            return json.loads(data)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProviderError("高德响应不是有效 JSON") from exc
    except (OSError, TimeoutError) as exc:
        raise ProviderError("高德网络请求失败") from exc
    finally:
        conn.close()


class LiveGateway:
    def __init__(self, root, env=None, transport=None, clock=None):
        # Only normal local startup reads private keys. Offline tests injecting env={}
        # never see machine credentials. Permission/fee switches remain separate.
        if env is None:
            env = {**read_private_keys(root), **os.environ}
        self.key = env.get("MRM_AMAP_WEB_KEY", "")
        self.js_key = env.get("MRM_AMAP_JS_KEY", "")
        self.js_security = env.get("MRM_AMAP_JS_SECURITY", "")
        self.map_explicit = env.get("MRM_AMAP_MAP_OPT_IN") == "YES"
        self.authorized = (env.get("MRM_USAGE_AUTHORIZED") == "YES"
                           and env.get("MRM_FREE_QUOTA_VERIFIED") == "YES"
                           and env.get("MRM_EXPLICIT_LIVE_OPT_IN") == "YES")
        self.enabled = bool(self.authorized and self.key)
        self.transport = transport or fixed_host_fetch
        self.clock = clock or time.time
        self._lock = threading.Lock()
        self._last_global = 0.0
        self._last_route = {}
        local_dir = Path(root) / "local"
        self.usage_file = local_dir / "amap_request_attempts.json"
        self.map_usage_file = local_dir / "amap_map_proxy_attempts.json"
        self.map_init_usage_file = local_dir / "amap_map_initialization_attempts.json"
        self.map_init_daily_cap = MAP_INIT_DAILY_CAP
        self.map_init_monthly_cap = MAP_INIT_MONTHLY_CAP
        self.map_proxy_daily_cap = MAP_PROXY_DAILY_CAP
        self.map_proxy_monthly_cap = MAP_PROXY_MONTHLY_CAP
        try:
            requested = int(env.get("MRM_DAILY_REQUEST_CAP", "1000"))
        except (TypeError, ValueError):
            requested = 0
        try:
            requested_monthly = int(env.get("MRM_MONTHLY_REQUEST_CAP", str(MONTHLY_CAP)))
        except (TypeError, ValueError):
            requested_monthly = 0
        self.cap = min(DAILY_CAP, max(0, requested))
        self.monthly_cap = min(MONTHLY_CAP, max(0, requested_monthly))
        if self.cap <= 0 or self.monthly_cap <= 0:
            self.enabled = False

    def _day(self):
        return datetime.now(CHINA_TZ).date().isoformat()

    def _month(self):
        return self._day()[:7]

    def _usage(self, path=None):
        return self._read_usage(self.usage_file if path is None else path)

    def _read_usage(self, path):
        today, month = self._day(), self._month()
        if not path.exists():
            return {"day": today, "day_count": 0, "month": month, "month_count": 0}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError()
            # Migrate the previous {day,count} format conservatively. Its last
            # recorded count is carried into this month's counter rather than lost.
            if "day_count" not in data or "month_count" not in data:
                saved_day = data.get("day")
                old_count = data.get("count")
                if (not isinstance(saved_day, str) or not isinstance(old_count, int)
                        or isinstance(old_count, bool) or old_count < 0):
                    raise ValueError()
                saved_date = datetime.strptime(saved_day, "%Y-%m-%d").date()
                current_date = datetime.strptime(today, "%Y-%m-%d").date()
                if saved_date > current_date:
                    raise ValueError()
                carry = old_count if saved_day[:7] == month else 0
                return {"day": today, "day_count": old_count if saved_day == today else 0,
                        "month": month, "month_count": carry}
            saved_day, saved_month = data.get("day"), data.get("month")
            day_count, month_count = data.get("day_count"), data.get("month_count")
            if (not isinstance(saved_day, str) or not isinstance(saved_month, str)
                    or not isinstance(day_count, int) or isinstance(day_count, bool) or day_count < 0
                    or not isinstance(month_count, int) or isinstance(month_count, bool) or month_count < 0):
                raise ValueError()
            saved_date = datetime.strptime(saved_day, "%Y-%m-%d").date()
            current_date = datetime.strptime(today, "%Y-%m-%d").date()
            if saved_date > current_date or saved_month > month or saved_month != saved_day[:7]:
                raise ValueError()
            return {
                "day": today,
                "day_count": day_count if saved_day == today else 0,
                "month": month,
                "month_count": month_count if saved_month == month else 0,
            }
        except (OSError, ValueError, TypeError) as exc:
            raise Disabled("本地配额计数异常，已停止真实调用") from exc

    def _reserve(self, usage, path=None):
        path = self.usage_file if path is None else path
        path.parent.mkdir(parents=True, exist_ok=True)
        pending = path.with_suffix(".tmp")
        record = {
            "day": self._day(),
            "day_count": usage["day_count"] + 1,
            "month": self._month(),
            "month_count": usage["month_count"] + 1,
        }
        try:
            fd = os.open(str(pending), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(record, out)
            os.replace(pending, path)
            if os.name != "nt":
                os.chmod(path, 0o600)
        except OSError as exc:
            raise Disabled("无法持久化请求计数，已停止真实调用") from exc
        finally:
            try:
                pending.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _remaining(usage, daily_cap, monthly_cap):
        return (max(0, daily_cap - usage["day_count"]),
                max(0, monthly_cap - usage["month_count"]))

    def _safe_usage(self, path):
        try:
            return self._usage(path), True
        except Disabled:
            return {"day": self._day(), "day_count": 0,
                    "month": self._month(), "month_count": 0}, False

    def map_enabled(self):
        if not (self.enabled and self.map_explicit and self.js_key and self.js_security):
            return False
        init_usage, init_ok = self._safe_usage(self.map_init_usage_file)
        proxy_usage, proxy_ok = self._safe_usage(self.map_usage_file)
        if not init_ok or not proxy_ok:
            return False
        init_day, init_month = self._remaining(
            init_usage, self.map_init_daily_cap, self.map_init_monthly_cap)
        proxy_day, proxy_month = self._remaining(
            proxy_usage, self.map_proxy_daily_cap, self.map_proxy_monthly_cap)
        return min(init_day, init_month, proxy_day, proxy_month) > 0

    def reserve_map_initialization(self):
        if not self.map_enabled():
            raise Disabled("地图组件尚未授权启用或已达到地图预算")
        with self._lock:
            usage = self._usage(self.map_init_usage_file)
            daily, monthly = self._remaining(
                usage, self.map_init_daily_cap, self.map_init_monthly_cap)
            if daily <= 0 or monthly <= 0:
                raise RateLimited("地图初始化达到本机日/月硬上限")
            self._reserve(usage, self.map_init_usage_file)

    def reserve_map_proxy(self):
        if not self.map_enabled():
            raise Disabled("地图组件尚未授权启用或已达到地图预算")
        with self._lock:
            usage = self._usage(self.map_usage_file)
            daily, monthly = self._remaining(
                usage, self.map_proxy_daily_cap, self.map_proxy_monthly_cap)
            if daily <= 0 or monthly <= 0:
                raise RateLimited("地图代理请求达到本机日/月硬上限")
            self._reserve(usage, self.map_usage_file)

    def status(self):
        with self._lock:
            route_usage, route_ok = self._safe_usage(self.usage_file)
            map_usage, map_ok = self._safe_usage(self.map_usage_file)
            init_usage, init_ok = self._safe_usage(self.map_init_usage_file)
            remaining, monthly_remaining = self._remaining(
                route_usage, self.cap, self.monthly_cap)
            map_proxy_remaining, map_proxy_monthly = self._remaining(
                map_usage, self.map_proxy_daily_cap, self.map_proxy_monthly_cap)
            map_init_remaining, map_init_monthly = self._remaining(
                init_usage, self.map_init_daily_cap, self.map_init_monthly_cap)
            live_enabled = bool(self.enabled and route_ok and remaining > 0
                                and monthly_remaining > 0)
            map_enabled = bool(live_enabled and self.map_explicit and self.js_key
                               and self.js_security and map_ok and init_ok
                               and map_proxy_remaining > 0 and map_proxy_monthly > 0
                               and map_init_remaining > 0 and map_init_monthly > 0)
            return {
                "live_enabled": live_enabled,
                "mode": "live_ready" if live_enabled else "simulation",
                "daily_request_cap": self.cap,
                "monthly_request_cap": self.monthly_cap,
                "remaining_app_budget": remaining if route_ok else 0,
                "remaining_monthly_app_budget": monthly_remaining if route_ok else 0,
                "requires_verified_authorization": True,
                "js_map_enabled": map_enabled,
                "js_map_key": self.js_key if map_enabled else None,
                "map_initialization_daily_cap": self.map_init_daily_cap,
                "map_initialization_monthly_cap": self.map_init_monthly_cap,
                "remaining_map_initializations": map_init_remaining if init_ok else 0,
                "remaining_monthly_map_initializations": map_init_monthly if init_ok else 0,
                "remaining_map_proxy_budget": map_proxy_remaining if map_ok else 0,
                "remaining_monthly_map_proxy_budget": map_proxy_monthly if map_ok else 0,
            }

    def drive(self, data):
        # Permission check must come before validation and any network activity.
        if not self.enabled:
            raise Disabled("高德真实模式尚未授权启用")
        spec = validate_request(data)
        token = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        with self._lock:
            usage = self._usage()
            daily, monthly = self._remaining(usage, self.cap, self.monthly_cap)
            if daily <= 0 or monthly <= 0:
                raise RateLimited("已达到应用内高德日/月硬上限")
            now = self.clock()
            if now - self._last_global < MIN_GLOBAL_SECONDS:
                raise RateLimited("请求过于频繁，请稍后操作")
            if now - self._last_route.get(token, -1e12) < MIN_ROUTE_SECONDS:
                raise RateLimited("同一路线5分钟内不得重复查询")
            self._reserve(usage)  # Count attempts BEFORE network, even failed requests.
            self._last_global = now
            self._last_route[token] = now
        return parse_driving(self.transport(query_path(spec, self.key)))
