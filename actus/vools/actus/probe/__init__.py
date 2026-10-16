"""probe/__init__.py — 探针主入口。

probe() 函数：探测当前机器的所有维度，返回 ProbeReport。

ProbeReport / format_summary 的组装与渲染逻辑在 report.py（对应 PROBE_PLAN.md
§3.1 的分层架构），本模块只负责采集编排 + 从这里再导出，保持单一真源。
"""

__all__ = ['probe', 'ProbeReport', 'format_summary']

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


def probe(*, force_refresh: bool = False, max_age: int = 3600,
          verbose: bool = False) -> ProbeReport:
    """
    执行完整探测，返回 ProbeReport。

    参数:
        force_refresh: 强制刷新（忽略缓存）
        max_age: 缓存有效期（秒），默认 1 小时
        verbose: 打印详细输出

    返回:
        ProbeReport 对象
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
        )
        if verbose:
            print("[probe] loaded from cache")
        return report

    t0 = time.time()

    # ── 依次执行各探测器 ──
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

    all_items = []
    for ProberClass in probers:
        p = ProberClass()
        results = p.run()
        all_items.extend(results)
        if verbose:
            available = sum(1 for r in results if r.available)
            print("[probe] %s: %d/%d available" % (
                ProberClass.__name__, available, len(results)))

    elapsed = (time.time() - t0) * 1000

    # ── 构建报告 ──
    report = ProbeReport(
        timestamp=t0,
        elapsed_ms=elapsed,
        platform_info=get_platform_info(),
        permissions_info=get_permissions_info(),
        environment_info=get_environment_info(),
        resources_info=get_resources_info(),
        items=all_items,
    )
    report.build_summary()

    # ── 保存缓存 ──
    save_cache(report.to_dict())

    return report
