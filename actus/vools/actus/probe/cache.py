"""probe/cache.py — 探测结果缓存（schema 版本化 / 原子写 / 优雅降级）。

缓存语义（本模块是唯一真源，`probe()` 只按 `None` / 非 `None` 分支处理）：

* **快照，不是状态**：默认 1 小时（`_CACHE_TTL`），`probe(max_age=...)` 覆盖。
  `max_age <= 0` 明确表示「不复用缓存」（改前 `max_age or _CACHE_TTL` 会把 0
  当成「没传」，于是 `--max-age 0` 静默复用 1 小时旧数据）。
* **版本化**：payload 必须带 `schema_version`，与 `CACHE_SCHEMA_VERSION`
  （= `report.REPORT_SCHEMA_VERSION`）不一致一律视为无缓存。探测结构变了
  （新增 section / 维度改名 / items 字段变动）时，旧缓存不会冒充新报告 ——
  否则用户会因为「缓存里没有新段」而看不到新探测项，且要等满 TTL 才自愈。
* **优雅降级**：文件缺失 / JSON 损坏 / 顶层不是对象 / 时间戳非数 / 维度缺失 /
  items 形状错乱 / 时钟回拨（时间戳在未来），一律返回 `None`（＝无缓存），
  **绝不把异常抛给 probe()**。改前 `[]` 会抛 AttributeError、`{"timestamp":"x"}`
  会抛 TypeError，整条 probe() 直接炸掉。
* **原子写**：先 `json.dumps` 再写同目录临时文件、最后 `os.replace`。改前直接
  `json.dump` 落盘，遇到不可序列化的值（或进程被 kill）会留下半截 JSON，
  下一次读缓存就走异常路径。

缓存文件位置（可测性/可重定向，本轮修复）
------------------------------------------
改前：`_CACHE_DIR` 是 import 时用 `__file__` 硬算出来的模块级常量，**完全不读
`ACTUS_META_DIR`** —— 而 actus 其它模块（`cli.py` 的 `_meta`、`export.py` 的
`meta_dir`、`cost.py` 的 `COSTS_DIR`）都遵循「`ACTUS_META_DIR` 优先」的约定。
三个真实后果：
  1. **测试隔离不掉**：测试里 `ACTUS_META_DIR=tmp` 挡不住 probe 缓存，真跑 probe
     会写进仓库的 `actus/_meta/probe_cache.json`；
  2. **用户重定向不了**：把 `_meta` 挪走（只读仓库 / 多项目共存）后，probe 缓存
     仍写原处；
  3. **打包安装后**会把缓存算到 site-packages 里的 `_meta`，那里可能不可写。

改后：路径改成**函数式解析**（`_cache_dir()` / `_cache_path()`，每次调用重新解析），
优先级（**先后顺序即语义，写死在这里**）：
  1. 模块属性 `_CACHE_FILE` / `_CACHE_DIR` **被显式改过**（测试用
     `monkeypatch.setattr` 隔离）→ 用它，保证既有测试与外部代码不受影响；
  2. `paths.meta_dir()`（**唯一真源**）：`ACTUS_META_DIR` → 用它；
     否则 `ACTUS_REPO_ROOT/_meta`；再否则 `__file__` 推导（三者都由 paths 解析）；
  3. 都没有 → 与改前**逐字相同**的 `__file__` 推导（`<repo_root>/_meta`）。
`_CACHE_FILE` / `_CACHE_DIR` 作为「默认值」继续保留（外部有引用，不能删）。
"""

__all__ = [
    "load_cache",
    "save_cache",
    "invalidate_cache",
    "cache_info",
    "CACHE_SCHEMA_VERSION",
]

import json
import os
import tempfile
import time
from typing import Optional

from ..paths import DEFAULT_REPO_ROOT, meta_dir
from .report import REPORT_SCHEMA_VERSION

# 缓存文件名（目录可变，文件名不变）
_CACHE_FILENAME = "probe_cache.json"


