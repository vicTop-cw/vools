"""
vools.bridge.configs - 跨语言编译器位置统一声明与持久化

单一真源：`DEFAULT_SPECS` 声明每种语言「在哪找工具链」，模块内**不含任何用户机器绝对路径**。
用户机器的实际安装位置由三层运行时数据承载，全部可写、可持久化到用户侧 JSON（不进仓库、不发布）：

    1. overrides     —— 用户显式指定的工具链绝对路径（set_override）
    2. project_roots —— 各语言项目根目录（set_project_root，如 Pentad 工程根）
    3. discovered     —— 探针发现的历史结果（probe 写入）

查询顺序（resolve_compiler）：
    overrides → discovered → 环境变量（VOOLS_<LANG>_PATH / spec.root_env）
    → project_root + globs → PATH（shutil.which） → WSL 回退

公共 API：
    get_spec / all_specs
    resolve_compiler(lang) / resolve_aux(lang, key)
    set_override / get_override / clear_override
    set_project_root / get_project_root / all_project_roots
    set_discovered / get_discovered
    load_user_config / save_user_config / get_user_config_path
    export_report

用法::

    from vools.bridge.configs import resolve_compiler, set_project_root, save_user_config

    # 运行时告诉它 Pentad 工程在哪
    set_project_root('pentad', r'D:\\MyTools\\Pentad')
    save_user_config()                       # 落盘到 ~/.vools/bridge_config.json

    # 取编译器
    p5c = resolve_compiler('pentad')          # -> .../target/release/p5c.exe
"""

import os
import sys
import json
import glob
import shutil
import platform
from typing import Dict, List, Optional, Any, Union

from .core.compat.dataclass_compat import dataclass, field, asdict

_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'


# ============================================================================
# 工具链声明
# ============================================================================

@dataclass
class ToolchainSpec:
    """
    单语言工具链的位置声明。

    属性：
        name: 语言名（小写）
        commands: 可执行命令名列表（走 PATH 查找），按优先级排序
        version_args: 版本检测参数
        category: 报告分组
        install_hint: 各平台安装提示
        kind: 工具链形态（'exe'=可执行 / 'dir'=目录 / 'pkg'=Python 包源码目录）
        root_env: 项目根目录的环境变量名（如 VOOLS_PENTAD_ROOT）；无则 None
        globs: 相对项目根的工具链 glob 模板列表（支持 ** 递归子目录）
        aux: 附加产物声明，键名 -> glob 模板列表（相对项目根），如 lz 的 lz_builtins rlib
        root_dirname_hints: 在 VOOLS_PROJECTS_ROOT 下匹配项目根的目录名候选
            （探针扫描用；不含绝对路径，只给名字，如 ['Tnr','tnr']）
    """
    name: str
    commands: List[str] = field(default_factory=list)
    version_args: List[str] = field(default_factory=lambda: ['--version'])
    category: str = '其他'
    install_hint: Dict[str, str] = field(default_factory=dict)
    kind: str = 'exe'
    root_env: Optional[str] = None
    globs: List[str] = field(default_factory=list)
    aux: Dict[str, List[str]] = field(default_factory=dict)
    root_dirname_hints: List[str] = field(default_factory=list)

    __attrs_post_init__ = lambda self: None


# ============================================================================
# 默认声明（不含任何用户绝对路径）
# ============================================================================

_WIN = 'Windows'
_LNX = 'Linux'
_OSX = 'Darwin'

