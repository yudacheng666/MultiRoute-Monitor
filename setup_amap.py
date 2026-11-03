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
