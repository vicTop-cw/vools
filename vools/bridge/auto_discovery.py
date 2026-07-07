"""
vools.bridge.auto_discovery - 编译器自动发现与配置

一键发现本机和 WSL 环境中所有已安装的编程语言编译器，
并自动配置到 BridgeManager 中。

主要功能：
1. discover_all() - 一键发现所有环境的编译器
2. discover_local() - 仅发现本机编译器
3. discover_wsl() - 仅发现 WSL 编译器
4. get_discovery_report() - 生成完整的发现报告
5. configure_from_discovery() - 从发现结果配置 manager

用法：
    from vools.bridge.auto_discovery import discover_all

    # 一键发现所有
    result = discover_all()

    # 查看报告
    print(result['report'])

    # 查看可用语言
    print('本机可用:', result['local'].available_languages())
    print('WSL 可用:', result['wsl'][0].available_languages() if result['wsl'] else [])
"""

import os
import sys
import platform
from typing import Dict, List, Optional, Any

from . import probe
from . import manager as _manager_instance
from .manager import LanguageConfig

_IS_WINDOWS = platform.system() == 'Windows'


# ============================================================================
# 公共 API
# ============================================================================

def discover_all(
    languages: Optional[List[str]] = None,
    configure_manager: bool = True,
    include_wsl: bool = True,
) -> Dict[str, Any]:
    """
    一键发现所有环境中的编译器

    Args:
        languages: 指定要探测的语言列表，None 表示全部
        configure_manager: 是否自动配置到 BridgeManager
        include_wsl: 是否包含 WSL 环境

    Returns:
        dict: {
            'local': ProbeReport,        # 本机探测报告
            'wsl': List[ProbeReport],    # WSL 各发行版探测报告
            'discovered': dict,           # 已发现的语言
            'report': str,                # 格式化报告文本
        }
    """
    result = {
        'local': None,
        'wsl': [],
        'discovered': {},
        'report': '',
    }

    # 1. 本机探测
    local_report = probe.probe_with_extra_paths(languages=languages)
    result['local'] = local_report
    result['discovered']['local'] = local_report.available_languages()

    # 2. WSL 探测
    if _IS_WINDOWS and include_wsl:
        try:
            wsl_reports = probe.probe_all_wsl(languages=languages)
            result['wsl'] = wsl_reports
            for r in wsl_reports:
                result['discovered'][r.host] = r.available_languages()
        except Exception as e:
            result['wsl_error'] = str(e)

    # 3. 配置到 manager
    if configure_manager:
        _configure_from_report(local_report)

    # 4. 生成报告
    result['report'] = _generate_full_report(result)

    return result


def discover_local(
    languages: Optional[List[str]] = None,
    configure_manager: bool = True,
) -> Dict[str, Any]:
    """
    仅发现本机编译器

    Args:
        languages: 指定要探测的语言列表
        configure_manager: 是否自动配置到 BridgeManager

    Returns:
        dict: 发现结果
    """
    return discover_all(languages=languages, configure_manager=configure_manager, include_wsl=False)


def discover_wsl(
    languages: Optional[List[str]] = None,
) -> List[probe.ProbeReport]:
    """
    仅发现 WSL 环境中的编译器

    Args:
        languages: 指定要探测的语言列表

    Returns:
        List[ProbeReport]: 各 WSL 发行版的探测报告
    """
    if not _IS_WINDOWS:
        return []
    return probe.probe_all_wsl(languages=languages)


def get_discovery_report(
    languages: Optional[List[str]] = None,
    include_wsl: bool = True,
) -> str:
    """
    生成完整的发现报告文本

    Args:
        languages: 指定要探测的语言列表
        include_wsl: 是否包含 WSL

    Returns:
        str: 格式化的报告文本
    """
    result = discover_all(languages=languages, configure_manager=False, include_wsl=include_wsl)
    return result['report']


def configure_from_discovery(
    report: Optional[probe.ProbeReport] = None,
    include_wsl: bool = True,
) -> int:
    """
    从探测结果配置 BridgeManager

    Args:
        report: ProbeReport 实例，如果为 None 则自动探测
        include_wsl: 是否包含 WSL 环境（仅当 report 为 None 时有效）

    Returns:
        int: 成功配置的语言数量
    """
    if report is None:
        result = discover_all(configure_manager=False, include_wsl=include_wsl)
        count = 0
        if result.get('local'):
            count += _configure_from_report(result['local'])
        for wsl_report in result.get('wsl', []):
            count += _configure_from_report(wsl_report)
        return count
    return _configure_from_report(report)


# ============================================================================
# 内部函数
# ============================================================================

def _configure_from_report(report: probe.ProbeReport) -> int:
    """从探测报告配置 manager"""
    count = 0
    for lang, status in report.languages.items():
        if status.available and status.path:
            lang_lower = lang.lower()
            bin_dir = os.path.dirname(status.path)

            config = _manager_instance.get_config(lang_lower)
            if config:
                # 更新已有配置
                if bin_dir and bin_dir not in config.compiler_paths:
                    config.compiler_paths.insert(0, bin_dir)
                    _manager_instance.clear_cache(lang_lower)
            else:
                # 注册新语言
                probe_config = probe.LANGUAGE_PROBES.get(lang, {})
                _manager_instance.register(LanguageConfig(
                    name=lang_lower,
                    compiler=status.command or lang_lower,
                    compiler_paths=[bin_dir] if bin_dir else [],
                    version_pattern=probe_config.get('version_pattern'),
                ))
            count += 1
    return count


def _generate_full_report(result: Dict[str, Any]) -> str:
    """生成完整报告文本"""
    lines = []

    lines.append('=' * 70)
    lines.append('  vools.bridge 编译器自动发现报告')
    lines.append('=' * 70)

    # 本机报告
    if result.get('local'):
        local = result['local']
        lines.append('')
        lines.append('【本机环境】')
        lines.append(f'  平台: {local.platform}')
        lines.append(f'  架构: {local.arch}')
        lines.append(f'  Python: {local.python_version}')
        lines.append('')
        _append_language_summary(lines, local)

    # WSL 报告
    if result.get('wsl'):
        for wsl_report in result['wsl']:
            lines.append('')
            lines.append(f'【WSL: {wsl_report.host}】')
            lines.append(f'  平台: {wsl_report.platform}')
            lines.append(f'  架构: {wsl_report.arch}')
            lines.append('')
            _append_language_summary(lines, wsl_report)

    # 统计汇总
    lines.append('')
    lines.append('=' * 70)
    total_available = len(result['discovered'].get('local', []))
    total_langs = len(probe.LANGUAGE_PROBES)
    lines.append(f'  总计: {total_available}/{total_langs} 种语言可用')
    lines.append('=' * 70)

    return '\n'.join(lines)


def _append_language_summary(lines: List[str], report: probe.ProbeReport):
    """追加语言摘要到报告"""
    by_category: Dict[str, List[probe.LanguageStatus]] = {}
    for st in report.languages.values():
        by_category.setdefault(st.category or '其他', []).append(st)

    available_count = 0
    for category, sts in by_category.items():
        lines.append(f'  【{category}】')
        for st in sorted(sts, key=lambda x: x.name):
            if st.available:
                available_count += 1
                version_info = f' v{st.version}' if st.version else ''
                lines.append(f'    [OK]   {st.name:12s}{version_info}')
            else:
                lines.append(f'    [NO]   {st.name:12s} 未安装')
        lines.append('')


# ============================================================================
# 模块导出
# ============================================================================

__all__ = [
    'discover_all',
    'discover_local',
    'discover_wsl',
    'get_discovery_report',
    'configure_from_discovery',
]