DEFAULT_SPECS: Dict[str, ToolchainSpec] = {
    # ---------- 新增：非 PATH 工具链（依赖项目根 / env 变量 / glob） ----------
    'tnr': ToolchainSpec(
        name='tnr',
        commands=['tnr'],
        version_args=['version'],
        category='张量语言',
        root_env='VOOLS_TNR_ROOT',
        globs=['target/release/tnr.exe', 'target/debug/tnr.exe',
               'target/release/tnr', 'target/debug/tnr'],
        root_dirname_hints=['Tnr', 'tnr'],
        install_hint={
            _WIN: '设置 VOOLS_TNR_ROOT 指向 Tnr 工程根，或把 tnr.exe 所在目录加入 PATH',
            _LNX: '把 tnr 所在目录加入 PATH',
            _OSX: '把 tnr 所在目录加入 PATH',
        },
    ),
    'lz': ToolchainSpec(
        name='lz',
        commands=['lang-zone', 'lz', 'lzc'],
        version_args=['--version'],
        category='转译语言',
        root_env='VOOLS_LZ_ROOT',
        globs=['target/debug/lang-zone.exe', 'target/release/lang-zone.exe',
               'target/debug/lang-zone', 'target/release/lang-zone'],
        aux={
            'lz_builtins_rlib': [
                'target/debug/liblz_builtins.rlib',
                'target/debug/liblz_builtins*.rlib',
                'target/release/liblz_builtins.rlib',
                'target/release/liblz_builtins*.rlib',
            ],
            'lz_builtins_deps': [
                'target/debug/deps',
                'target/release/deps',
            ],
        },
        root_dirname_hints=['lang-zone', 'Lang-Zone', 'lz'],
        install_hint={
            _WIN: '设置 VOOLS_LZ_ROOT 指向 lang-zone 工程根（含 lz_builtins crate）',
            _LNX: '把 lang-zone 所在目录加入 PATH',
            _OSX: '把 lang-zone 所在目录加入 PATH',
        },
    ),
    'zi': ToolchainSpec(
        name='zi',
        commands=['zhi', 'elixir'],
        version_args=['--version'],
        category='中文编程语言',
        kind='pkg',
        root_env='VOOLS_ZI_ROOT',
        globs=['zhi/src'],
        aux={
            'zhi_src': ['zhi/src'],
            'elixir': ['elixir'],
        },
        root_dirname_hints=['兹', 'Zi', 'zi'],
        install_hint={
            _WIN: '设置 VOOLS_ZI_ROOT 指向兹工程根（其下应有 zhi/src）',
            _LNX: '设置 VOOLS_ZI_ROOT 指向兹工程根',
            _OSX: '设置 VOOLS_ZI_ROOT 指向兹工程根',
        },
    ),
    'pentad': ToolchainSpec(
        name='pentad',
        commands=['p5c'],
        version_args=['--version'],
        category='多范式语言',
        root_env='VOOLS_PENTAD_ROOT',
        globs=['target/release/p5c.exe', 'target/debug/p5c.exe',
               'target/release/p5c', 'target/debug/p5c',
               'target/release/**/p5c.exe', 'target/debug/**/p5c.exe'],
        root_dirname_hints=['Pentad', 'pentad'],
        install_hint={
            _WIN: '设置 VOOLS_PENTAD_ROOT 指向 Pentad 工程根，或把 p5c.exe 所在目录加入 PATH',
            _LNX: '设置 VOOLS_PENTAD_ROOT 指向 Pentad 工程根',
            _OSX: '设置 VOOLS_PENTAD_ROOT 指向 Pentad 工程根',
        },
    ),

    # ---------- 系统级编译语言 ----------
    'c': ToolchainSpec(name='c', commands=['gcc', 'clang', 'cl', 'cc'],
                       category='系统级'),
    'cpp': ToolchainSpec(name='cpp', commands=['g++', 'clang++', 'cl', 'c++'],
                         category='系统级'),
    'rust': ToolchainSpec(name='rust', commands=['rustc', 'cargo'], category='系统级'),
    'go': ToolchainSpec(name='go', commands=['go'], version_args=['version'],
                        category='系统级'),
    'nim': ToolchainSpec(name='nim', commands=['nim'], category='系统级'),
    'cangjie': ToolchainSpec(name='cangjie', commands=['cjc'], category='系统级'),
    'zig': ToolchainSpec(name='zig', commands=['zig'], category='系统级'),
    'moonbit': ToolchainSpec(name='moonbit', commands=['moon', 'moonc'],
                             category='系统级'),
    'mojo': ToolchainSpec(name='mojo', commands=['mojo'], category='AI/ML'),

    # ---------- JVM ----------
    'java': ToolchainSpec(name='java', commands=['java', 'javac'], category='JVM'),
    'kotlin': ToolchainSpec(name='kotlin', commands=['kotlinc'], category='JVM'),
    'scala': ToolchainSpec(name='scala', commands=['scala', 'scalac'], category='JVM'),

    # ---------- .NET ----------
    'csharp': ToolchainSpec(name='csharp', commands=['dotnet', 'csc', 'mcs'],
                            category='.NET'),
    'vbnet': ToolchainSpec(name='vbnet', commands=['dotnet', 'vbc'], category='.NET'),
    'powershell': ToolchainSpec(name='powershell', commands=['pwsh', 'powershell'],
                                version_args=['-Command', '$PSVersionTable.PSVersion.ToString()'],
                                category='脚本'),

    # ---------- 解释型 / 脚本 ----------
    'python': ToolchainSpec(name='python', commands=['python', 'python3'],
                            category='脚本'),
    'ruby': ToolchainSpec(name='ruby', commands=['ruby'], category='脚本'),
    'perl': ToolchainSpec(name='perl', commands=['perl'], category='脚本'),
    'php': ToolchainSpec(name='php', commands=['php'], category='脚本'),
    'lua': ToolchainSpec(name='lua', commands=['lua', 'luajit'], category='脚本'),
    'r': ToolchainSpec(name='r', commands=['Rscript', 'R'], category='脚本'),
    'julia': ToolchainSpec(name='julia', commands=['julia'], category='脚本'),
    'dart': ToolchainSpec(name='dart', commands=['dart'], category='脚本'),
    'typescript': ToolchainSpec(name='typescript', commands=['tsc', 'node', 'npm'],
                                category='脚本'),
    'vbscript': ToolchainSpec(name='vbscript', commands=['cscript'], category='脚本'),
    'shell': ToolchainSpec(name='shell', commands=['bash', 'sh', 'zsh'],
                           category='脚本'),
    'swift': ToolchainSpec(name='swift', commands=['swift'], category='系统级'),
    'elixir': ToolchainSpec(name='elixir', commands=['elixir', 'mix'], category='BEAM'),
    'erlang': ToolchainSpec(name='erlang', commands=['erl', 'escript'], category='BEAM'),
    'haskell': ToolchainSpec(name='haskell', commands=['ghc', 'runghc', 'stack'],
                             category='函数式'),
    'freebasic': ToolchainSpec(name='freebasic', commands=['fbc'], category='系统级'),
    'cypy': ToolchainSpec(name='cypy', commands=['cypy'], category='脚本'),
    'md': ToolchainSpec(name='md', commands=[], kind='exe', category='标记'),
}