# 默认值（兼容保留：外部/测试一直用 monkeypatch.setattr 改这两个名字来隔离缓存）。
# 注意：这里用**不含环境变量**的常量做基线，_cache_path() 里靠「是否等于基线」
# 判断模块属性有没有被显式改过；真正生效的目录由 paths.meta_dir() 在调用时解析。
_DEFAULT_CACHE_DIR = os.path.join(DEFAULT_REPO_ROOT, "_meta")
_DEFAULT_CACHE_FILE = os.path.join(_DEFAULT_CACHE_DIR, _CACHE_FILENAME)
_CACHE_DIR = _DEFAULT_CACHE_DIR
_CACHE_FILE = _DEFAULT_CACHE_FILE

_CACHE_TTL = 3600  # 1 小时过期


def _cache_dir() -> str:
    """解析缓存目录（优先级见模块 docstring：显式 monkeypatch > ACTUS_META_DIR > 默认）。"""
    if _CACHE_FILE != _DEFAULT_CACHE_FILE:
        # 显式指定了缓存文件（测试最常用的隔离手段）：目录跟着它走
        return os.path.dirname(os.path.abspath(_CACHE_FILE))
    if _CACHE_DIR != _DEFAULT_CACHE_DIR:
        # 只改了目录（少见，但兼容）：文件名沿用默认
        return _CACHE_DIR
    # 真源：ACTUS_META_DIR > ACTUS_REPO_ROOT/_meta > __file__ 推导（paths.meta_dir()）
    return meta_dir()


def _cache_path() -> str:
    """解析缓存文件路径（**每次调用重新解析**，所以测试可以在 import 之后再设环境变量）。"""
    if _CACHE_FILE != _DEFAULT_CACHE_FILE:
        return _CACHE_FILE
    if _CACHE_DIR != _DEFAULT_CACHE_DIR:
        return os.path.join(_CACHE_DIR, _CACHE_FILENAME)
    # 真源：ACTUS_META_DIR > ACTUS_REPO_ROOT/_meta > __file__ 推导（paths.meta_dir()）
    return os.path.join(meta_dir(), _CACHE_FILENAME)

# 缓存 payload 结构版本。真源在 report.REPORT_SCHEMA_VERSION（报告结构在哪定义，
# 版本就在哪），这里只做别名 —— 两处各写一个数字迟早会漂移。
CACHE_SCHEMA_VERSION = REPORT_SCHEMA_VERSION

# 允许的时钟回拨量（秒）：缓存时间戳比「现在」还新超过这个量，判为无效。
# 典型来源：系统时钟被校正、缓存文件被手工改过、多机共享同一缓存目录。
# 改前没有这道判据：时间戳在未来时 `age` 为负，`age > max_age` 恒 False，
# 一份「未来」缓存会永久有效（实测 timestamp=now+1年 时 max_age=10 仍命中）。
_FUTURE_TOLERANCE = 300.0

# 必须齐备的维度键：历史上 save_cache 只落盘 items/summary，四个维度不落盘，
# 缓存命中后 platform/permissions/environment/resources 全变空 dict。
_REQUIRED_DIMENSIONS = ("platform", "permissions", "environment", "resources")

# load_cache 最近一次拒绝缓存的原因（供 cache_info() 排障，不影响返回值语义）
_LAST_REJECT = ""


def _ensure_cache_dir():
    """确保缓存目录存在（目录按 _cache_dir() 解析，支持 ACTUS_META_DIR）。"""
    os.makedirs(_cache_dir(), exist_ok=True)


def _resolve_max_age(max_age) -> Optional[float]:
    """把 max_age 归一成秒；返回 None 表示「本次不复用缓存」。

    - None（没传）→ 默认 TTL
    - 0 / 负数 / NaN → None（改前 0 会被 `or` 吃掉变成 3600）
    - 非法类型（字符串等）→ 默认 TTL（不静默当成「永不过期」）
    - inf → inf（永不判过期，语义自洽：age > inf 恒 False）
    """
    if max_age is None:
        return float(_CACHE_TTL)
    try:
        value = float(max_age)
    except (TypeError, ValueError):
        return float(_CACHE_TTL)
    if not (value > 0):          # 覆盖 0 / 负数 / NaN
        return None
    return value


