"""probe/__init__.py — 探针主入口。

probe() 函数：探测当前机器的所有维度，返回 ProbeReport。

ProbeReport / format_summary 的组装与渲染逻辑在 report.py（对应 PROBE_PLAN.md
§3.1 的分层架构），本模块只负责采集编排 + 从这里再导出，保持单一真源。

Phase 2（PROBE_PLAN.md §9）：探测器改为线程池并行（_MAX_PROBE_WORKERS 线程）。
并行只压缩墙钟耗时，**不改变语义**：items 仍按 probers 列表原顺序合并，
缓存命中/失效、异常降级约定与串行版逐字一致。

计时口径：`elapsed_ms` = **总墙钟**（并行段 + 四维度 + 组装 + 落盘），并额外拆出
`probers_ms` / `dimensions_ms` / `assemble_ms` / `cache_write_ms` 四个分段，
任何一段都不再是黑箱。改前 `elapsed_ms` 只量到并行段结束，而四个维度采集器在它
之后才跑 —— 实测 wall 13.4s 只报 elapsed_ms 8.4s（少报 5s），KPI 被系统性美化。
现在 elapsed_ms 覆盖到 probe() 返回前的最后一刻。

四维度去重：platform/permissions/environment/resources 四个探测器本来就把
`get_*_info()` 的结果原样放进 `ProbeItem.extra`，而 probe() 组装报告时又串行调了
一遍同样的函数（environment 单次 warm 2.7s / 冷 6.6s，等于白花两份）。现在优先
复用并行段已经算好的那份，只有条目缺失/失败/extra 为空时才回退重算。
"""

__all__ = ['probe', 'ProbeReport', 'format_summary']

import concurrent.futures
import threading
import time

from .base import ProbeItem
from .report import ProbeReport, format_summary
from .cache import load_cache, save_cache, invalidate_cache
from .platform import PlatformProber, get_platform_info
from .permissions import PermissionsProber, get_permissions_info
from .environment import EnvironmentProber, get_environment_info
from .resources import ResourcesProber, get_resources_info
from .system_tools import SystemToolsProber
from .runtimes import RuntimesProber
from .compilers import CompilersProber
from .python_pkgs import PythonPackagesProber
from .actions import ActionsProber

try:
    from .platform_tools import PlatformToolsProber
except ImportError:          # 平台司令尚未交付时不影响本体
    PlatformToolsProber = None

# 并行度上限：8 线程（PROBE_PLAN.md §9 Phase 2「线程池并行探测（8 线程）」）
_MAX_PROBE_WORKERS = 8

# 四个「维度」section：探测器把 get_*_info() 的结果原样放进 ProbeItem.extra，
# 因此并行段其实已经算过一份，组装报告时优先复用（见模块 docstring「四维度去重」）。
_DIMENSION_SECTIONS = ('platform', 'permissions', 'environment', 'resources')

# getter 用 lambda 包一层：在 probe() 里按**调用时**的模块全局解析，
# 这样测试 monkeypatch(probe_pkg.get_platform_info) 依然生效（不能在导入期捕获）。
_DIMENSION_GETTERS = {
    'platform': lambda: get_platform_info(),
    'permissions': lambda: get_permissions_info(),
    'environment': lambda: get_environment_info(),
    'resources': lambda: get_resources_info(),
}


def _run_prober(ProberClass):
    """在（可能并发的）工作线程里执行单个探测器，返回 ProbeItem 列表。

    异常约定与串行版完全一致：探测器内部异常本来就由 base.Prober.run() 兜住并
    降级成 available=False 的条目；这里再兜一层「构造/run 自身抛异常」的极端情况
    （name/category 取类名、error 取异常文本，与 base.Prober.run() 同形状），
    保证单个探测器炸掉绝不拖垮整体报告。
    """
    try:
        results = ProberClass().run()
    except Exception as exc:
        return [ProbeItem(
            name=ProberClass.__name__,
            category=ProberClass.__name__,
            available=False,
            error=str(exc),
        )]
    return list(results or [])


def _build_prober_list():
    """返回本次要执行的探测器清单 —— 列表顺序即 items 的合并顺序。"""
    global PlatformToolsProber

    if PlatformToolsProber is None:
        # 平台司令的 platform_tools.py 可能在本次进程启动之后才落地：
        # 惰性再做一次导入尝试（失败一律不影响本体，任何异常都不许冒泡）。
        try:
            from .platform_tools import PlatformToolsProber as _PlatformToolsProber
        except Exception:
            pass
        else:
            PlatformToolsProber = _PlatformToolsProber

    probers = [
        PlatformProber,
        PermissionsProber,
        EnvironmentProber,
        ResourcesProber,
        SystemToolsProber,
        RuntimesProber,
        CompilersProber,
        PythonPackagesProber,
        ActionsProber,
    ]
    if PlatformToolsProber is not None:
        probers.append(PlatformToolsProber)
    return probers


