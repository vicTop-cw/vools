"""
vools.bridge.manager - 跨语言桥接统一管理器

提供各种外部语言编译器和运行时环境的统一配置、管理和查询。

核心功能：
1. 语言编译器配置 - 路径、参数、版本检测
2. 依赖库管理 - DLL/so 路径、加载顺序
3. 运行时环境 - PATH、DLL 搜索路径等
4. 统一状态查询 - 某语言是否可用、哪个版本等
5. 路径配置 - 设置编译器路径、库路径等
6. 配置持久化 - 保存/加载配置到文件

用法：
    from vools.bridge.manager import manager, register_language

    # 注册语言
    register_language('nim', {
        'compiler': 'nim',
        'compiler_paths': ['/usr/bin', '/opt/nim/bin'],
        'runtime_paths': ['/usr/lib', '/opt/nim/lib'],
        'dll_dependencies': [],
        'env_setup': True,
    })

    # 查询状态
    print(manager.is_available('nim'))  # True/False
    print(manager.get_compiler_path('nim'))  # '/opt/nim/bin/nim'

    # 设置环境
    manager.setup_runtime('nim')

    # 配置路径
    manager.set_compiler_path('nim', '/custom/nim/bin')
    manager.add_runtime_path('nim', '/custom/nim/lib')
"""

import os
import sys
import platform
import subprocess
import shutil
import ctypes
import threading
import json
from typing import Dict, List, Optional, Callable, Any
from vools.core.dataclass_compat import dataclass, field, asdict

# 平台判断
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# ============================================================================
# 语言配置数据类
# ============================================================================

@dataclass
class LanguageConfig:
    """
    单个语言的配置

    属性：
        name: 语言名称（小写，如 'nim', 'rust', 'c'）
        compiler: 编译器命令名（如 'nim', 'rustc', 'gcc'）
        compiler_paths: 编译器搜索路径列表
        runtime_paths: 运行时库搜索路径列表
        dll_dependencies: 依赖的 DLL/so 文件列表（仅 Windows）
        env_setup: 是否自动设置环境变量
        version_check: 版本检测命令（默认 ['compiler', '--version']）
        version_pattern: 版本号提取正则（可选）
        compile_cmd_template: 编译命令模板
        library_prefix: 库的命名前缀（如 'lib'）
        library_suffix: 库的命名后缀（如 '.so', '.dll'）
        extra_env: 额外的环境变量 dict
    """
    name: str
    compiler: str
    compiler_paths: List[str] = field(default_factory=list)
    runtime_paths: List[str] = field(default_factory=list)
    dll_dependencies: List[str] = field(default_factory=list)
    env_setup: bool = True
    version_check: List[str] = None
    version_pattern: str = None
    compile_cmd_template: str = None
    library_prefix: str = ''
    library_suffix: str = ''
    extra_env: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.version_check is None:
            self.version_check = [self.compiler, '--version']

        if _IS_WINDOWS and self.library_suffix == '':
            self.library_suffix = '.dll'
        elif _IS_LINUX and self.library_suffix == '':
            self.library_suffix = '.so'
        elif _IS_MACOS and self.library_suffix == '':
            self.library_suffix = '.dylib'


@dataclass
class LanguageStatus:
    """
    语言的运行时状态

    属性：
        available: 是否可用
        compiler_path: 编译器路径（如果可用）
        version: 检测到的版本号
        runtime_ready: 运行时环境是否就绪
        error: 错误信息（如果不可用）
    """
    available: bool = False
    compiler_path: Optional[str] = None
    version: Optional[str] = None
    runtime_ready: bool = False
    error: Optional[str] = None


# ============================================================================
# 全局语言注册表
# ============================================================================

_LANGUAGE_REGISTRY: Dict[str, LanguageConfig] = {}
_STATUS_CACHE: Dict[str, LanguageStatus] = {}
_CACHE_LOCK = threading.Lock()


# ============================================================================
# 内部工具函数
# ============================================================================

