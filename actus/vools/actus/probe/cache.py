"""probe/cache.py — 探测结果缓存。"""


__all__ = [
    "load_cache",
    "save_cache",
    "invalidate_cache",
]

import json
import os
import time
from typing import Optional

# 缓存文件路径
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "_meta")
_CACHE_FILE = os.path.join(_CACHE_DIR, "probe_cache.json")
_CACHE_TTL = 3600  # 1 小时过期


def _ensure_cache_dir():
    """确保缓存目录存在。"""
    os.makedirs(_CACHE_DIR, exist_ok=True)


def load_cache(force_refresh: bool = False, max_age: int = None) -> Optional[dict]:
    """加载缓存。返回 None 表示缓存无效或不存在。"""
    max_age = max_age or _CACHE_TTL
    if force_refresh:
        return None
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("timestamp", 0) > max_age:
            return None
        return data
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def save_cache(report: dict) -> bool:
    """保存探测结果到缓存。

    必须持久化全部维度：probe() 从缓存重建 ProbeReport 时按
    platform/permissions/environment/resources 四个键回填，若这里不落盘，
    第二次 probe() 命中缓存后这四个维度全部为空 dict（实测缓存往返丢失）。
    """
    try:
        _ensure_cache_dir()
        data = {
            "timestamp": time.time(),
            "elapsed_ms": report.get("elapsed_ms", 0),
            "platform": report.get("platform", {}),
            "permissions": report.get("permissions", {}),
            "environment": report.get("environment", {}),
            "resources": report.get("resources", {}),
            "summary": report.get("summary", {}),
            "items": report.get("items", []),
        }
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def invalidate_cache():
    """清除缓存。"""
    try:
        if os.path.exists(_CACHE_FILE):
            os.remove(_CACHE_FILE)
    except OSError:
        pass