# ============================================================================
# 运行时状态
# ============================================================================

_OVERRIDES: Dict[str, str] = {}           # lang -> 绝对路径（工具链本体）
_PROJECT_ROOTS: Dict[str, str] = {}       # lang -> 工程根目录
_DISCOVERED: Dict[str, Dict[str, Any]] = {}  # lang -> {path, version, ts}
_USER_CONFIG_LOADED = False
_AUTO_DISCOVERED = False


def _ensure_user_state() -> None:
    """首次调用时加载用户 JSON 并从 VOOLS_PROJECTS_ROOT 扫描工程根（幂等）。"""
    global _USER_CONFIG_LOADED, _AUTO_DISCOVERED
    if not _USER_CONFIG_LOADED:
        load_user_config()
    if not _AUTO_DISCOVERED:
        _AUTO_DISCOVERED = True
        if os.environ.get('VOOLS_PROJECTS_ROOT'):
            discover_project_roots()


# ============================================================================
# 内部工具
# ============================================================================

def _expand_globs(base: str, globs: List[str]) -> List[str]:
    """在 base 下展开 glob 模板，返回存在的路径列表。"""
    found: List[str] = []
    for g in globs:
        pattern = os.path.join(base, g) if not os.path.isabs(g) else g
        matches = glob.glob(pattern, recursive=True)
        for m in matches:
            if m not in found:
                found.append(m)
    return found


