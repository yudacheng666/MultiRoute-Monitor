"""Local-only, interactive secret configuration; no network calls and no opt-in.

Usage from project folder: python setup_amap.py

Values are stored under local/amap_keys.json, which .gitignore excludes.
This never enables live requests or map tile loading.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import sys
from pathlib import Path

FIELDS = ("MRM_AMAP_WEB_KEY", "MRM_AMAP_JS_KEY", "MRM_AMAP_JS_SECURITY")
MAX_LENGTH = 256
VALUE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,256}$")


def private_key_path(root):
    return Path(root) / "local" / "amap_keys.json"


def read_private_keys(root):
    """Fail closed when missing/malformed; never include permissions or opt-in."""
    target = private_key_path(root)
    try:
        if target.is_symlink():
            return {}
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {name: data[name] for name in FIELDS
            if isinstance(data.get(name), str) and VALUE_PATTERN.fullmatch(data[name])}


def save_private_keys(root, values):
    if not isinstance(values, dict) or any(k not in FIELDS for k in values):
        raise ValueError("不支持的配置项")
    clean = {name:value for name,value in values.items()
             if isinstance(value, str) and VALUE_PATTERN.fullmatch(value)}
    if len(clean) != len(values):
        raise ValueError("Key/安全密钥格式有误，请检查复制内容")
    target = private_key_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("私有配置路径不得是符号链接")
    tmp = target.with_suffix(".tmp")
    if tmp.is_symlink():
        raise ValueError("临时路径不得是符号链接")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(clean, out, ensure_ascii=False)
        os.replace(tmp, target)
        if os.name != "nt":
            os.chmod(target, 0o600)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return target



AUTH_TICKET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,80}$")
AUTH_FLAGS_DISABLED = {
    "MRM_USAGE_AUTHORIZED": "NO",
    "MRM_FREE_QUOTA_VERIFIED": "NO",
    "MRM_EXPLICIT_LIVE_OPT_IN": "NO",
    "MRM_AMAP_MAP_OPT_IN": "NO",
}


def authorization_path(root):
    return Path(root) / "local" / "amap_authorization.json"


def _write_private_json(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("私有配置路径不得是符号链接")
    pending = target.with_suffix(".tmp")
    if pending.is_symlink():
        raise ValueError("临时路径不得是符号链接")
    try:
        fd = os.open(str(pending), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False)
        os.replace(pending, target)
        if os.name != "nt":
            os.chmod(target, 0o600)
    finally:
        try:
            pending.unlink(missing_ok=True)
        except OSError:
            pass


def save_private_authorization(root, payload):
    """Persist a local self-attestation only after the user confirms AMap approval.

    The application cannot verify the provider's ticket or account-level usage.
    It therefore requires explicit attestations and applies a 50% quota reserve.
    """
    if not isinstance(payload, dict):
        raise ValueError("授权数据格式错误")
    ticket = payload.get("ticket_id")
    route_remaining = payload.get("route_quota_remaining")
    map_remaining = payload.get("map_quota_remaining")
    confirmations = (
        "personal_developer_verified", "approved_by_amap", "quota_verified", "account_exclusive", "zero_cost_ack"
    )
    if not isinstance(ticket, str) or not AUTH_TICKET_PATTERN.fullmatch(ticket.strip()):
        raise ValueError("请填写有效的高德工单编号")
    if any(payload.get(field) is not True for field in confirmations):
        raise ValueError("必须确认高德书面许可、账户剩余额度、账号独占使用和费用风险")
    for value, label in ((route_remaining, "驾车规划"), (map_remaining, "地图初始化")):
        if not isinstance(value, int) or isinstance(value, bool) or value < 2 or value > 100000000:
            raise ValueError(label + "剩余免费额度必须是有效整数")
    # Keep at least half of the user-reported remaining free quota unused.
    route_monthly = min(30000, route_remaining // 2)
    map_monthly = min(900, map_remaining // 2)
    if route_monthly < 1 or map_monthly < 1:
        raise ValueError("当前剩余额度不足，真实高德保持关闭")
    route_daily = min(1000, max(1, route_monthly // 30))
    map_daily = min(30, max(1, map_monthly // 30))
    record = {
        "enabled": True,
        "ticket_id": ticket.strip(),
        "route_quota_remaining_at_enable": route_remaining,
        "map_quota_remaining_at_enable": map_remaining,
        "route_daily_cap": route_daily,
        "route_monthly_cap": route_monthly,
        "map_daily_cap": map_daily,
        "map_monthly_cap": map_monthly,
        "personal_developer_verified": True,
        "approved_by_amap": True,
        "quota_verified": True,
        "account_exclusive": True,
        "zero_cost_ack": True,
    }
    _write_private_json(authorization_path(root), record)
    return record


def disable_private_authorization(root):
    """Persist an explicit off marker that overrides environment opt-in flags."""
    _write_private_json(authorization_path(root), {"disabled": True})


def read_private_authorization(root):
    """Return only validated runtime switches; never return ticket/quota metadata."""
    target = authorization_path(root)
    if target.is_symlink():
        return dict(AUTH_FLAGS_DISABLED)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return dict(AUTH_FLAGS_DISABLED)
    if not isinstance(data, dict):
        return dict(AUTH_FLAGS_DISABLED)
    if data.get("disabled") is True:
        return dict(AUTH_FLAGS_DISABLED)
    ticket = data.get("ticket_id")
    route_daily, route_monthly = data.get("route_daily_cap"), data.get("route_monthly_cap")
    map_daily, map_monthly = data.get("map_daily_cap"), data.get("map_monthly_cap")
    route_remaining = data.get("route_quota_remaining_at_enable")
    map_remaining = data.get("map_quota_remaining_at_enable")
    numeric = (route_daily, route_monthly, map_daily, map_monthly,
               route_remaining, map_remaining)
    if (data.get("enabled") is not True
            or not isinstance(ticket, str) or not AUTH_TICKET_PATTERN.fullmatch(ticket)
            or any(data.get(field) is not True for field in (
                "personal_developer_verified", "approved_by_amap", "quota_verified", "account_exclusive", "zero_cost_ack"))
            or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in numeric)
            or route_remaining > 100000000 or map_remaining > 100000000
            or route_monthly != min(30000, route_remaining // 2)
            or map_monthly != min(900, map_remaining // 2)
            or route_daily != min(1000, max(1, route_monthly // 30))
            or map_daily != min(30, max(1, map_monthly // 30))):
        return dict(AUTH_FLAGS_DISABLED)
    return {
        "MRM_USAGE_AUTHORIZED": "YES",
        "MRM_FREE_QUOTA_VERIFIED": "YES",
        "MRM_EXPLICIT_LIVE_OPT_IN": "YES",
        "MRM_AMAP_MAP_OPT_IN": "YES",
        "MRM_DAILY_REQUEST_CAP": str(route_daily),
        "MRM_MONTHLY_REQUEST_CAP": str(route_monthly),
        "MRM_MAP_INIT_DAILY_CAP": str(map_daily),
        "MRM_MAP_INIT_MONTHLY_CAP": str(map_monthly),
    }


def main():
    root = Path(__file__).resolve().parent
    print("MultiRoute-Monitor 高德本地配置（不会连接高德或启用真实请求）")
    print("请在本机分别填写两种 Key 与 JS 安全密钥；内容不会回显。")
    print("第三项“JS安全密钥”在高德 Web端(JS API) Key 旁边，不是第三个 Key。")
    print("按回车可保留已填写的旧值；首次可留空以后补填。")
    old = read_private_keys(root)
    labels = (
        ("MRM_AMAP_WEB_KEY", "1/3 Web服务 Key"),
        ("MRM_AMAP_JS_KEY", "2/3 Web端(JS API) Key"),
        ("MRM_AMAP_JS_SECURITY", "3/3 JS安全密钥 securityJsCode"),
    )
    chosen = dict(old)
    try:
        for name,label in labels:
            prompt = label + ("（已存在，可直接回车保留）: " if name in old else "（可回车跳过）: ")
            value = getpass.getpass(prompt).strip()
            if value:
                if not VALUE_PATTERN.fullmatch(value):
                    print("输入格式不符合要求；没有改写已有文件。")
                    return 1
                chosen[name] = value
        if not chosen:
            print("未填写任何 Key；仍为模拟模式，无需操作。")
            return 0
        save_private_keys(root, chosen)
    except (KeyboardInterrupt, EOFError):
        print("\n已取消；原配置保持不变。")
        return 1
    except (ValueError, OSError) as e:
        print("保存失败：" + str(e))
        return 1
    print("已保存到本机 local/amap_keys.json（Git 已忽略该文件）。")
    print("真实高德调用仍然关闭。不要把此文件、Key或安全密钥发到聊天或上传 GitHub。")
    print("下一步：保持模拟模式，等待授权和免费配额核实。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
