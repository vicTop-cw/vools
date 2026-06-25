"""
vools.bridge.probe - 跨语言编译环境探测工具

提供一键检测本机/WSL/远程主机上已安装的编程语言编译器/运行时，
返回结构化的可用性报告。

主要功能：
1. probe_environment() - 检测本机环境
2. probe_wsl() - 检测 WSL Linux 子系统
3. probe_remote(host) - 检测远程主机（基于 SSH）
4. print_report() - 友好的报告输出
5. get_available_languages() - 仅返回可用的语言列表

支持的语言（按桥接子包顺序）：
  c / cpp / rust / go / nim / cangjie / csharp / java / scala / 
  ruby / julia / r / freebasic / mojo /
  typescript / kotlin / zig / lua / dart / swift / php
"""

import os
import sys
import platform
import subprocess
import shutil
import json
from typing import Dict, List, Optional, Tuple, Any
from ...core.dataclass_compat import dataclass, field, asdict

_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# ============================================================================
# 语言探测配置
# ============================================================================
# 每种语言的探测命令列表（按优先级），找到任一即视为可用
# version_cmd 用于获取版本号
# install_hint 提供安装建议
# ============================================================================

LANGUAGE_PROBES: Dict[str, Dict[str, Any]] = {
    # ---------- 系统级编译语言 ----------
    'c': {
        'commands': ['gcc', 'clang', 'cl', 'cc'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': '系统级',
        'install_hint': {
            'Windows': '安装 MinGW-w64 或 Visual Studio Build Tools',
            'Linux': 'sudo apt install gcc  # Debian/Ubuntu',
            'Darwin': 'xcode-select --install',
        },
    },
    'cpp': {
        'commands': ['g++', 'clang++', 'cl', 'c++'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': '系统级',
        'install_hint': {
            'Windows': '安装 MinGW-w64 或 Visual Studio Build Tools',
            'Linux': 'sudo apt install g++',
            'Darwin': 'xcode-select --install',
        },
    },
    'rust': {
        'commands': ['rustc', 'cargo'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': '系统级',
        'install_hint': {
            'Windows': '访问 https://rustup.rs/ 一键安装',
            'Linux': 'curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | sh',
            'Darwin': 'brew install rust  # 或使用 rustup',
        },
    },
    'go': {
        'commands': ['go'],
        'version_args': ['version'],
        'version_pattern': r'go(\d+\.\d+(?:\.\d+)?)',
        'category': '系统级',
        'install_hint': {
            'Windows': 'https://go.dev/dl/ 下载 MSI',
            'Linux': 'sudo apt install golang-go  # 或从官网下载',
            'Darwin': 'brew install go',
        },
    },
    'nim': {
        'commands': ['nim'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': '系统级',
        'install_hint': {
            'Windows': 'https://nim-lang.org/install_windows.html',
            'Linux': 'sudo apt install nim  # 或使用 choosenim',
            'Darwin': 'brew install nim',
        },
    },
    'cangjie': {
        'commands': ['cjc'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': '系统级',
        'install_hint': {
            'Windows': '下载 仓颉 SDK: https://cangjie-lang.cn/',
            'Linux': '下载 仓颉 SDK: https://cangjie-lang.cn/',
            'Darwin': '下载 仓颉 SDK: https://cangjie-lang.cn/',
        },
    },
    'zig': {
        'commands': ['zig'],
        'version_args': ['version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': '系统级',
        'install_hint': {
            'Windows': 'https://ziglang.org/download/ 下载 zip 解压即可',
            'Linux': 'snap install zig  # 或官网下载',
            'Darwin': 'brew install zig',
        },
    },

    # ---------- JVM 生态 ----------
    'java': {
        'commands': ['java', 'javac'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+(?:\.\d+)?(?:\.\d+)?)',
        'category': 'JVM',
        'install_hint': {
            'Windows': 'https://adoptium.net/ 下载 JDK',
            'Linux': 'sudo apt install default-jdk',
            'Darwin': 'brew install openjdk',
        },
    },
    'kotlin': {
        'commands': ['kotlinc', 'kotlin'],
        'version_args': ['-version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': 'JVM',
        'install_hint': {
            'Windows': 'https://kotlinlang.org/docs/command-line.html',
            'Linux': 'sudo snap install kotlin --classic',
            'Darwin': 'brew install kotlin',
        },
    },
    'scala': {
        'commands': ['scala', 'scalac'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': 'JVM',
        'install_hint': {
            'Windows': 'https://www.scala-lang.org/download/',
            'Linux': 'sudo apt install scala',
            'Darwin': 'brew install scala',
        },
    },

    # ---------- .NET 生态 ----------
    'csharp': {
        'commands': ['dotnet', 'csc', 'mcs'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': '.NET',
        'install_hint': {
            'Windows': 'https://dotnet.microsoft.com/download',
            'Linux': 'sudo apt install dotnet-sdk-8.0',
            'Darwin': 'brew install --cask dotnet-sdk',
        },
    },

    # ---------- 脚本语言 ----------
    'ruby': {
        'commands': ['ruby'],
        'version_args': ['--version'],
        'version_pattern': r'ruby (\d+\.\d+(?:\.\d+)?)',
        'category': '脚本',
        'install_hint': {
            'Windows': 'https://rubyinstaller.org/',
            'Linux': 'sudo apt install ruby-full',
            'Darwin': '系统自带，或 brew install ruby',
        },
    },
    'php': {
        'commands': ['php'],
        'version_args': ['--version'],
        'version_pattern': r'PHP (\d+\.\d+(?:\.\d+)?)',
        'category': '脚本',
        'install_hint': {
            'Windows': 'https://windows.php.net/download/',
            'Linux': 'sudo apt install php',
            'Darwin': 'brew install php',
        },
    },
    'lua': {
        'commands': ['luajit', 'lua'],
        'version_args': ['--version', '-v'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': '脚本',
        'install_hint': {
            'Windows': 'https://luajit.org/download.html',
            'Linux': 'sudo apt install luajit',
            'Darwin': 'brew install luajit',
        },
    },
    'freebasic': {
        'commands': ['fbc'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': '脚本',
        'install_hint': {
            'Windows': 'https://www.freebasic.net/',
            'Linux': 'sudo apt install freebasic',
            'Darwin': 'brew install freebasic',
        },
    },

    # ---------- 科学计算 ----------
    'julia': {
        'commands': ['julia'],
        'version_args': ['--version'],
        'version_pattern': r'julia version (\d+\.\d+(?:\.\d+)?)',
        'category': '科学计算',
        'install_hint': {
            'Windows': 'https://julialang.org/downloads/',
            'Linux': 'sudo apt install julia  # 或官网安装脚本',
            'Darwin': 'brew install --cask julia',
        },
    },
    'r': {
        'commands': ['R', 'Rscript'],
        'version_args': ['--version'],
        'version_pattern': r'R version (\d+\.\d+(?:\.\d+)?)',
        'category': '科学计算',
        'install_hint': {
            'Windows': 'https://cran.r-project.org/bin/windows/base/',
            'Linux': 'sudo apt install r-base',
            'Darwin': 'brew install r',
        },
    },

    # ---------- AI/ML 专用 ----------
    'mojo': {
        'commands': ['mojo'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': 'AI/ML',
        'install_hint': {
            'Windows': 'https://modular.com/mojo  # 当前仅支持 Linux/macOS',
            'Linux': 'curl -s https://get.modular.com | sh -',
            'Darwin': 'https://modular.com/mojo',
        },
    },

    # ---------- 建议新增 ----------
    'typescript': {
        'commands': ['tsc', 'node', 'npm'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': '脚本',
        'install_hint': {
            'Windows': 'https://nodejs.org/ 下载安装 Node.js',
            'Linux': 'sudo apt install nodejs npm',
            'Darwin': 'brew install node',
        },
    },
    'dart': {
        'commands': ['dart', 'flutter'],
        'version_args': ['--version'],
        'version_pattern': r'(\d+\.\d+(?:\.\d+)?)',
        'category': '脚本',
        'install_hint': {
            'Windows': 'https://dart.dev/get-dart',
            'Linux': 'sudo apt install dart',
            'Darwin': 'brew install dart',
        },
    },
    'swift': {
        'commands': ['swift'],
        'version_args': ['--version'],
        'version_pattern': r'Swift version (\d+\.\d+(?:\.\d+)?)',
        'category': '系统级',
        'install_hint': {
            'Windows': 'https://www.swift.org/download/  # Windows 支持有限',
            'Linux': 'https://www.swift.org/download/',
            'Darwin': 'xcode-select --install  # 或 brew install swift',
        },
    },
}

# 已被 vools.bridge 子包实现覆盖的语言
# 其他语言（typescript, kotlin, zig, lua, dart, swift, php）需先实现桥接
BRIDGE_SUPPORTED = {
    'c', 'cpp', 'rust', 'go', 'nim', 'cangjie', 'csharp',
    'java', 'scala', 'ruby', 'julia', 'r', 'freebasic', 'mojo',
}


# ============================================================================
# 探测结果数据类
# ============================================================================

@dataclass
class LanguageStatus:
    """单个语言的探测结果"""
    name: str
    available: bool = False
    path: Optional[str] = None       # 可执行文件路径
    version: Optional[str] = None    # 版本号
    command: Optional[str] = None    # 实际使用的命令
    category: str = ''
    install_hint: str = ''
    error: Optional[str] = None      # 探测失败时的错误信息

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProbeReport:
    """完整的探测报告"""
    platform: str
    arch: str
    python_version: str
    languages: Dict[str, LanguageStatus] = field(default_factory=dict)
    host: str = 'local'              # 'local' / 'wsl' / 'ssh://...'

    def is_available(self, lang: str) -> bool:
        return self.languages.get(lang, LanguageStatus(name=lang)).available

    def available_languages(self) -> List[str]:
        """返回已安装的语言列表"""
        return [name for name, st in self.languages.items() if st.available]

    def missing_languages(self) -> List[str]:
        """返回未安装的语言列表"""
        return [name for name, st in self.languages.items() if not st.available]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'platform': self.platform,
            'arch': self.arch,
            'python_version': self.python_version,
            'host': self.host,
            'languages': {k: v.to_dict() for k, v in self.languages.items()},
        }


# ============================================================================
# 核心探测函数
# ============================================================================

def _probe_one(lang: str, config: Dict[str, Any], env: Optional[Dict[str, str]] = None) -> LanguageStatus:
    """
    探测单个语言

    Args:
        lang: 语言名
        config: LANGUAGE_PROBES 中的配置
        env: 可选的环境变量（用于远程主机/WSL）
    """
    status = LanguageStatus(
        name=lang,
        category=config.get('category', ''),
    )

    for cmd in config['commands']:
        # 优先使用 which 查找路径
        if env is None:
            path = shutil.which(cmd)
        else:
            # 在指定环境中查找
            path = _which_in_env(cmd, env)

        if path:
            status.path = path
            status.command = cmd
            # 获取版本
            try:
                version_args = config.get('version_args', ['--version'])
                result = subprocess.run(
                    [path] + version_args,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                    env=env,
                )
                output = (result.stdout or '') + (result.stderr or '')
                if output:
                    import re
                    pat = config.get('version_pattern', r'(\d+\.\d+(?:\.\d+)?)')
                    m = re.search(pat, output)
                    if m:
                        status.version = m.group(1)
                    else:
                        # 取第一行作为版本描述
                        first_line = output.strip().split('\n')[0]
                        status.version = first_line[:80]
                status.available = True
            except Exception as e:
                status.available = True  # 找到命令就算可用
                status.version = 'unknown'
                status.error = f'版本检测失败: {e}'
            break
        else:
            status.error = f'未找到命令 {cmd}'

    if not status.available:
        platform_key = platform.system()
        hints = config.get('install_hint', {})
        status.install_hint = hints.get(platform_key, hints.get('Linux', '请参考官方文档'))

    return status


def _which_in_env(cmd: str, env: Dict[str, str]) -> Optional[str]:
    """在指定环境变量中查找命令"""
    # 使用 which 命令在远程环境查找
    try:
        result = subprocess.run(
            ['which', cmd],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            env=env,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def probe_environment(
    languages: Optional[List[str]] = None,
    host: str = 'local',
    extra_env: Optional[Dict[str, str]] = None,
) -> ProbeReport:
    """
    探测指定环境的编程语言编译器/运行时可用性

    Args:
        languages: 要探测的语言列表，None 表示探测所有
        host: 主机标识（'local' / 'wsl' / 'ssh://...'）
        extra_env: 额外的环境变量

    Returns:
        ProbeReport: 完整的探测报告
    """
    # 准备环境变量
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    # 准备探测目标
    if languages is None:
        languages = list(LANGUAGE_PROBES.keys())

    # 基础信息
    report = ProbeReport(
        platform=f"{platform.system()} {platform.release()}",
        arch=platform.machine(),
        python_version=sys.version.split()[0],
        host=host,
    )

    for lang in languages:
        config = LANGUAGE_PROBES.get(lang)
        if not config:
            # 未知语言
            st = LanguageStatus(
                name=lang,
                available=False,
                error='未在 LANGUAGE_PROBES 中注册',
                install_hint='请在 vools.bridge.probe.LANGUAGE_PROBES 中添加该语言',
            )
        else:
            st = _probe_one(lang, config, env=env)
        report.languages[lang] = st

    return report


def probe_wsl(
    dist: str = 'Ubuntu',
    languages: Optional[List[str]] = None,
) -> ProbeReport:
    """
    探测 WSL（Windows Subsystem for Linux）中的环境

    Args:
        dist: WSL 发行版名称（默认 'Ubuntu'）
        languages: 要探测的语言列表
    """
    if not _IS_WINDOWS:
        # 非 Windows 平台直接探测本地
        return probe_environment(languages=languages, host='wsl(unsupported-on-platform)')

    # 检查 wsl 是否可用
    if shutil.which('wsl') is None:
        report = ProbeReport(
            platform='WSL (unavailable)',
            arch=platform.machine(),
            python_version=sys.version.split()[0],
            host=f'wsl:{dist}',
        )
        for lang in (languages or list(LANGUAGE_PROBES.keys())):
            st = LanguageStatus(
                name=lang,
                available=False,
                error='wsl 命令不可用，请先安装 WSL',
                install_hint='wsl --install  # PowerShell 管理员模式',
            )
            report.languages[lang] = st
        return report

    # 探测 WSL 发行版
    try:
        check = subprocess.run(
            ['wsl', '-d', dist, '--', 'echo', 'wsl-ready'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if check.returncode != 0 or 'wsl-ready' not in check.stdout:
            raise RuntimeError(f'WSL 发行版 {dist} 不可用: {check.stderr}')
    except Exception as e:
        report = ProbeReport(
            platform='WSL (error)',
            arch=platform.machine(),
            python_version=sys.version.split()[0],
            host=f'wsl:{dist}',
        )
        st = LanguageStatus(
            name='<wsl>',
            available=False,
            error=str(e),
        )
        report.languages['<wsl>'] = st
        return report

    # 在 WSL 中探测每个语言
    if languages is None:
        languages = list(LANGUAGE_PROBES.keys())

    # 获取 WSL 的发行版信息
    try:
        info = subprocess.run(
            ['wsl', '-d', dist, '--', 'cat', '/etc/os-release'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        os_info = info.stdout.strip().split('\n')[0] if info.returncode == 0 else 'WSL Linux'
    except Exception:
        os_info = 'WSL Linux'

    arch_info = subprocess.run(
        ['wsl', '-d', dist, '--', 'uname', '-m'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
        timeout=5,
    )
    arch = arch_info.stdout.strip() or platform.machine()

    report = ProbeReport(
        platform=os_info,
        arch=arch,
        python_version=sys.version.split()[0],  # 本机 Python 版本（WSL 中的 Python 需要单独探测）
        host=f'wsl:{dist}',
    )

    for lang in languages:
        config = LANGUAGE_PROBES.get(lang)
        if not config:
            st = LanguageStatus(
                name=lang,
                available=False,
                error='未在 LANGUAGE_PROBES 中注册',
            )
        else:
            st = _probe_one_wsl(lang, config, dist)
        report.languages[lang] = st

    return report


def _probe_one_wsl(lang: str, config: Dict[str, Any], dist: str) -> LanguageStatus:
    """在 WSL 中探测单个语言"""
    status = LanguageStatus(
        name=lang,
        category=config.get('category', ''),
    )

    for cmd in config['commands']:
        try:
            # 检查命令是否存在
            check = subprocess.run(
                ['wsl', '-d', dist, '--', 'which', cmd],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if check.returncode == 0 and check.stdout.strip():
                path = check.stdout.strip()
                status.path = path
                status.command = cmd
                # 获取版本
                try:
                    version_args = config.get('version_args', ['--version'])
                    result = subprocess.run(
                        ['wsl', '-d', dist, '--', cmd] + version_args,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=5,
                    )
                    # WSL 输出可能是 GBK 编码，统一容错处理
                    for enc in ('utf-8', 'gbk', 'latin-1'):
                        try:
                            output = result.stdout.decode(enc, errors='ignore') + result.stderr.decode(enc, errors='ignore')
                            break
                        except Exception:
                            continue
                    else:
                        output = (result.stdout or b'').decode('utf-8', errors='ignore') + (result.stderr or b'').decode('utf-8', errors='ignore')
                    if output:
                        import re
                        pat = config.get('version_pattern', r'(\d+\.\d+(?:\.\d+)?)')
                        m = re.search(pat, output)
                        if m:
                            status.version = m.group(1)
                        else:
                            first_line = output.strip().split('\n')[0]
                            status.version = first_line[:80]
                    status.available = True
                except Exception as e:
                    status.available = True
                    status.version = 'unknown'
                    status.error = f'版本检测失败: {e}'
                break
        except Exception as e:
            status.error = f'wsl 探测失败: {e}'

    if not status.available:
        hints = config.get('install_hint', {})
        # WSL 中使用 Linux 的安装建议
        status.install_hint = hints.get('Linux', hints.get('Windows', '请参考官方文档'))

    return status


# ============================================================================
# 便捷函数
# ============================================================================

def get_available_languages(
    languages: Optional[List[str]] = None,
    host: str = 'local',
) -> List[str]:
    """快速获取可用语言列表"""
    report = probe_environment(languages=languages, host=host)
    return report.available_languages()


def print_report(report: ProbeReport, show_install: bool = True) -> str:
    """
    生成友好的探测报告文本

    Returns:
        报告文本字符串
    """
    lines = []
    lines.append('=' * 70)
    lines.append(f'  vools.bridge 环境探测报告')
    lines.append('=' * 70)
    lines.append(f'  主机: {report.host}')
    lines.append(f'  平台: {report.platform}')
    lines.append(f'  架构: {report.arch}')
    lines.append(f'  Python: {report.python_version}')
    lines.append('=' * 70)

    # 按类别分组
    by_category: Dict[str, List[LanguageStatus]] = {}
    for st in report.languages.values():
        by_category.setdefault(st.category or '其他', []).append(st)

    available_count = 0
    total_count = len(report.languages)

    for category, sts in by_category.items():
        lines.append(f'')
        lines.append(f'【{category}】')
        for st in sorted(sts, key=lambda x: x.name):
            if st.available:
                available_count += 1
                version_info = f' v{st.version}' if st.version else ''
                path_info = f' ({st.path})' if st.path else ''
                lines.append(f'  [OK]   {st.name:12s}{version_info}{path_info}')
            else:
                lines.append(f'  [NO]   {st.name:12s} 未安装')

    lines.append('')
    lines.append('=' * 70)
    lines.append(f'  统计: {available_count}/{total_count} 种语言可用')
    lines.append('=' * 70)

    if show_install:
        missing = report.missing_languages()
        if missing:
            lines.append('')
            lines.append('【安装建议】')
            for lang in missing:
                st = report.languages[lang]
                if st.install_hint:
                    lines.append(f'  - {lang}: {st.install_hint}')

    return '\n'.join(lines)


def save_report(report: ProbeReport, filepath: str) -> None:
    """保存报告为 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)


# ============================================================================
# 模块导出
# ============================================================================

__all__ = [
    'LANGUAGE_PROBES',
    'BRIDGE_SUPPORTED',
    'LanguageStatus',
    'ProbeReport',
    'probe_environment',
    'probe_wsl',
    'get_available_languages',
    'print_report',
    'save_report',
]