def _is_executable(path: str) -> bool:
    """判断路径是否为可执行文件（exe 模式）。"""
    if not path or not os.path.exists(path):
        return False
    if os.path.isdir(path):
        return True  # dir / pkg 模式
    return True


def _spec_env_var(spec: ToolchainSpec, suffix: str) -> Optional[str]:
    """按 spec 推断 env 变量名：VOOLS_<LANG>_<SUFFIX>。"""
    if suffix == 'ROOT' and spec.root_env:
        return spec.root_env
    return 'VOOLS_{}_PATH'.format(spec.name.upper())


# ============================================================================
# 公共 API：spec 查询
# ============================================================================

def get_spec(lang: str) -> Optional[ToolchainSpec]:
    """按语言名取工具链声明（不存在返回 None）。"""
    return DEFAULT_SPECS.get(lang.lower())


def all_specs() -> Dict[str, ToolchainSpec]:
    """返回全部声明。"""
    return dict(DEFAULT_SPECS)


def register_spec(spec: ToolchainSpec) -> None:
    """运行时注册/覆盖一条声明（扩展第三方语言用）。"""
    DEFAULT_SPECS[spec.name.lower()] = spec


# ============================================================================
# 公共 API：运行时覆盖
# ============================================================================

def set_override(lang: str, path: str) -> None:
    """显式指定工具链路径（最高优先级，持久化到用户 JSON）。"""
    _OVERRIDES[lang.lower()] = path


def get_override(lang: str) -> Optional[str]:
    return _OVERRIDES.get(lang.lower())


def clear_override(lang: str) -> bool:
    return _OVERRIDES.pop(lang.lower(), None) is not None


def all_overrides() -> Dict[str, str]:
    return dict(_OVERRIDES)


def set_project_root(lang: str, path: str) -> None:
    """指定语言工程根目录（其下按 globs 找工具链）。"""
    if path:
        _PROJECT_ROOTS[lang.lower()] = path


def get_project_root(lang: str) -> Optional[str]:
    return _PROJECT_ROOTS.get(lang.lower())


def all_project_roots() -> Dict[str, str]:
    return dict(_PROJECT_ROOTS)


def set_discovered(lang: str, path: str, version: str = '') -> None:
    """写入探针发现结果。"""
    _DISCOVERED[lang.lower()] = {
        'path': path,
        'version': version,
        'ts': _now_iso(),
    }


def get_discovered(lang: str) -> Optional[Dict[str, Any]]:
    return _DISCOVERED.get(lang.lower())


def all_discovered() -> Dict[str, Dict[str, Any]]:
    return dict(_DISCOVERED)


# ============================================================================
# 公共 API：解析
# ============================================================================