def _dimension_from_items(name, items):
    """从并行段产出的条目里取该维度 dict；取不到返回 None。

    四个维度探测器都是 `extra=<get_*_info() 的返回值>`，所以这份 extra 就是
    **同一次运行**算出来的真实维度值，不必再跑第二遍。
    """
    for item in items:
        if getattr(item, 'category', None) != name:
            continue
        extra = getattr(item, 'extra', None)
        if isinstance(extra, dict) and extra:
            return dict(extra)      # 浅拷贝：报告不与探测器条目共享同一个 dict
    return None


def _cached_timing_extras(cached):
    """把缓存带回来的分段耗时（*_ms）原样交给报告层，命中缓存时也能看到拆分。"""
    return dict((key, value) for key, value in cached.items()
                if key.endswith('_ms') and key != 'elapsed_ms')


def probe(*, force_refresh: bool = False, max_age: int = 3600,
          verbose: bool = False) -> ProbeReport:
    """
    执行完整探测，返回 ProbeReport。

    参数:
        force_refresh: 强制刷新（忽略缓存）
        max_age: 缓存有效期（秒），默认 1 小时
        verbose: 打印详细输出（多线程下由锁串行化，不会交错乱码）

    返回:
        ProbeReport 对象。`elapsed_ms` 是**总墙钟**，可拆分为
        probers_ms / dimensions_ms / assemble_ms / cache_write_ms。
    """
    # 尝试加载缓存
    cached = load_cache(force_refresh=force_refresh, max_age=max_age)
    if cached is not None:
        report = ProbeReport(
            timestamp=cached.get("timestamp", 0),
            elapsed_ms=cached.get("elapsed_ms", 0),
            platform_info=cached.get("platform", {}),
            permissions_info=cached.get("permissions", {}),
            environment_info=cached.get("environment", {}),
            resources_info=cached.get("resources", {}),
            items=[ProbeItem(**item) for item in cached.get("items", [])],
            summary=cached.get("summary", {}),
            timings=cached.get("timings"),
            **_cached_timing_extras(cached)
        )
        if verbose:
            print("[probe] loaded from cache")
        return report

    t0 = time.time()

    probers = _build_prober_list()

    all_items = []
    if probers:
        # 并行度 = min(8, 探测器数量)，至少 1
        workers = max(1, min(_MAX_PROBE_WORKERS, len(probers)))
        # verbose 进度输出要线程安全：整行打印串行化，避免多线程交错乱码
        progress_lock = threading.Lock() if verbose else None
        results_by_index = [None] * len(probers)

        def _task(index, ProberClass):
            results = _run_prober(ProberClass)
            if progress_lock is not None:
                available = sum(1 for r in results if r.available)
                with progress_lock:
                    print("[probe] %s: %d/%d available" % (
                        ProberClass.__name__, available, len(results)))
            return index, results

        # ── 并发执行各探测器 ──
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for index, ProberClass in enumerate(probers):
                futures[executor.submit(_task, index, ProberClass)] = (index, ProberClass)

            for future in concurrent.futures.as_completed(futures):
                index, ProberClass = futures[future]
                try:
                    index, results = future.result()
                except Exception as exc:   # 双保险：_run_prober 已兜异常，理论到不了这里
                    results = [ProbeItem(
                        name=ProberClass.__name__,
                        category=ProberClass.__name__,
                        available=False,
                        error=str(exc),
                    )]
                results_by_index[index] = results

        # 按 probers 原始顺序合并 —— 并行不改变 items 的顺序与结构
        for results in results_by_index:
            if results:
                all_items.extend(results)

    probers_ms = (time.time() - t0) * 1000

    # ── 四维度：优先复用并行段的结果，缺失才回退重算 ──
    t_dimensions = time.time()
    dimensions = {}
    for name in _DIMENSION_SECTIONS:
        dimensions[name] = (_dimension_from_items(name, all_items)
                            or _DIMENSION_GETTERS[name]())
    dimensions_ms = (time.time() - t_dimensions) * 1000

    # ── 构建报告 ──
    t_assemble = time.time()
    report = ProbeReport(
        timestamp=t0,
        elapsed_ms=0,
        platform_info=dimensions['platform'],
        permissions_info=dimensions['permissions'],
        environment_info=dimensions['environment'],
        resources_info=dimensions['resources'],
        items=all_items,
        probers_ms=round(probers_ms, 1),
        dimensions_ms=round(dimensions_ms, 1),
    )
    report.build_summary()
    report.extra['assemble_ms'] = round((time.time() - t_assemble) * 1000, 1)

    # ── 保存缓存 ──（先按「到此刻为止」的墙钟落盘；写盘耗时只能事后回填）
    t_cache = time.time()
    report.elapsed_ms = (t_cache - t0) * 1000
    save_cache(report.to_dict())
    report.extra['cache_write_ms'] = round((time.time() - t_cache) * 1000, 1)

    # elapsed_ms = 总墙钟：覆盖到组装 + 落盘完成，KPI 不再少报尾部串行耗时。
    report.elapsed_ms = (time.time() - t0) * 1000

    return report