def _read_payload():
    """读取并解析缓存文件，返回 (payload, reason)。"""
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            return json.load(f), ""
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError) as exc:
        # ValueError 覆盖 json.JSONDecodeError 与 UnicodeDecodeError
        return None, "unreadable(%s)" % type(exc).__name__


def _valid_timestamp(value) -> Optional[float]:
    """时间戳必须是有限正数；未来时间戳超出容忍量即视为无效（返回 None）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        stamp = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if stamp != stamp:                                  # NaN
        return None
    if stamp <= 0:                                      # 0 / 负数
        return None
    if stamp == float("inf") or stamp == float("-inf"):
        return None
    if stamp > time.time() + _FUTURE_TOLERANCE:         # 时钟回拨 / 被改过
        return None
    return stamp


def _validate_payload(data) -> tuple:
    """校验缓存 payload，返回 (ok, reason)。**只判定，不抛异常。**"""
    if not isinstance(data, dict):
        return False, "not-an-object(%s)" % type(data).__name__

    schema = data.get("schema_version")
    if schema != CACHE_SCHEMA_VERSION:
        # 旧缓存（改前版本没有这个键）与将来更新的版本都走这条路：结构不可信
        return False, "schema-mismatch(file=%r, expected=%r)" % (
            schema, CACHE_SCHEMA_VERSION)

    if _valid_timestamp(data.get("timestamp")) is None:
        return False, "bad-timestamp(%r)" % (data.get("timestamp"),)

    for key in _REQUIRED_DIMENSIONS:
        if not isinstance(data.get(key), dict):
            return False, "missing-dimension(%s)" % key

    items = data.get("items")
    if not isinstance(items, list):
        return False, "items-not-a-list(%s)" % type(items).__name__
    for index, entry in enumerate(items):
        # probe() 命中缓存后按 ProbeItem(**item) 重建，形状不对会 TypeError 炸穿
        if not isinstance(entry, dict):
            return False, "items[%d]-not-an-object" % index
        if not isinstance(entry.get("name"), str) or not entry.get("name"):
            return False, "items[%d]-has-no-name" % index

    summary = data.get("summary")
    if summary is not None and not isinstance(summary, dict):
        return False, "summary-not-an-object(%s)" % type(summary).__name__
    # summary 自洽性：缓存是本地文件，手写一份"形状合法"的 JSON 就能把
    # `available_items` 改成 999 冒充结论。probe() 命中后已改为**重算** summary
    # （见 __init__.py），这里是第二道闸：数字与 items 对不上的缓存直接判无效，
    # 让伪造/损坏的缓存在"缓存层"就被拦掉，而不是等渲染层去兜。
    # 空 summary 放行（历史/测试 seed 的载荷可能没有 summary，由 probe() 重算）。
    if summary:
        totals = tuple(summary.get(k) for k in
                       ("total_items", "available_items", "unavailable_items"))
        if any(isinstance(v, bool) or not isinstance(v, int) for v in totals):
            return False, "summary-bad-counts(%r)" % (totals,)
        total, available, unavailable = totals
        if total != len(items):
            return False, "summary-total-mismatch(total=%d, items=%d)" % (
                total, len(items))
        if available < 0 or unavailable < 0 or available + unavailable != total:
            return False, "summary-inconsistent(total=%d, available=%d, unavailable=%d)" % (
                total, available, unavailable)

    return True, ""


def load_cache(force_refresh: bool = False, max_age: int = None) -> Optional[dict]:
    """加载缓存。返回 None 表示缓存无效或不存在（调用方按「无缓存」处理）。

    参数:
        force_refresh: True 时无条件忽略缓存（不读盘）
        max_age: 缓存有效期（秒）。None＝默认 1 小时；<=0＝不复用缓存

    任何异常路径都降级为 None，绝不向 probe() 抛异常。
    """
    global _LAST_REJECT

    if force_refresh:
        _LAST_REJECT = "force-refresh"
        return None

    ttl = _resolve_max_age(max_age)
    if ttl is None:
        _LAST_REJECT = "max-age<=0(non-reuse)"
        return None

    data, reason = _read_payload()
    if data is None:
        _LAST_REJECT = reason
        return None

    ok, reason = _validate_payload(data)
    if not ok:
        _LAST_REJECT = reason
        return None

    age = time.time() - float(data["timestamp"])
    if age > ttl:
        _LAST_REJECT = "expired(age=%.1fs > max_age=%.1fs)" % (age, ttl)
        return None

    _LAST_REJECT = ""
    return data


def save_cache(report: dict) -> bool:
    """保存探测结果到缓存。返回 True 表示已落盘；任何失败返回 False。

    必须持久化**全部**维度：probe() 从缓存重建 ProbeReport 时按
    platform/permissions/environment/resources 四个键回填，若这里不落盘，
    第二次 probe() 命中缓存后这四个维度全部为空 dict（实测缓存往返丢失）。

    改后不再用键白名单，而是整体透传 + 覆盖元信息：将来探测层新增维度
    （例如 `platform_tools`）会自动跟着缓存走，不必再回来改这里 —— 白名单
    的失败形态是静默丢字段，且只有等 TTL 过期用户才可能发现。

    写入是原子的：先完整序列化到内存，再写同目录临时文件并 os.replace，
    避免半截 JSON 留下「损坏缓存」。
    """
    try:
        if not isinstance(report, dict):
            return False
        _ensure_cache_dir()
        data = dict(report)                       # 整体透传（含未来新增维度）
        data["schema_version"] = CACHE_SCHEMA_VERSION
        data["timestamp"] = _report_timestamp(report)
        data["cached_at"] = time.time()
        text = json.dumps(data, ensure_ascii=False, indent=2)   # 先序列化：不落半截
        _atomic_write(_cache_path(), text)
        return True
    except Exception:
        return False


def _report_timestamp(report: dict) -> float:
    """取报告自身的探测时间戳（数据的「采集时刻」）；不合法则用当前时间。"""
    stamp = _valid_timestamp(report.get("timestamp"))
    return stamp if stamp is not None else time.time()


def _atomic_write(path: str, text: str):
    """同目录临时文件 + os.replace 原子替换（Windows 上 os.replace 亦原子）。"""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".probe_cache.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def invalidate_cache():
    """清除缓存（含上一次原子写中断留下的临时文件）。"""
    path = _cache_path()
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
    # 清理临时残留：只碰本模块自己生成的 .probe_cache.*.tmp，不扫其它文件
    try:
        directory = os.path.dirname(os.path.abspath(path)) or "."
        for name in os.listdir(directory):
            if name.startswith(".probe_cache.") and name.endswith(".tmp"):
                try:
                    os.remove(os.path.join(directory, name))
                except OSError:
                    pass
    except OSError:
        pass


def cache_info() -> dict:
    """缓存诊断快照（纯读，不改任何状态）。

    回答「我明明探测过，为什么又重跑了」这类问题：文件在不在、多大、schema
    是否匹配、数据多旧、上次为什么被拒绝。`probe()` 不消费它，供 CLI/排障用。
    """
    path = _cache_path()
    info = {
        "path": path,
        "exists": os.path.exists(path),
        "schema_expected": CACHE_SCHEMA_VERSION,
        "schema_in_file": None,
        "ttl_seconds": _CACHE_TTL,
        "size_bytes": None,
        "timestamp": None,
        "age_seconds": None,
        "item_count": None,
        "valid": False,
        "reason": "",
        "last_reject": _LAST_REJECT,
    }
    if not info["exists"]:
        info["reason"] = "missing"
        return info
    try:
        info["size_bytes"] = os.path.getsize(path)
    except OSError:
        pass

    data, reason = _read_payload()
    if data is None:
        info["reason"] = reason
        return info
    if isinstance(data, dict):
        info["schema_in_file"] = data.get("schema_version")
        info["timestamp"] = data.get("timestamp")
        items = data.get("items")
        if isinstance(items, list):
            info["item_count"] = len(items)
    stamp = _valid_timestamp(data.get("timestamp")) if isinstance(data, dict) else None
    if stamp is not None:
        info["age_seconds"] = round(time.time() - stamp, 1)

    ok, reason = _validate_payload(data)
    info["valid"] = ok
    info["reason"] = "ok" if ok else reason
    return info