def _find_executable(name: str, extra_paths: List[str] = None) -> Optional[str]:
    """
    查找可执行文件路径

    参数：
        name: 可执行文件名
        extra_paths: 额外的搜索路径

    返回：
        找到的路径，不存在返回 None
    """
    # 先检查系统 PATH
    system_path = shutil.which(name)
    if system_path and os.path.exists(system_path):
        return system_path

    # 检查额外路径
    if extra_paths:
        for base_dir in extra_paths:
            if not base_dir:
                continue
            # Windows 可能需要加 .exe
            candidate = os.path.join(base_dir, name)
            if _IS_WINDOWS:
                candidate_exe = candidate + '.exe'
                if os.path.exists(candidate_exe):
                    return candidate_exe
            if os.path.exists(candidate):
                return candidate

    return None


def _run_version_check(config: LanguageConfig) -> tuple:
    """
    执行版本检测

    返回：
        (success: bool, output: str, version: str or None)
    """
    compiler_path = _find_executable(config.compiler, config.compiler_paths)
    if not compiler_path:
        return False, '', None

    cmd = config.version_check.copy()
    cmd[0] = compiler_path  # 替换为实际路径

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            output = result.stdout.strip() or result.stderr.strip()
            version = None
            if config.version_pattern:
                import re
                match = re.search(config.version_pattern, output)
                if match:
                    version = match.group(1)
            return True, output, version or ''
        return False, result.stderr, None
    except Exception as e:
        return False, str(e), None


def _setup_dll_search_paths(paths: List[str]) -> None:
    """
    设置 Windows DLL 搜索路径

    参数：
        paths: DLL 搜索路径列表
    """
    if not _IS_WINDOWS:
        return

    add_dll_dir = getattr(os, 'add_dll_directory', None)
    if add_dll_dir:
        for p in paths:
            if os.path.exists(p):
                try:
                    add_dll_dir(p)
                except OSError:
                    pass


def _setup_env_paths(paths: List[str], key: str = 'PATH') -> None:
    """
    添加路径到环境变量

    参数：
        paths: 要添加的路径列表
        key: 环境变量名（默认 'PATH'）
    """
    current = os.environ.get(key, '')
    sep = os.pathsep

    new_paths = []
    for p in paths:
        if p and p not in current.split(sep):
            new_paths.append(p)

    if new_paths:
        os.environ[key] = sep.join(new_paths) + sep + current


# ============================================================================
# BridgeManager 类
# ============================================================================