def resolve_compiler(lang: str) -> Optional[str]:
    """
    解析某语言的工具链路径。

    顺序：overrides → discovered → env(VOOLS_<LANG>_PATH) → project_root+globs
          → PATH(shutil.which) → WSL 回退。

    返回：
        命中返回路径（文件或目录）；未命中返回 None。
    """
    key = lang.lower()
    spec = get_spec(key)
    if spec is None:
        return None
    _ensure_user_state()

    # 1. override
    ov = _OVERRIDES.get(key)
    if ov and os.path.exists(ov):
        return ov

    # 2. discovered
    disc = _DISCOVERED.get(key)
    if disc and disc.get('path') and os.path.exists(disc['path']):
        return disc['path']

    # 3. env: VOOLS_<LANG>_PATH
    env_path = os.environ.get('VOOLS_{}_PATH'.format(spec.name.upper()))
    if env_path and os.path.exists(env_path):
        return env_path

    # 4. env: spec.root_env -> globs
    if spec.root_env:
        root = os.environ.get(spec.root_env)
        if root and os.path.isdir(root):
            found = _expand_globs(root, spec.globs)
            if found:
                return found[0]

    # 5. project_root (runtime) -> globs
    proot = _PROJECT_ROOTS.get(key)
    if proot and os.path.isdir(proot):
        found = _expand_globs(proot, spec.globs)
        if found:
            return found[0]

    # 6. PATH
    if spec.commands:
        for cmd in spec.commands:
            try:
                found = shutil.which(cmd)
            except Exception:
                found = None
            if found and os.path.exists(found):
                return found

    # 7. WSL 回退
    if _IS_WINDOWS and spec.commands:
        try:
            from .core.wsl import check_wsl_command
            for cmd in spec.commands:
                if check_wsl_command(cmd):
                    # 返回命令名，由调用方用 wsl 前缀执行
                    return cmd
        except Exception:
            pass

    return None


def resolve_aux(lang: str, key: str) -> Optional[str]:
    """
    解析附加产物（如 lz 的 lz_builtins rlib）。

    查找顺序：env(VOOLS_<LANG>_<KEY>_PATH) → project_root + aux[key] globs
              → spec.root_env + aux[key] globs。

    返回：命中的路径或 None。
    """
    spec = get_spec(lang)
    if spec is None:
        return None
    _ensure_user_state()
    aux_globs = (spec.aux or {}).get(key)
    if not aux_globs:
        return None

    env_name = 'VOOLS_{}_{}_PATH'.format(spec.name.upper(), key.upper())
    env_val = os.environ.get(env_name)
    if env_val and os.path.exists(env_val):
        return env_val

    roots = []
    proot = _PROJECT_ROOTS.get(lang.lower())
    if proot:
        roots.append(proot)
    if spec.root_env:
        env_root = os.environ.get(spec.root_env)
        if env_root:
            roots.append(env_root)

    for root in roots:
        found = _expand_globs(root, aux_globs)
        if found:
            return found[0]
    return None


# ============================================================================
# 用户侧 JSON 持久化（不进仓库）
# ============================================================================

def get_user_config_path() -> str:
    """用户配置文件路径（可用 VOOLS_BRIDGE_CONFIG 覆盖）。"""
    override = os.environ.get('VOOLS_BRIDGE_CONFIG')
    if override:
        return override
    return os.path.join(os.path.expanduser('~'), '.vools', 'bridge_config.json')


def _now_iso() -> str:
    try:
        from datetime import datetime
        return datetime.now().isoformat(timespec='seconds')
    except Exception:
        return ''


def load_user_config(path: Optional[str] = None) -> int:
    """
    从用户 JSON 加载配置。

    Returns: 加载的键数量。
    """
    global _USER_CONFIG_LOADED
    if path is None:
        path = get_user_config_path()
    if not os.path.exists(path):
        return 0
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return 0

    count = 0
    overrides = data.get('overrides', {})
    for lang, val in overrides.items():
        if isinstance(val, str) and val:
            _OVERRIDES[lang.lower()] = val
            count += 1

    roots = data.get('project_roots', {})
    for lang, val in roots.items():
        if isinstance(val, str) and val:
            _PROJECT_ROOTS[lang.lower()] = val
            count += 1

    disc = data.get('discovered', {})
    for lang, val in disc.items():
        if isinstance(val, dict) and val.get('path'):
            _DISCOVERED[lang.lower()] = {
                'path': val['path'],
                'version': val.get('version', ''),
                'ts': val.get('ts', ''),
            }
            count += 1

    _USER_CONFIG_LOADED = True
    return count


