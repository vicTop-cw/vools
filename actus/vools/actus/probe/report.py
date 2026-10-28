"""probe/report.py — ProbeReport 组装与摘要渲染。

对应 PROBE_PLAN.md §3.1 架构里的「vools.actus.probe.report — ProbeReport 组装」层：
把各探测器产出的 ProbeItem 列表 + 四个维度 dict 汇总成一份可序列化报告，
并提供人类可读摘要。__init__.py 的 probe() 负责采集，本模块负责组装/呈现。

渲染约定（本轮打磨，改前 → 改后）：

1. **section 恒定输出**：改前某个维度为空时整段消失（空报告实测一个 section 都
   不打印），用户分不清「探测失败」和「这台机器没这项」；改后每段都有标题，
   无数据时给 `(no data)` 占位。
2. **防御式访问 + 文本清洗**：改前 `perm['user']` / `s['total_items']` 这类硬下标
   遇到缺键（旧缓存、结构变更、部分降级）直接 KeyError 崩掉整份人类可读输出；
   改前 `version=None` 会渲染成字面量 `None`；改前 `wsl --version` 的 UTF-16
   版本号夹带 NUL，整份输出会被终端/`grep` 当成二进制（实测 stdout 含 13 个 NUL）。
   改后所有取值走 `.get`，并用 `_clean()` 去掉控制字符、折叠空白。
3. **耗时如实呈现**：`elapsed_ms` 的口径是**总墙钟**（引擎已从「仅并行段」
   改成「并行段 + 四维度 + 组装 + 落盘」）。标签因此写 `Total wall`（不是
   `Elapsed:`，避免读的人以为还是探测段耗时），并打印四段拆分
   `probers / dimensions / assemble / cache_write`，缺哪段显示 `n/a`
   （缓存命中路径没有 `cache_write_ms`，把「没记录」画成 0.0ms 就是伪造）。
4. **新增 [Timing] 段**：并行化之后用户要知道「哪段最慢、并行换来了几倍」。
   数据取自 `ProbeItem.elapsed_ms`（base.Prober.run() 已逐 prober 盖章，采集层
   无需改动），同一探测器的条目共享该耗时，故按分类取 max 而不是求和；
   并行倍率的分母用 `probers_ms`（并行段）而非总墙钟，否则串行尾巴会把收益说小。
5. **新增 verbose 视图**：`format_summary(report, verbose=True)` 额外给出
   四段耗时逐行明细、不可用条目清单、关键工具的真实路径、磁盘逐卷明细。
   默认输出保持精简。

向后兼容：`ProbeReport` / `format_summary` 的名字、位置参数、返回类型不变；
`timings` 是新增的可选字段，`verbose` 是新增的可选参数。
"""


__all__ = ['ProbeReport', 'format_summary', 'REPORT_SCHEMA_VERSION']

import sys
import time
from typing import Any, Dict

from .base import ProbeItem


# 报告结构版本。**探测结构变了就 bump**（新增维度/section、items 字段改名、
# summary 形状变动、已有字段语义变更）。cache.py 用它在加载时判定旧缓存失效 ——
# 否则新增 section 后旧缓存会冒充新报告，用户看不到新探测项，得等满 TTL 才自愈。
#   1: 隐式版本（无 schema 键）
#   2: 增加 schema_version / timings / 版本化缓存校验
#   3: `elapsed_ms` 语义从「仅并行段」改为「总墙钟」，并新增分段字段
#      probers_ms / dimensions_ms / assemble_ms / cache_write_ms
#      （同名老字段两套口径不可比 → schema=2 的缓存必须整体失效）
#   4: 新增 `report_source`（probe / cache）字段；缓存命中路径改为**重算 summary**，
#      `cache.load_cache` 也会校验 summary 与 items 自洽 —— 旧缓存没有这层保证，
#      可能带着伪造/过期的 summary 冒充新报告，故 schema=3 的缓存整体失效
#   5: 缓存 payload 新增「防事故」三件套 host / probe_version / items_digest
#      （跨机器误用 / 旧版本残留 / 写坏或人工编辑）。三者都是**新增必填**形状，
#      schema=4 的缓存一律缺这三键 ⇒ 虽会被新校验以 host-missing 拒掉，但那种
#      拒绝理由会误导排障（像是"文件缺字段"而不是"结构换代了"）；
#      故按既有规矩 bump，让旧缓存在 schema 闸门处就以 schema-mismatch 明确失效。
REPORT_SCHEMA_VERSION = 5