class BridgeManager:
    """
    跨语言桥接统一管理器

    提供语言配置的注册、查询、运行时环境设置等统一接口。

    用法：
        manager = BridgeManager()

        # 手动注册
        manager.register(LanguageConfig(
            name='nim',
            compiler='nim',
            compiler_paths=['/opt/nim/bin'],
        ))

        # 查询状态
        status = manager.get_status('nim')
        print(f"Nim 可用: {status.available}, 版本: {status.version}")

        # 设置运行时环境
        manager.setup_runtime('nim')
    """

    def __init__(self):
        self._configs: Dict[str, LanguageConfig] = {}
        self._status_cache: Dict[str, LanguageStatus] = {}
        self._cache_lock = threading.Lock()
        self._initialized = False

    # ------------------------------------------------------------------------
    # 注册和配置
    # ------------------------------------------------------------------------

    def register(self, config: LanguageConfig) -> None:
        """
        注册语言配置

        参数：
            config: LanguageConfig 实例
        """
        self._configs[config.name.lower()] = config
        # 清除缓存
        with self._cache_lock:
            self._status_cache.pop(config.name.lower(), None)

    def register_language(self, name: str, **kwargs) -> LanguageConfig:
        """
        便捷方法：注册语言配置（通过关键字参数）

        参数：
            name: 语言名称
            **kwargs: LanguageConfig 的属性

        返回：
            创建的 LanguageConfig 实例
        """
        config = LanguageConfig(name=name, compiler=kwargs.pop('compiler', name), **kwargs)
        self.register(config)
        return config

    def get_config(self, name: str) -> Optional[LanguageConfig]:
        """
        获取语言配置

        参数：
            name: 语言名称

        返回：
            LanguageConfig 实例，不存在返回 None
        """
        return self._configs.get(name.lower())

    def unregister(self, name: str) -> bool:
        """
        取消注册语言

        参数：
            name: 语言名称

        返回：
            是否成功取消
        """
        with self._cache_lock:
            self._status_cache.pop(name.lower(), None)
        return self._configs.pop(name.lower(), None) is not None

    # ------------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------------

    def is_available(self, name: str) -> bool:
        """
        检查语言是否可用

        参数：
            name: 语言名称

        返回：
            是否可用
        """
        return self.get_status(name).available

    def get_status(self, name: str, use_cache: bool = True) -> LanguageStatus:
        """
        获取语言详细状态

        参数：
            name: 语言名称
            use_cache: 是否使用缓存

        返回：
            LanguageStatus 实例
        """
        name_lower = name.lower()

        # 检查缓存
        if use_cache:
            with self._cache_lock:
                if name_lower in self._status_cache:
                    return self._status_cache[name_lower]

        config = self._configs.get(name_lower)
        if not config:
            status = LanguageStatus(available=False, error=f"Language '{name}' not registered")
        else:
            status = self._check_status(config)

        # 更新缓存
        with self._cache_lock:
            self._status_cache[name_lower] = status

        return status

    def _check_status(self, config: LanguageConfig) -> LanguageStatus:
        """检查语言状态"""
        # 1. 查找编译器
        compiler_path = _find_executable(config.compiler, config.compiler_paths)
        if not compiler_path:
            return LanguageStatus(
                available=False,
                error=f"Compiler '{config.compiler}' not found in paths: {config.compiler_paths}"
            )

        # 2. 版本检测
        success, output, version = _run_version_check(config)
        if not success:
            return LanguageStatus(
                available=False,
                compiler_path=compiler_path,
                error=f"Version check failed: {output}"
            )

        # 3. 检查运行时依赖
        runtime_ready = True
        if _IS_WINDOWS and config.dll_dependencies:
            for dll in config.dll_dependencies:
                dll_path = _find_executable(dll, config.runtime_paths)
                if not dll_path and not os.path.exists(dll):
                    runtime_ready = False
                    break

        return LanguageStatus(
            available=True,
            compiler_path=compiler_path,
            version=version,
            runtime_ready=runtime_ready
        )

    def get_compiler_path(self, name: str) -> Optional[str]:
        """
        获取编译器路径

        参数：
            name: 语言名称

        返回：
            编译器路径，不存在返回 None
        """
        return self.get_status(name).compiler_path

    def get_version(self, name: str) -> Optional[str]:
        """
        获取语言版本

        参数：
            name: 语言名称

        返回：
            版本号字符串，不存在返回 None
        """
        return self.get_status(name).version

    def list_languages(self) -> List[str]:
        """
        列出所有已注册的语言

        返回：
            语言名称列表
        """
        return list(self._configs.keys())

    def list_available(self) -> List[str]:
        """
        列出所有可用的语言

        返回：
            可用的语言名称列表
        """
        return [name for name, cfg in self._configs.items() if self.is_available(name)]

    # ------------------------------------------------------------------------
    # 运行时环境设置
    # ------------------------------------------------------------------------

    def setup_runtime(self, name: str) -> bool:
        """
        设置语言的运行时环境

        包括：
        - 添加编译器路径到 PATH
        - 添加运行时库路径到 PATH
        - Windows 上添加 DLL 搜索路径

        参数：
            name: 语言名称

        返回：
            是否成功
        """
        config = self._configs.get(name.lower())
        if not config:
            return False

        if not config.env_setup:
            return True

        # 1. 设置 PATH
        all_paths = list(config.compiler_paths) + list(config.runtime_paths)
        _setup_env_paths(all_paths)

        # 2. Windows DLL 搜索路径
        if _IS_WINDOWS:
            _setup_dll_search_paths(config.runtime_paths)

        # 3. 额外环境变量
        for key, value in config.extra_env.items():
            os.environ[key] = value

        return True

    def setup_all_runtimes(self) -> int:
        """
        设置所有已注册语言的运行时环境

        返回：
            成功设置的语言数量
        """
        count = 0
        for name in self._configs:
            if self.setup_runtime(name):
                count += 1
        return count

    # ------------------------------------------------------------------------
    # 缓存管理
    # ------------------------------------------------------------------------

    def clear_cache(self, name: str = None) -> None:
        """
        清除状态缓存

        参数：
            name: 语言名称，为 None 则清除所有缓存
        """
        with self._cache_lock:
            if name:
                self._status_cache.pop(name.lower(), None)
            else:
                self._status_cache.clear()

    # ------------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------------

    def find_library(self, name: str, lib_name: str) -> Optional[str]:
        """
        查找库文件路径

        参数：
            name: 语言名称
            lib_name: 库名称（不含前后缀）

        返回：
            库文件完整路径，不存在返回 None
        """
        config = self._configs.get(name.lower())
        if not config:
            return None

        suffixes = [config.library_suffix]
        if _IS_WINDOWS:
            suffixes = ['.dll', '.pyd', '.so']
        elif _IS_LINUX:
            suffixes = ['.so', '.a']
        elif _IS_MACOS:
            suffixes = ['.dylib', '.so']

        for suffix in suffixes:
            for path in config.runtime_paths:
                candidate = os.path.join(path, config.library_prefix + lib_name + suffix)
                if os.path.exists(candidate):
                    return candidate

        # 尝试系统搜索
        for suffix in suffixes:
            system_candidate = config.library_prefix + lib_name + suffix
            found = shutil.which(system_candidate)
            if found:
                return found

        return None

    # ------------------------------------------------------------------------
    # 路径配置管理
    # ------------------------------------------------------------------------

    def set_compiler_path(self, name: str, path: str) -> bool:
        """
        设置编译器的搜索路径（覆盖默认路径）

        参数：
            name: 语言名称
            path: 编译器目录路径

        返回：
            是否成功
        """
        config = self._configs.get(name.lower())
        if not config:
            return False

        if os.path.isdir(path):
            config.compiler_paths = [path]
            self.clear_cache(name)
            return True
        return False

    def add_compiler_path(self, name: str, path: str) -> bool:
        """
        添加编译器搜索路径（追加到列表）

        参数：
            name: 语言名称
            path: 编译器目录路径

        返回：
            是否成功
        """
        config = self._configs.get(name.lower())
        if not config:
            return False

        if os.path.isdir(path) and path not in config.compiler_paths:
            config.compiler_paths.append(path)
            self.clear_cache(name)
            return True
        return False

    def set_runtime_path(self, name: str, path: str) -> bool:
        """
        设置运行时库的搜索路径（覆盖默认路径）

        参数：
            name: 语言名称
            path: 运行时库目录路径

        返回：
            是否成功
        """
        config = self._configs.get(name.lower())
        if not config:
            return False

        if os.path.isdir(path):
            config.runtime_paths = [path]
            self.clear_cache(name)
            return True
        return False

    def add_runtime_path(self, name: str, path: str) -> bool:
        """
        添加运行时库搜索路径（追加到列表）

        参数：
            name: 语言名称
            path: 运行时库目录路径

        返回：
            是否成功
        """
        config = self._configs.get(name.lower())
        if not config:
            return False

        if os.path.isdir(path) and path not in config.runtime_paths:
            config.runtime_paths.append(path)
            self.clear_cache(name)
            return True
        return False

    def get_all_paths(self, name: str) -> dict:
        """
        获取语言的所有路径配置

        参数：
            name: 语言名称

        返回：
            dict: {
                'compiler': str or None,
                'compiler_paths': list,
                'runtime_paths': list
            }
        """
        config = self._configs.get(name.lower())
        if not config:
            return {
                'compiler': None,
                'compiler_paths': [],
                'runtime_paths': []
            }

        status = self.get_status(name)
        return {
            'compiler': status.compiler_path,
            'compiler_paths': config.compiler_paths,
            'runtime_paths': config.runtime_paths
        }

    # ------------------------------------------------------------------------
    # 配置持久化
    # ------------------------------------------------------------------------

    def save_config(self, file_path: str = None) -> str:
        """
        保存配置到文件

        参数：
            file_path: 配置文件路径，默认为用户配置目录

        返回：
            保存的文件路径
        """
        if file_path is None:
            config_dir = os.path.join(os.path.expanduser('~'), '.vools')
            os.makedirs(config_dir, exist_ok=True)
            file_path = os.path.join(config_dir, 'bridge_manager.json')

        config_data = {}
        for name, config in self._configs.items():
            config_data[name] = {
                'name': config.name,
                'compiler': config.compiler,
                'compiler_paths': config.compiler_paths,
                'runtime_paths': config.runtime_paths,
                'dll_dependencies': config.dll_dependencies,
                'env_setup': config.env_setup,
                'version_pattern': config.version_pattern,
                'library_prefix': config.library_prefix,
                'library_suffix': config.library_suffix,
            }

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        return file_path

    def load_config(self, file_path: str = None) -> int:
        """
        从文件加载配置

        参数：
            file_path: 配置文件路径，默认为用户配置目录

        返回：
            加载的配置项数量
        """
        if file_path is None:
            config_dir = os.path.join(os.path.expanduser('~'), '.vools')
            file_path = os.path.join(config_dir, 'bridge_manager.json')

        if not os.path.exists(file_path):
            return 0

        with open(file_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        count = 0
        for name, data in config_data.items():
            config = LanguageConfig(
                name=data.get('name', name),
                compiler=data.get('compiler', name),
                compiler_paths=data.get('compiler_paths', []),
                runtime_paths=data.get('runtime_paths', []),
                dll_dependencies=data.get('dll_dependencies', []),
                env_setup=data.get('env_setup', True),
                version_pattern=data.get('version_pattern'),
                library_prefix=data.get('library_prefix', ''),
                library_suffix=data.get('library_suffix', ''),
            )
            self.register(config)
            count += 1

        return count

    def get_config_file_path(self) -> str:
        """
        获取默认配置文件路径

        返回：
            配置文件路径
        """
        config_dir = os.path.join(os.path.expanduser('~'), '.vools')
        return os.path.join(config_dir, 'bridge_manager.json')


# ============================================================================
# 全局管理器实例
# ============================================================================

manager = BridgeManager()


# ============================================================================
# 内置语言预配置
# ============================================================================

_initialized = False

def _register_builtin_languages():
    """注册内置语言配置"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    # C (gcc/clang) - 特殊，C 不需要编译器路径，它直接调用系统工具
    manager.register(LanguageConfig(
        name='c',
        compiler='gcc' if _IS_WINDOWS else 'cc',
        compiler_paths=[
            r'C:\MinGW\bin' if _IS_WINDOWS else '/usr/bin',
            r'C:\msys64\mingw64\bin' if _IS_WINDOWS else '/usr/local/bin',
        ],
        runtime_paths=[
            r'C:\MinGW\bin' if _IS_WINDOWS else '/usr/lib',
            r'C:\msys64\mingw64\bin' if _IS_WINDOWS else '/usr/local/lib',
        ],
        version_check=['gcc', '--version'] if _IS_WINDOWS else ['cc', '--version'],
        library_suffix='.dll' if _IS_WINDOWS else '.so',
    ))

    # Nim
    nim_paths = []
    if _IS_WINDOWS:
        nim_paths = [
            r'E:\Dowloads\nim-2.2.10_x64\nim-2.2.10\bin',
            r'C:\Users\victo\.codearts-cpp\tools\mingw\bin',
            r'C:\Program Files\Nim\bin',
            r'C:\nim\bin',
        ]
    else:
        nim_paths = [
            '/home/vic/nim-2.2.10/bin',
            '/opt/nim/bin',
            '/usr/local/bin',
            '/usr/bin',
        ]

    manager.register(LanguageConfig(
        name='nim',
        compiler='nim' + ('.exe' if _IS_WINDOWS else ''),
        compiler_paths=nim_paths,
        runtime_paths=nim_paths,
        dll_dependencies=['libgcc_s_seh-1.dll', 'libwinpthread-1.dll'] if _IS_WINDOWS else [],
        version_pattern=r'version (\d+\.\d+\.\d+)',
    ))

    # Rust
    rust_paths = []
    if _IS_WINDOWS:
        rust_paths = [
            os.path.expanduser('~/.cargo/bin'),
            r'C:\Program Files\Rust\.cargo\bin',
        ]
    else:
        rust_paths = [
            os.path.expanduser('~/.cargo/bin'),
            '/usr/local/cargo/bin',
            '/usr/bin',
        ]

    manager.register(LanguageConfig(
        name='rust',
        compiler='rustc' + ('.exe' if _IS_WINDOWS else ''),
        compiler_paths=rust_paths,
        runtime_paths=rust_paths,
        library_prefix='lib',
        library_suffix='.dll' if _IS_WINDOWS else '.so',
    ))

    # C++
    if _IS_WINDOWS:
        cpp_paths = [
            r'C:\MinGW\bin',
            r'C:\msys64\mingw64\bin',
            r'C:\Program Files\LLVM\bin',
        ]
    else:
        cpp_paths = ['/usr/bin', '/usr/local/bin']

    manager.register(LanguageConfig(
        name='cpp',
        compiler='g++' if _IS_WINDOWS else 'c++',
        compiler_paths=cpp_paths,
        runtime_paths=cpp_paths,
        version_check=['g++', '--version'] if _IS_WINDOWS else ['c++', '--version'],
    ))

    # Go
    go_paths = []
    if _IS_WINDOWS:
        go_paths = [
            r'C:\Go\bin',
            os.path.expanduser(r'~\go\bin'),
        ]
    else:
        go_paths = ['/usr/local/go/bin', '/usr/lib/go/bin', os.path.expanduser('~/go/bin')]

    manager.register(LanguageConfig(
        name='go',
        compiler='go' + ('.exe' if _IS_WINDOWS else ''),
        compiler_paths=go_paths,
        runtime_paths=go_paths,
        version_pattern=r'go(\d+\.\d+\.\d+)',
    ))

    # Java
    java_paths = []
    if _IS_WINDOWS:
        java_paths = [
            r'C:\Program Files\Java\jdk*\bin',
            r'C:\Program Files\Eclipse Adoptium\jdk*\bin',
        ]
    else:
        java_paths = ['/usr/lib/jvm/java*/bin', '/usr/java/bin', '/usr/local/java/bin']

    manager.register(LanguageConfig(
        name='java',
        compiler='java' + ('.exe' if _IS_WINDOWS else ''),
        compiler_paths=java_paths,
        runtime_paths=java_paths,
        version_pattern=r'version "(\d+\.\d+\.\d+)',
    ))

    # C#
    if _IS_WINDOWS:
        csharp_paths = [
            r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319',
            r'C:\Program Files\dotnet',
        ]
    else:
        csharp_paths = ['/usr/share/dotnet', '/usr/local/share/dotnet']

    manager.register(LanguageConfig(
        name='csharp',
        compiler='dotnet',
        compiler_paths=csharp_paths,
        runtime_paths=csharp_paths,
    ))

    # Julia
    julia_paths = []
    if _IS_WINDOWS:
        julia_paths = [
            r'C:\Users\victo\AppData\Local\Programs\Julia-1.11.0\bin',
            r'C:\Program Files\Julia-1.11.0\bin',
            r'C:\Users\victo\AppData\Local\Microsoft\WindowsApps',
            os.path.expanduser('~/AppData/Local/Programs/Julia-1.11.0/bin'),
        ]
    else:
        julia_paths = [
            '/home/julia/bin',
            '/usr/local/julia/bin',
            '/opt/julia/bin',
            os.path.expanduser('~/julia/bin'),
            '/usr/bin',
        ]

    manager.register(LanguageConfig(
        name='julia',
        compiler='julia' + ('.exe' if _IS_WINDOWS else ''),
        compiler_paths=julia_paths,
        runtime_paths=julia_paths,
        version_pattern=r'version (\d+\.\d+\.\d+)',
    ))

    # FreeBASIC
    fbc_paths = []
    if _IS_WINDOWS:
        fbc_paths = [
            r'C:\FreeBASIC',
            r'C:\Program Files\FreeBASIC',
            os.path.expanduser('~\\FreeBASIC'),
        ]
    else:
        fbc_paths = ['/usr/local/bin', '/usr/bin', '/opt/freebasic/bin']

    manager.register(LanguageConfig(
        name='freebasic',
        compiler='fbc64' + ('.exe' if _IS_WINDOWS else ''),
        compiler_paths=fbc_paths,
        runtime_paths=fbc_paths,
        library_suffix='.dll' if _IS_WINDOWS else '.so',
    ))

    # 仓颉 (CangJie)
    cangjie_paths = []
    if _IS_WINDOWS:
        cangjie_paths = [
            r'C:\cangjie',
            r'C:\Program Files\Huawei\cangjie',
            os.path.expanduser('~\\cangjie'),
        ]
    else:
        cangjie_paths = ['/opt/cangjie/bin', '/usr/local/bin', '/usr/bin']

    manager.register(LanguageConfig(
        name='cangjie',
        compiler='cjc' + ('.exe' if _IS_WINDOWS else ''),
        compiler_paths=cangjie_paths,
        runtime_paths=cangjie_paths,
        library_suffix='.dll' if _IS_WINDOWS else '.so',
    ))

    # Scala (使用 Java 运行时)
    if _IS_WINDOWS:
        scala_paths = [
            r'C:\Program Files\scala\bin',
            r'C:\Program Files (x86)\scala\bin',
        ]
    else:
        scala_paths = ['/usr/local/bin', '/usr/bin', '/opt/scala/bin']

    manager.register(LanguageConfig(
        name='scala',
        compiler='scala' + ('.exe' if _IS_WINDOWS else ''),
        compiler_paths=scala_paths,
        runtime_paths=java_paths,  # 复用 Java 路径
    ))

    # R
    r_paths = []
    if _IS_WINDOWS:
        r_paths = [
            r'C:\Program Files\R\R-4.*\bin\x64',
            r'C:\Program Files\R\R-4.*\bin',
        ]
    else:
        r_paths = ['/usr/bin', '/usr/local/bin', '/opt/R/bin']

    manager.register(LanguageConfig(
        name='r',
        compiler='Rscript' + ('.exe' if _IS_WINDOWS else ''),
        compiler_paths=r_paths,
        runtime_paths=r_paths,
        version_pattern=r'version (\d+\.\d+\.\d+)',
    ))

    # Mojo
    mojo_paths = []
    if _IS_WINDOWS:
        mojo_paths = [
            r'C:\Users\victo\.modular\mojo',
            os.path.expanduser('~\\.modular\\mojo'),
        ]
    else:
        mojo_paths = [
            os.path.expanduser('~/.modular/mojo/bin'),
            '/opt/mojo/bin',
            '/usr/local/bin',
        ]

    manager.register(LanguageConfig(
        name='mojo',
        compiler='mojo' + ('.exe' if _IS_WINDOWS else ''),
        compiler_paths=mojo_paths,
        runtime_paths=mojo_paths,
        version_pattern=r'Mojo (\d+\.\d+\.\d+)',
    ))


# 注册内置语言
_register_builtin_languages()


# ============================================================================
# 便捷函数（导出到模块级别）
# ============================================================================

def register_language(name: str, **kwargs) -> LanguageConfig:
    """
    便捷函数：注册语言配置

    用法：
        register_language('nim', compiler='nim', compiler_paths=['/opt/nim/bin'])
    """
    return manager.register_language(name, **kwargs)


def is_available(name: str) -> bool:
    """便捷函数：检查语言是否可用"""
    return manager.is_available(name)


def get_status(name: str) -> LanguageStatus:
    """便捷函数：获取语言状态"""
    return manager.get_status(name)


def get_compiler_path(name: str) -> Optional[str]:
    """便捷函数：获取编译器路径"""
    return manager.get_compiler_path(name)


def get_version(name: str) -> Optional[str]:
    """便捷函数：获取版本"""
    return manager.get_version(name)


def setup_runtime(name: str) -> bool:
    """便捷函数：设置运行时环境"""
    return manager.setup_runtime(name)


def list_languages() -> List[str]:
    """便捷函数：列出已注册的语言"""
    return manager.list_languages()


def list_available() -> List[str]:
    """便捷函数：列出可用的语言"""
    return manager.list_available()


def set_compiler_path(name: str, path: str) -> bool:
    """便捷函数：设置编译器搜索路径"""
    return manager.set_compiler_path(name, path)


def add_compiler_path(name: str, path: str) -> bool:
    """便捷函数：添加编译器搜索路径"""
    return manager.add_compiler_path(name, path)


def set_runtime_path(name: str, path: str) -> bool:
    """便捷函数：设置运行时库搜索路径"""
    return manager.set_runtime_path(name, path)


def add_runtime_path(name: str, path: str) -> bool:
    """便捷函数：添加运行时库搜索路径"""
    return manager.add_runtime_path(name, path)


def get_all_paths(name: str) -> dict:
    """便捷函数：获取语言的所有路径"""
    return manager.get_all_paths(name)


def save_config(file_path: str = None) -> str:
    """便捷函数：保存配置到文件"""
    return manager.save_config(file_path)


def load_config(file_path: str = None) -> int:
    """便捷函数：从文件加载配置"""
    return manager.load_config(file_path)


def get_config_file_path() -> str:
    """便捷函数：获取默认配置文件路径"""
    return manager.get_config_file_path()


def get_compiler(name: str) -> tuple:
    """
    获取编译器的完整信息

    参数：
        name: 语言名称

    返回：
        tuple: (compiler_path, config)
        - compiler_path: 编译器完整路径，不存在为 None
        - config: LanguageConfig 实例
    """
    config = manager.get_config(name)
    if not config:
        return None, None
    return manager.get_compiler_path(name), config


def get_compiler_executable(name: str, executable: str = None) -> str:
    """
    获取特定可执行文件的路径

    参数：
        name: 语言名称
        executable: 可执行文件名（如 'cargo', 'dotnet'），默认使用语言配置中的 compiler

    返回：
        可执行文件完整路径，不存在返回命令名本身
    """
    config = manager.get_config(name)
    if not config:
        return executable or name

    cmd = executable or config.compiler
    compiler_path = manager.get_compiler_path(name)
    if compiler_path:
        # 返回包含完整路径的命令
        return os.path.join(os.path.dirname(compiler_path), cmd)

    return cmd


class LanguageCompilerHelper:
    """
    语言编译器辅助类

    封装通用的编译器检测和调用逻辑，各语言模块可以使用此类来：
    1. 检测编译器是否可用
    2. 获取编译器路径
    3. 执行编译器命令

    用法：
        helper = LanguageCompilerHelper('nim')

        if helper.is_available():
            print(helper.get_compiler_path())

        result = helper.run(['--version'])
        print(result.stdout)
    """

    def __init__(self, name: str):
        """
        初始化辅助类

        参数：
            name: 语言名称
        """
        self.name = name
        self._status = None

    @property
    def status(self) -> LanguageStatus:
        """获取语言状态（带缓存）"""
        if self._status is None:
            self._status = manager.get_status(self.name)
        return self._status

    def is_available(self) -> bool:
        """检查编译器是否可用"""
        return self.status.available

    def get_compiler_path(self) -> Optional[str]:
        """获取编译器路径"""
        return self.status.compiler_path

    def get_version(self) -> Optional[str]:
        """获取编译器版本"""
        return self.status.version

    def setup_env(self) -> bool:
        """设置运行时环境"""
        return manager.setup_runtime(self.name)

    def run(self, args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """
        执行编译器命令

        参数：
            args: 命令参数列表
            timeout: 超时时间（秒）

        返回：
            subprocess.CompletedProcess 对象
        """
        compiler_path = self.get_compiler_path()
        if not compiler_path:
            raise RuntimeError(f"Compiler for '{self.name}' not available")

        cmd = [compiler_path] + args
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )

    def run_and_check(self, args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """
        执行编译器命令并检查返回码

        参数：
            args: 命令参数列表
            timeout: 超时时间（秒）

        返回：
            subprocess.CompletedProcess 对象

        异常：
            RuntimeError: 命令返回非零退出码
        """
        result = self.run(args, timeout)
        if result.returncode != 0:
            raise RuntimeError(
                f"Compiler command failed:\n"
                f"Command: {' '.join(result.args)}\n"
                f"Stderr: {result.stderr}\n"
                f"Stdout: {result.stdout}"
            )
        return result


def get_helper(name: str) -> LanguageCompilerHelper:
    """
    获取语言编译器辅助类实例

    参数：
        name: 语言名称

    返回：
        LanguageCompilerHelper 实例
    """
    return LanguageCompilerHelper(name)


# 导出
__all__ = [
    'manager',
    'LanguageConfig',
    'LanguageStatus',
    'BridgeManager',
    'LanguageCompilerHelper',
    'register_language',
    'is_available',
    'get_status',
    'get_compiler_path',
    'get_compiler',
    'get_compiler_executable',
    'get_helper',
    'get_version',
    'setup_runtime',
    'list_languages',
    'list_available',
    # 路径配置
    'set_compiler_path',
    'add_compiler_path',
    'set_runtime_path',
    'add_runtime_path',
    'get_all_paths',
    # 配置持久化
    'save_config',
    'load_config',
    'get_config_file_path',
]