def save_user_config(path: Optional[str] = None) -> str:
    """
    把当前 overrides / project_roots / discovered 写入用户 JSON。

    Returns: 写入的文件路径。
    """
    if path is None:
        path = get_user_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    data = {
        '_comment': 'vools 编译器位置运行时配置。本文件由工具在本机生成，请勿提交/发布。',
        'overrides': dict(_OVERRIDES),
        'project_roots': dict(_PROJECT_ROOTS),
        'discovered': dict(_DISCOVERED),
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def clear_runtime() -> None:
    """清空全部运行时状态（测试/重发现用）。

    同时复位惰性加载标志，确保下一次 resolve_compiler/resolve_aux
    会重新加载用户 JSON 并重新从 VOOLS_PROJECTS_ROOT 扫描工程根。
    """
    global _USER_CONFIG_LOADED, _AUTO_DISCOVERED
    _OVERRIDES.clear()
    _PROJECT_ROOTS.clear()
    _DISCOVERED.clear()
    _USER_CONFIG_LOADED = False
    _AUTO_DISCOVERED = False


# ============================================================================
# 探针：从 VOOLS_PROJECTS_ROOT 扫描项目根（不硬编码路径）
# ============================================================================

def discover_project_roots(roots_hint: Optional[str] = None) -> Dict[str, str]:
    """
    从用户指定的「项目根集合」里扫描各语言工程根并写入运行时。

    读取环境变量 `VOOLS_PROJECTS_ROOT`（多个用 `;` 或 `os.pathsep` 分隔），
    在每个候选根下按 spec.root_dirname_hints 匹配目录名，命中即 set_project_root。

    Args:
        roots_hint: 覆盖 VOOLS_PROJECTS_ROOT（测试用）。

    Returns:
        本扫描发现的 {lang: project_root} 映射（未命中的语言不写入）。
    """
    if roots_hint is None:
        roots_hint = os.environ.get('VOOLS_PROJECTS_ROOT', '')
    if not roots_hint:
        return {}

    sep = ';' if _IS_WINDOWS else os.pathsep
    roots = [r for r in roots_hint.split(sep) if r.strip()]

    found: Dict[str, str] = {}
    for name, spec in DEFAULT_SPECS.items():
        if not spec.root_dirname_hints:
            continue
        for root in roots:
            if not os.path.isdir(root):
                continue
            for hint in spec.root_dirname_hints:
                cand = os.path.join(root, hint)
                if os.path.isdir(cand):
                    set_project_root(name, cand)
                    found[name] = cand
                    break
            if name in found:
                break
    return found


# ============================================================================
# 报告
# ============================================================================

def export_report() -> str:
    """生成当前位置配置的可读报告。"""
    lines = ['=== vools.bridge.configs 报告 ===', '']
    for name, spec in sorted(DEFAULT_SPECS.items()):
        resolved = resolve_compiler(name)
        status = 'OK ' if resolved else 'NO '
        detail = resolved if resolved else ''
        if spec.root_env:
            detail = '{}  [root_env={}]'.format(detail, spec.root_env)
        lines.append('  {} {:12s} {}'.format(status, name, detail))
    lines.append('')
    lines.append('用户 JSON: {}'.format(get_user_config_path()))
    return '\n'.join(lines)


# 模块导出
__all__ = [
    'ToolchainSpec',
    'DEFAULT_SPECS',
    'get_spec',
    'all_specs',
    'register_spec',
    'resolve_compiler',
    'resolve_aux',
    'set_override',
    'get_override',
    'clear_override',
    'all_overrides',
    'set_project_root',
    'get_project_root',
    'all_project_roots',
    'set_discovered',
    'get_discovered',
    'all_discovered',
    'load_user_config',
    'save_user_config',
    'get_user_config_path',
    'clear_runtime',
    'discover_project_roots',
    'export_report',
]