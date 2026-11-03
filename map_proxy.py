"""Restricted AMap JS API security-code proxy for local PERSONAL use only.

Uses official same-origin /_AMapService prefix and keeps jscode on the server.
This is not a public proxy and does not permit caller-specified upstream hosts.
"""
from __future__ import annotations
import http.client
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from amap_client import Disabled, ProviderError

PREFIX = "/_AMapService/"
WEB_SERVICE_UPSTREAM = "restapi.amap.com"
STYLE_UPSTREAM = "webapi.amap.com"
# Restrict outgoing endpoints instead of creating an arbitrary forwarding proxy.
WEB_SERVICE_PATH = re.compile(r"^/v3/(?:assistant|place|geocode|direction|distance|config)/[a-zA-Z0-9/_-]{1,120}$")
STYLE_PATH = re.compile(r"^/v4/map/styles(?:/[a-zA-Z0-9/_-]{1,120})?$")
ALLOWED = (WEB_SERVICE_PATH, STYLE_PATH)
MAX_BYTES = 1_000_000

def prepare_proxy_path(target, security_code):
    if not isinstance(security_code, str) or not security_code or len(security_code) > 256:
        raise Disabled("高德地图安全码未配置")
    url = urlsplit(target)
    if url.scheme or url.netloc or url.fragment or not url.path.startswith(PREFIX) or len(target) > 1800:
        raise ValueError("路径不在地图代理白名单内")
    path = url.path[len(PREFIX)-1:]
    if not any(pattern.fullmatch(path) for pattern in ALLOWED):
        raise ValueError("地图代理路径未获允许")
    pairs = parse_qsl(url.query, keep_blank_values=True, max_num_fields=40)
    if any(k.lower() in ("jscode", "securityjscode", "callback") for k,_ in pairs):
        raise ValueError("地图代理参数不允许")
    return path + "?" + urlencode(pairs + [("jscode", security_code)])

def select_upstream(upstream_path):
    """Select only one of two documented AMap hosts; never trust a URL host."""
    if not isinstance(upstream_path, str):
        raise ValueError("上游路径无效")
    parts = urlsplit(upstream_path)
    if parts.scheme or parts.netloc or parts.fragment:
        raise ValueError("不接受外部绝对地址")
    if STYLE_PATH.fullmatch(parts.path):
        return STYLE_UPSTREAM
    if WEB_SERVICE_PATH.fullmatch(parts.path):
        return WEB_SERVICE_UPSTREAM
    raise ValueError("上游资源不在白名单内")


def proxy_get(upstream_path):
    # Map styles use webapi.amap.com; supported Web Service uses restapi.amap.com.
    # Exact fixed-host selection is validated again here, even if called directly.
    host = select_upstream(upstream_path)
    conn = http.client.HTTPSConnection(host, timeout=8)
    try:
        conn.request("GET", upstream_path, headers={
            "Accept": "*/*", "Accept-Encoding": "identity"
        })
        res = conn.getresponse()
        if res.status != 200:
            raise ProviderError("高德地图服务响应失败")
        body = res.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ProviderError("高德地图代理响应超过限制")
        kind = res.getheader("Content-Type", "application/json").split(";")[0].strip().lower()
        if kind not in ("application/json", "text/plain", "image/png", "image/jpeg",
                        "application/javascript", "text/javascript", "application/octet-stream"):
            raise ProviderError("高德地图响应类型不允许")
        return body, kind
    except OSError as exc:
        raise ProviderError("高德地图代理连接失败") from exc
    finally:
        conn.close()