# 关键工具分类：只有这些分类的条目才会进 summary["key_tools"]（保持改前口径）
_KEY_TOOL_CATEGORIES = ("system_tools", "compilers", "runtimes")

# 总墙钟的四段拆分（引擎把这几段落盘在 ProbeReport.extra 上）。
# 顺序即渲染顺序：并行段 → 四维度采集 → 组装报告 → 缓存落盘。
_TIMING_SEGMENTS = (
    ("probers", "probers_ms"),
    ("dimensions", "dimensions_ms"),
    ("assemble", "assemble_ms"),
    ("cache_write", "cache_write_ms"),
)

_LINE_WIDTH = 60
_MAX_VALUE_CHARS = 64       # 默认模式单值长度上限（改前 curl/java 版本串独占 180 列）
_MAX_VERBOSE_CHARS = 240    # verbose 模式上限
_BAR_WIDTH = 22
_NO_DATA = "  (no data)"


# ---------------------------------------------------------------------------
# 文本工具（渲染层唯一的「脏数据入口」）
# ---------------------------------------------------------------------------

def _clean(value) -> str:
    """把任意值渲染成**单行安全文本**：去控制字符（含 NUL）、折叠空白。

    改前直接把探测到的字符串塞进输出，两个实测后果：
    * `wsl --version` 是 UTF-16 输出，解码后夹带 NUL（实测改前 stdout 里 13 个），
      `python -m vools.actus.cli probe | grep ...` 会把整份报告当成 "binary file"；
    * 解码失败的字节会变成 U+FFFD（实测 `cl` 的版本串），而 U+FFFD 在 cp936
      （中文 Windows 的 locale 编码）里**无法编码**：实测同字符串在 cp936 stdout
      上 `print()` 抛 UnicodeEncodeError（exit=1）。CLI 的 `main()` 会先
      `_ensure_utf8_stdout()` 把 stdout 改成 UTF-8，所以 `probe` 子命令本身
      不踩这个坑；但 `format_summary` 是公开 API（probe/__init__.py 再导出），
      第三方「拿到字符串直接 print」就会踩到。这里统一折成 `?`，
      信息量不变（U+FFFD 本来就表示「这个字节解不出来」）。
    """
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    chars = []
    for ch in text:
        code = ord(ch)
        if ch in "\r\n\t" or code < 32 or code == 127:
            chars.append(" ")
        elif code == 0xFFFD:                     # 解码替换符 → 可打印的 ?
            chars.append("?")
        else:
            chars.append(ch)
    return " ".join("".join(chars).split())


def _ensure_printable(text: str) -> str:
    """保证返回值能在**当前 stdout 编码**下打印出来（兜底，不是主要防线）。

    `format_summary` 是公开 API，调用方常直接 `print(...)`；若其 stdout 是
    cp936（中文 Windows 未 reconfigure 的管道/重定向）而报告里混进 UTF-8 专用
    字符（U+FFFD、部分符号），就会 UnicodeEncodeError 打断整条输出。这里按目标
    编码做一次 replace 往返，把不可打印字符降级成 `?`。（`python -m ... cli probe`
    自身是安全的：`main()` 已把 stdout reconfigure 成 UTF-8。本函数是给
    直接调用 format_summary 的库消费者兜底。）
    """
    encoding = getattr(sys.stdout, "encoding", None)
    if not encoding:
        return text
    try:
        normalized = encoding.lower().replace("-", "").replace("_", "")
        if normalized in ("utf8", "utf16", "utf32", "cp65001"):
            return text
        return text.encode(encoding, "replace").decode(encoding, "replace")
    except (LookupError, UnicodeError, AttributeError):
        return text


