"""Restricted AMap JS API security-code proxy for local personal use.

Matches the official JS API 2.0 proxy split:
- /_AMapService/v4/map/styles -> https://webapi.amap.com/v4/map/styles
- other supported /v3/* and /v4/* Web Service resources -> https://restapi.amap.com/

The browser never supplies an upstream host and never receives securityJsCode.
"""
from __future__ import annotations

import http.client
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from amap_client import Disabled, ProviderError

PREFIX = "/_AMapService/"
WEB_SERVICE_UPSTREAM = "restapi.amap.com"
STYLE_UPSTREAM = "webapi.amap.com"

# The official JS API proxy uses a catch-all /_AMapService/ route for Web
# Services. Keep that behavior for versioned API paths while rejecting
# encoded separators, dot segments, backslashes, and arbitrary URL hosts.
WEB_SERVICE_PATH = re.compile(
    r"^/v[34]/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$"
)
STYLE_PATH = re.compile(
    r"^/v4/map/styles(?:/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*)?$"
)
MAX_BYTES = 1_000_000
MAX_TARGET_LENGTH = 1800
ALLOWED_CONTENT_TYPES = frozenset({
    "application/json", "text/plain", "image/png", "image/jpeg",
    "image/webp", "image/gif", "application/javascript",
    "text/javascript", "application/octet-stream",
})


def prepare_proxy_path(target, security_code):
    if not isinstance(security_code, str) or not security_code or len(security_code) > 256:
        raise Disabled("高德地图安全码未配置")
    if not isinstance(target, str) or len(target) > MAX_TARGET_LENGTH:
        raise ValueError("地图代理请求无效")
    url = urlsplit(target)
    if (url.scheme or url.netloc or url.fragment or "\\" in url.path
            or not url.path.startswith(PREFIX)):
        raise ValueError("路径不在地图代理白名单内")
    path = url.path[len(PREFIX) - 1:]
    if not (STYLE_PATH.fullmatch(path) or WEB_SERVICE_PATH.fullmatch(path)):
        raise ValueError("地图代理路径未获允许")
    try:
        pairs = parse_qsl(url.query, keep_blank_values=True, max_num_fields=40)
    except ValueError as exc:
        raise ValueError("地图代理参数数量超限") from exc
    if any(k.lower() in ("jscode", "securityjscode", "callback") for k, _ in pairs):
        raise ValueError("地图代理参数不允许")
    return path + "?" + urlencode(pairs + [("jscode", security_code)])


def select_upstream(upstream_path):
    """Select only one of two documented AMap hosts; never trust a URL host."""
    if not isinstance(upstream_path, str):
        raise ValueError("上游路径无效")
    parts = urlsplit(upstream_path)
    if parts.scheme or parts.netloc or parts.fragment or "\\" in parts.path:
        raise ValueError("不接受外部绝对地址")
    if STYLE_PATH.fullmatch(parts.path):
        return STYLE_UPSTREAM
    if WEB_SERVICE_PATH.fullmatch(parts.path):
        return WEB_SERVICE_UPSTREAM
    raise ValueError("上游资源不在白名单内")


def proxy_get(upstream_path):
    """GET a fixed AMap host; never follow redirects or forward provider headers."""
    host = select_upstream(upstream_path)
    conn = None
    try:
        conn = http.client.HTTPSConnection(host, timeout=8)
        conn.request("GET", upstream_path, headers={
            "Accept": "*/*", "Accept-Encoding": "identity",
        })
        response = conn.getresponse()
        if response.status != 200:
            # In particular, do not follow redirects to an untrusted host.
            raise ProviderError("高德地图服务响应失败")
        declared = response.getheader("Content-Length")
        if declared:
            try:
                if int(declared) > MAX_BYTES:
                    raise ProviderError("高德地图代理响应超过限制")
            except ValueError:
                raise ProviderError("高德地图响应长度无效")
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ProviderError("高德地图代理响应超过限制")
        raw_type = response.getheader("Content-Type", "application/json")
        kind = raw_type.split(";", 1)[0].strip().lower()
        if kind not in ALLOWED_CONTENT_TYPES:
            raise ProviderError("高德地图响应类型不允许")
        return body, kind
    except ProviderError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise ProviderError("高德地图代理连接失败") from exc
    finally:
        if conn is not None:
            conn.close()