def _short(value, limit: int = _MAX_VALUE_CHARS) -> str:
    """清洗 + 超长截断（保留尾部省略号，让人知道还有内容）。"""
    text = _clean(value)
    if limit and len(text) > limit:
        return text[:max(1, limit - 1)] + "…"
    return text


def _yesno(value) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _format_timestamp(stamp) -> str:
    """epoch 秒 → 本地时间字符串（改前只印 `%.0f` 裸秒数，人读不出来）。"""
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(stamp)))
    except (TypeError, ValueError, OverflowError, OSError):
        return "unknown"


def _humanize_seconds(seconds) -> str:
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "?"
    if value != value or value < 0:      # NaN / 负数
        return "?"
    if value < 60:
        return "%ds" % int(round(value))
    if value < 3600:
        return "%dm %02ds" % (int(value // 60), int(value % 60))
    if value < 86400:
        return "%dh %02dm" % (int(value // 3600), int((value % 3600) // 60))
    return "%dd %02dh" % (int(value // 86400), int((value % 86400) // 3600))


def _humanize_ms(milliseconds) -> str:
    try:
        value = float(milliseconds)
    except (TypeError, ValueError):
        return "?"
    if value != value or value < 0:
        return "?"
    if value < 1000:
        return "%.1fms" % value
    if value < 60000:
        return "%.2fs" % (value / 1000.0)
    return "%dm %04.1fs" % (int(value // 60000), (value % 60000) / 1000.0)


def _round_ms(value):
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return value


def _segment_ms(report, key):
    """读一段耗时（probers_ms / dimensions_ms / assemble_ms / cache_write_ms）。

    缺失 → 返回 None，**绝不伪造 0**：缓存命中路径只有 probers/dimensions/
    assemble 三段（`cache_write_ms` 是保存过程的耗时，缓存里本来就没有），
    把「没记录」画成 0.0ms 会把「不知道」说成「不耗时」。

    数据来源按优先级：报告属性（未来若升级为正式字段）→ `report.extra`（当前
    引擎的落点，见 __init__.py）。0.0 是**合法实测值**（四维度复用并行段结果时
    实测就是 0.0），所以这里只把 None / 非数 / 负数 / NaN 判为缺失。
    """
    value = getattr(report, key, None)
    if value is None:
        extra = getattr(report, "extra", None)
        if isinstance(extra, dict):
            value = extra.get(key)
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value != value or value < 0:        # NaN / 负数
        return None
    return value


def _as_dict(value) -> Dict[str, Any]:
    """维度必须是 dict，否则当成空维度（缓存被改坏/旧结构都走这里）。"""
    return value if isinstance(value, dict) else {}


def _normalize_source(value) -> str:
    """`report_source` 归一：只接受 "probe" / "cache"，其它值标 "unknown"。

    为什么不让任意字符串通过：这是「报告怎么来的」的真值字段，写错或乱写会直接
    误导消费方（拿缓存当实测）。空值按默认 "probe"（老调用方没传这个参数）。
    """
    text = _clean(value).lower()
    if text in ("probe", "cache"):
        return text
    return "probe" if not text else "unknown"


# ---------------------------------------------------------------------------
# ProbeReport
# ---------------------------------------------------------------------------

class ProbeReport:
    """探针完整报告。

    `timings`（新增，可选）：{分类名: 毫秒} 的逐探测器耗时。不传则从
    `ProbeItem.elapsed_ms` 自动推导（compute_timings），行为向后兼容。
    `report_source`（新增，可选）：`"probe"`（本次真探测）或 `"cache"`
    （来自 `_meta/probe_cache.json`）。**缓存是本地文件，形状合法但内容不可信**
    （手写一份就能冒充报告），所以来源必须让消费方看得见：`--json` 里是
    `report_source`，人类可读摘要会多打一行"from cache"提示 + 复核建议。
    `extra_dims`（前向兼容）：调用方若因结构演进多传了维度关键字（如
    `platform_tools_info=...`），不会被 TypeError 拒掉，而是原样收进 `extra`
    并并入 `to_dict()` —— 采集层与报告层分开改时不至于互相炸。
    """

    def __init__(self, timestamp: float = None, elapsed_ms: float = 0,
                 platform_info: dict = None, permissions_info: dict = None,
                 environment_info: dict = None, resources_info: dict = None,
                 items: list = None, summary: dict = None,
                 timings: dict = None, report_source: str = "probe",
                 **extra_dims):
        self.timestamp = timestamp or time.time()
        self.elapsed_ms = elapsed_ms
        self.platform_info = platform_info or {}
        self.permissions_info = permissions_info or {}
        self.environment_info = environment_info or {}
        self.resources_info = resources_info or {}
        self.items = items or []
        self.summary = summary or {}
        self.timings = dict(timings) if isinstance(timings, dict) else {}
        self.report_source = _normalize_source(report_source)
        self.extra = dict(extra_dims)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "report_source": self.report_source,
            "timestamp": self.timestamp,
            "elapsed_ms": _round_ms(self.elapsed_ms or 0),
            "platform": self.platform_info,
            "permissions": self.permissions_info,
            "environment": self.environment_info,
            "resources": self.resources_info,
            "items": [_item_to_dict(item) for item in self.items],
            "summary": self.summary,
            "timings": dict((key, _round_ms(value))
                            for key, value in self.compute_timings().items()),
        }
        for key, value in self.extra.items():
            data.setdefault(key, value)
        return data

    def add_item(self, item: ProbeItem):
        self.items.append(item)

    def add_items(self, items: list):
        self.items.extend(items)

    def compute_timings(self) -> Dict[str, float]:
        """按分类汇总逐探测器耗时（不修改报告状态）。

        同一探测器的所有条目共享同一个 `_elapsed_ms`（base.Prober.run() 在
        run 结束时统一盖章），所以这里取 max 而不是求和 —— 求和会把 65 条
        system_tools 的 15s 累加成 15 分钟，那是假数字。
        """
        if self.timings:
            return dict(self.timings)
        timings = {}
        for item in self.items:
            elapsed = getattr(item, "_elapsed_ms", None)
            if elapsed is None:
                # 兼容「直接从 dict 反序列化」的条目（缓存/外部构造）
                if isinstance(item, dict):
                    elapsed = item.get("elapsed_ms")
            try:
                elapsed = float(elapsed)
            except (TypeError, ValueError):
                continue
            if elapsed != elapsed or elapsed < 0:
                continue
            label = _classify(item)
            current = timings.get(label)
            timings[label] = elapsed if current is None else max(current, elapsed)
        return timings

    def build_summary(self):
        """构建汇总信息（返回结构保持改前口径：by_category 条目只有 total/available）。"""
        available_count = sum(1 for i in self.items if getattr(i, "available", False))
        total_count = len(self.items)
        by_category = {}
        for item in self.items:
            cat = getattr(item, "category", "") or "unknown"
            if cat not in by_category:
                by_category[cat] = {"total": 0, "available": 0}
            by_category[cat]["total"] += 1
            if getattr(item, "available", False):
                by_category[cat]["available"] += 1

        # 提取关键工具状态
        key_tools = {}
        for item in self.items:
            if (getattr(item, "category", None) in _KEY_TOOL_CATEGORIES
                    and getattr(item, "available", False)):
                key_tools[getattr(item, "name", "?")] = {
                    "version": getattr(item, "version", None),
                    "path": getattr(item, "path", None),
                }

        self.summary = {
            "total_items": total_count,
            "available_items": available_count,
            "unavailable_items": total_count - available_count,
            "by_category": by_category,
            "key_tools": key_tools,
        }
        if not self.timings:
            self.timings = self.compute_timings()
        return self.summary


def _classify(item) -> str:
    """条目 → 渲染用的分类标签（探测器名与分类名在 items 里是同一个）。"""
    if isinstance(item, dict):
        return _clean(item.get("category")) or "unknown"
    return _clean(getattr(item, "category", "")) or "unknown"


def _item_to_dict(item) -> Dict[str, Any]:
    """条目序列化。正常是 ProbeItem；非预期类型也尽量降级成可序列化 dict。"""
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass
    if isinstance(item, dict):
        return dict(item)
    return {
        "name": _clean(getattr(item, "name", "")) or "?",
        "category": _clean(getattr(item, "category", "")) or "unknown",
        "available": bool(getattr(item, "available", False)),
        "path": getattr(item, "path", None),
        "version": getattr(item, "version", None),
    }


# ---------------------------------------------------------------------------
# 渲染：每个 section 一个小函数，缺数据时给占位而不是整段消失
# ---------------------------------------------------------------------------

def _render_header(report, verbose: bool) -> list:
    """报告头：时间戳 + **总墙钟** + 四段拆分。

    改前这里写 `Elapsed:`，而 `elapsed_ms` 的口径已从「仅并行段」改成「总墙钟」
    （probe() 全覆盖到落盘完成）—— 同一个标签两套含义会直接误导读数，所以标签
    改成 `Total wall` 并把四段（probers/dimensions/assemble/cache_write）打出来。
    缺段显示 `n/a` 而不是 0.0：缓存命中路径压根没有 cache_write 这一步，把
    「没记录」画成「不耗时」就是伪造。
    """
    stamp = getattr(report, "timestamp", None)
    wall = _safe_float(getattr(report, "elapsed_ms", 0) or 0)
    age = None
    try:
        age = time.time() - float(stamp)
    except (TypeError, ValueError):
        age = None
    lines = ["=" * _LINE_WIDTH, "vools probe report", "=" * _LINE_WIDTH]
    age_text = " (age %s)" % _humanize_seconds(age) if age is not None else ""
    lines.append("Timestamp: %s%s" % (_format_timestamp(stamp), age_text))

    # 来源标注：缓存是本地文件（形状合法即可伪造），必须让读者知道手里这份
    # 不是刚探测的。只对 cache / unknown 多打一行，正常 probe 输出保持不变。
    source = _clean(getattr(report, "report_source", "probe")).lower() or "probe"
    if source == "cache":
        lines.append("Source: cache  (from cache; use --force-refresh to re-probe)")
    elif source == "unknown":
        lines.append("Source: unknown")

    lines.append("Total wall: %s (%.1f ms)" % (_humanize_ms(wall), wall))

    segments = [(label, _segment_ms(report, key)) for label, key in _TIMING_SEGMENTS]
    if any(value is not None for _label, value in segments):
        if verbose:
            for label, value in segments:
                if value is None:
                    lines.append("    %-12s n/a" % label)
                else:
                    lines.append("    %-12s %s (%.1f ms)" % (
                        label, _humanize_ms(value), value))
            lines.append("    (total wall = probers + dimensions + assemble + cache_write)")
        else:
            parts = []
            for label, value in segments:
                parts.append("%s %s" % (label, "n/a" if value is None
                                        else _humanize_ms(value)))
            lines.append("    split: %s" % " | ".join(parts))
    return lines


def _render_platform(info, verbose: bool) -> list:
    lines = ["[Platform]"]
    info = _as_dict(info)
    if not info:
        lines.append(_NO_DATA)
        return lines
    lines.append("  OS: %s %s (%s)" % (
        _clean(info.get("os")) or "?",
        _clean(info.get("os_release")) or "?",
        _clean(info.get("arch")) or "?",
    ))
    lines.append("  Python: %s @ %s" % (
        _short(info.get("python_version")) or "?",
        _short(info.get("python_executable"),
               _MAX_VERBOSE_CHARS if verbose else _MAX_VALUE_CHARS) or "?",
    ))
    distro = info.get("linux_distro")
    if isinstance(distro, dict):
        lines.append("  Distro: %s %s" % (
            _clean(distro.get("name") or distro.get("id") or "?"),
            _clean(distro.get("version") or ""),
        ))
    if info.get("windows_version") is not None:
        lines.append("  Windows: %s" % (_clean(info.get("windows_version")) or "?"))
    if verbose:
        if info.get("windows_build") is not None:
            lines.append("  Build: %s" % (_clean(info.get("windows_build")) or "?"))
        if info.get("platform_tag"):
            lines.append("  Platform tag: %s" % _short(info.get("platform_tag")))
        for key, label in (("program_files", "Program Files"),
                           ("program_files_x86", "Program Files (x86)"),
                           ("app_data", "AppData"),
                           ("local_app_data", "LocalAppData")):
            if info.get(key):
                lines.append("  %s: %s" % (label, _short(info.get(key), _MAX_VERBOSE_CHARS)))
    return lines


def _render_permissions(info, verbose: bool) -> list:
    lines = ["[Permissions]"]
    info = _as_dict(info)
    if not info:
        lines.append(_NO_DATA)
        return lines
    user = _as_dict(info.get("user"))
    ident = "uid=%s" % ("n/a" if user.get("uid") is None else _clean(user.get("uid")))
    if user.get("gid") is not None:
        ident += ", gid=%s" % _clean(user.get("gid"))
    lines.append("  User: %s (%s)" % (_clean(user.get("name")) or "?", ident))
    lines.append("  Admin: %s" % _yesno(info.get("is_admin")))
    lines.append("  Can install system-wide: %s" % _yesno(info.get("can_install_system_wide")))
    if verbose:
        lines.append("  Elevated: %s" % _yesno(info.get("is_elevated")))
        lines.append("  Can create startups: %s" % _yesno(info.get("can_create_startups")))
        lines.append("  Elevation possible: %s" % _yesno(info.get("elevation_possible")))
        perms = _as_dict(info.get("effective_permissions"))
        for name in sorted(perms):
            entry = _as_dict(perms.get(name))
            lines.append("  %s: exists=%s write=%s" % (
                name, _yesno(entry.get("exists")), _yesno(entry.get("write"))))
    return lines


def _render_resources(info, verbose: bool) -> list:
    lines = ["[Resources]"]
    info = _as_dict(info)
    if not info:
        lines.append(_NO_DATA)
        return lines
    cpu = _as_dict(info.get("cpu"))
    mem = _as_dict(info.get("memory"))
    if cpu:
        model = _short(cpu.get("model") or cpu.get("platform") or "", 48)
        lines.append("  CPU: %s logical cores (%s)" % (
            _clean(cpu.get("count_logical")) or "?", model or "model unknown"))
    else:
        lines.append("  CPU: (no data)")
    if mem:
        lines.append("  Memory: %s MB total, %s MB available (%s%% used)" % (
            _clean(mem.get("total_mb")) or "?",
            _clean(mem.get("available_mb")) or "?",
            _clean(mem.get("used_percent")) or "?",
        ))
    else:
        lines.append("  Memory: (no data)")

    disk = info.get("disk")
    if isinstance(disk, list) and disk:
        total_mb = 0.0
        free_mb = 0.0
        for volume in disk:
            volume = _as_dict(volume)
            try:
                total_mb += float(volume.get("total_mb") or 0)
                free_mb += float(volume.get("free_mb") or 0)
            except (TypeError, ValueError):
                continue
        used = "?"
        if total_mb > 0:
            used = "%d" % round(100.0 * (1.0 - free_mb / total_mb))
        lines.append("  Disk: %d volume(s), %.0f MB free of %.0f MB (%s%% used)" % (
            len(disk), free_mb, total_mb, used))
        if verbose:
            for volume in disk:
                volume = _as_dict(volume)
                lines.append("    %s: %s MB free of %s MB (%s%% used)" % (
                    _short(volume.get("mountpoint") or volume.get("device"), 24) or "?",
                    _clean(volume.get("free_mb")) or "?",
                    _clean(volume.get("total_mb")) or "?",
                    _clean(volume.get("used_percent")) or "?"))
    else:
        lines.append("  Disk: (no data)")

    network = info.get("network")
    if isinstance(network, dict) and network:
        # 接口名在部分 locale 下是 GBK 乱码（resources.py 侧问题），只报数量
        lines.append("  Network: %d interface(s)" % len(network))
    return lines


def _render_environment(info, verbose: bool) -> list:
    lines = ["[Environment]"]
    info = _as_dict(info)
    if not info:
        lines.append(_NO_DATA)
        return lines
    lines.append("  PATH dirs: %s" % (_clean(info.get("path_count")) or "?"))
    venv = _as_dict(info.get("virtual_env"))
    if venv.get("active"):
        lines.append("  Virtual Env: %s" % (_short(venv.get("path"), _MAX_VERBOSE_CHARS) or "active"))
    elif verbose:
        lines.append("  Virtual Env: none")
    conda = _as_dict(info.get("conda_env"))
    if conda.get("active"):
        lines.append("  Conda Env: %s" % (_clean(conda.get("name")) or "?"))
    elif verbose:
        lines.append("  Conda Env: none")
    secrets = _as_dict(info.get("secret_keys_found"))
    if secrets:
        # 只报键名，绝不渲染值（探测器的安全约束）
        names = sorted(_clean(key) for key in secrets)
        lines.append("  Secret keys found: %s" % ", ".join(names))
    elif verbose:
        lines.append("  Secret keys found: none")
    return lines


def _render_summary(report) -> list:
    lines = ["[Summary]"]
    summary = _as_dict(getattr(report, "summary", None))
    if not summary:
        # 摘要可以没构建（ProbeReport() 裸构造），此时用 items 现算，别印 "no data"
        total = len(getattr(report, "items", []) or [])
        available = sum(1 for i in getattr(report, "items", []) or []
                        if getattr(i, "available", False))
        summary = {"total_items": total, "available_items": available,
                   "unavailable_items": total - available}
    total = summary.get("total_items", 0)
    available = summary.get("available_items", 0)
    unavailable = summary.get("unavailable_items", max(0, total - available))
    try:
        pct = "%d%%" % round(100.0 * float(available) / float(total)) if total else "n/a"
    except (TypeError, ValueError, ZeroDivisionError):
        pct = "n/a"
    lines.append("  Total items: %s" % _clean(total))
    lines.append("  Available: %s (%s)" % (_clean(available), pct))
    lines.append("  Unavailable: %s" % _clean(unavailable))
    return lines


def _render_by_category(report) -> list:
    lines = ["[By Category]"]
    summary = _as_dict(getattr(report, "summary", None))
    by_category = _as_dict(summary.get("by_category"))
    if not by_category:
        lines.append(_NO_DATA)
        return lines
    width = min(24, max(len(_clean(name)) for name in by_category))
    for category, counts in by_category.items():
        counts = _as_dict(counts)
        try:
            total = int(counts.get("total", 0))
            available = int(counts.get("available", 0))
        except (TypeError, ValueError):
            total, available = 0, 0
        pct = "%d%%" % round(100.0 * available / total) if total else "n/a"
        lines.append("  %-*s %3d/%-3d %5s" % (
            width, _clean(category)[:width], available, total, pct))
    return lines


def _render_timing(report) -> list:
    lines = ["[Timing]"]
    timings = {}
    compute = getattr(report, "compute_timings", None)
    if callable(compute):
        try:
            timings = dict(compute() or {})
        except Exception:
            timings = {}
    if not timings:
        lines.append(_NO_DATA)
        return lines

    wall_ms = 0.0
    try:
        wall_ms = float(getattr(report, "elapsed_ms", 0) or 0)
    except (TypeError, ValueError):
        wall_ms = 0.0
    try:
        prober_sum = sum(float(value) for value in timings.values())
    except (TypeError, ValueError):
        prober_sum = 0.0

    # 并行倍率的分母必须是「并行段」而不是总墙钟：总墙钟还含四维度采集、组装、
    # 落盘三段串行尾巴（实测 13.4s 里 5s 是尾巴），拿它当分母会把并行收益说小。
    parallel_ms = _segment_ms(report, "probers_ms")
    basis = "parallel segment"
    if parallel_ms is None or parallel_ms <= 0:
        parallel_ms = wall_ms
        basis = "wall clock"
    headline = ("  %s %s" % (basis, _humanize_ms(parallel_ms))
                if parallel_ms > 0 else "  %s n/a" % basis)
    headline += " | probers %d, sum %s" % (len(timings), _humanize_ms(prober_sum))
    if parallel_ms > 0 and prober_sum > 0:
        # 并行收益：串行总和 / 并行段耗时。探测是 IO 与 GIL 混合负载，只是量级参考
        headline += " | ~%.1fx" % (prober_sum / parallel_ms)
    if basis != "wall clock" and wall_ms - parallel_ms >= 10.0:
        # 串行尾巴（四维度 + 组装 + 落盘）确实存在时才提，避免重复报同一个数
        headline += " | total wall %s" % _humanize_ms(wall_ms)
    lines.append(headline)

    ordered = sorted(timings.items(), key=lambda kv: (-_safe_float(kv[1]), kv[0]))
    slowest = max((_safe_float(value) for _key, value in ordered), default=0.0)
    name_width = min(20, max(len(_clean(key)) for key, _value in ordered))
    for name, value in ordered:
        milliseconds = _safe_float(value)
        share = (milliseconds / prober_sum * 100.0) if prober_sum > 0 else 0.0
        bar_len = int(round(_BAR_WIDTH * milliseconds / slowest)) if slowest > 0 else 0
        lines.append("  %-*s %10s %5.1f%%  %s" % (
            name_width, _clean(name)[:name_width], _humanize_ms(milliseconds),
            share, "#" * max(bar_len, 1 if milliseconds > 0 else 0)))
    return lines


def _render_key_tools(report, verbose: bool) -> list:
    lines = ["[Key Tools]"]
    summary = _as_dict(getattr(report, "summary", None))
    key_tools = _as_dict(summary.get("key_tools"))
    if not key_tools:
        lines.append(_NO_DATA)
        return lines
    width = min(22, max(len(_clean(name)) for name in key_tools))
    limit = _MAX_VERBOSE_CHARS if verbose else _MAX_VALUE_CHARS
    for name in sorted(key_tools, key=lambda n: _clean(n).lower()):
        info = _as_dict(key_tools.get(name))
        version = _short(info.get("version"), limit)
        # 改前 version=None 会渲染成字面量 "None"；空版本改成占位符
        rendered = version or ("(no version reported)" if verbose else "-")
        lines.append("  [x] %-*s %s" % (width, _clean(name)[:width], rendered))
        if verbose and info.get("path"):
            lines.append("      @ %s" % _short(info.get("path"), _MAX_VERBOSE_CHARS))
    return lines


def _render_unavailable(report) -> list:
    """verbose 专属：按分类列出「这台机器上没有的东西」（最多 12 个/类）。"""
    lines = ["[Unavailable]"]
    grouped = {}
    for item in getattr(report, "items", []) or []:
        if getattr(item, "available", True):
            continue
        grouped.setdefault(_classify(item), []).append(
            _clean(getattr(item, "name", "")) or "?")
    if not grouped:
        lines.append("  (none)")
        return lines
    for category in sorted(grouped):
        names = sorted(grouped[category])
        shown = names[:12]
        suffix = "" if len(names) <= 12 else "  … +%d more" % (len(names) - 12)
        lines.append("  %s (%d): %s%s" % (
            category, len(names), ", ".join(shown), suffix))
    return lines


def _safe_float(value) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if result != result else result


def format_summary(report: ProbeReport, verbose: bool = False) -> str:
    """格式化输出摘要（人类可读）。

    参数:
        report: ProbeReport（方法只是读取，不修改报告）
        verbose: 追加不可用条目清单、工具真实路径、磁盘逐卷明细等细节
    """
    lines = []
    lines.extend(_render_header(report, verbose))
    lines.append("")

    for section in (
        _render_platform(getattr(report, "platform_info", None), verbose),
        _render_permissions(getattr(report, "permissions_info", None), verbose),
        _render_resources(getattr(report, "resources_info", None), verbose),
        _render_environment(getattr(report, "environment_info", None), verbose),
        _render_summary(report),
        _render_by_category(report),
        _render_timing(report),
        _render_key_tools(report, verbose),
    ):
        lines.extend(section)
        lines.append("")

    if verbose:
        lines.extend(_render_unavailable(report))
        lines.append("")

    lines.append("=" * _LINE_WIDTH)
    return _ensure_printable("\n".join(lines))
