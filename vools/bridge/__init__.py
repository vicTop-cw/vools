"""
vools.bridge - 跨语言桥接框架

提供统一的 Python 到其他语言的桥接能力，基于 LangBridge 抽象基类，
所有 27 种语言使用一致的装饰器接口，支持自动编译、缓存和回退机制。

支持的 27 种语言：
  FreeBASIC / C / C++ / Nim / Go / CangJie / Rust / Mojo / MoonBit / C# / Java / Scala / Ruby / Julia / R / TypeScript / VB.NET / Perl / Lua / Zig / Kotlin / Swift / PHP / Dart / PowerShell / VBScript / Shell

LangBridge 统一接口：
  所有语言桥接模块均继承自 LangBridge 抽象基类，提供统一的 decorator() 装饰器工厂。
  核心方法：compiler_available() / generate_code() / compile_code() / call_func()

三种使用模式：
  1. 单函数装饰器模式 - 函数体即目标语言代码，首次调用自动编译
  2. only_code 仅代码模式 - 只生成代码不编译，支持多种写入模式
  3. project 项目模式 - 编译整个项目目录，支持可执行文件或共享库

编译器自动发现：
  自动探测本机和 WSL 环境中已安装的编译器，无需手动配置 PATH。
  - discover_all() / discover_local() / discover_wsl() - 发现编译器
  - get_discovery_report() - 生成发现报告
  - configure_from_discovery() - 自动配置 BridgeManager
  - auto_discover() - 一键发现并配置

子模块：
- core: 核心基础设施（加载器、装饰器、类型映射、序列化）
- manager: 语言编译器和运行时环境统一管理器
- probe: 编译器自动探测模块
- auto_discovery: 一键自动发现与配置
- _base: LangBridge 抽象基类 + FunctionParser / DepResolver 工具类
- c / cpp / nim / go / cangjie / rust / mojo / csharp / java / scala / ruby / julia / r / freebasic / typescript / vbnet / perl / lua / zig / kotlin / swift / php / dart / powershell / vbscript / shell: 各语言桥接实现
"""

from .core.loader import LibraryLoader, SharedLibrary, load_library, load_from_path, is_available
from .core.types import CTypeMapper
from .core.decorators import bridge_function, bridge_module, bridge_func_name
from .core.serialization import Serializer

# manager 模块 - 语言编译器和运行时环境统一管理
from .manager import (
    manager,
    LanguageConfig,
    LanguageStatus,
    BridgeManager,
    LanguageCompilerHelper,
    register_language,
    get_status,
    get_compiler_path,
    get_compiler,
    get_compiler_executable,
    get_helper,
    get_version,
    setup_runtime,
    list_languages,
    list_available,
    auto_discover,
)

# auto_discovery 模块 - 一键自动发现
from .auto_discovery import (
    discover_all,
    discover_local,
    discover_wsl,
    get_discovery_report,
    configure_from_discovery,
)

# 便捷函数：检查语言是否可用
def _lang_is_available(name):
    """检查语言是否可用（委托给 manager）"""
    return manager.is_available(name)

__all__ = [
    # core 模块
    'LibraryLoader',
    'SharedLibrary',
    'load_library',
    'load_from_path',
    'is_available',
    'CTypeMapper',
    'bridge_function',
    'bridge_module',
    'bridge_func_name',
    'Serializer',

    # manager 模块
    'manager',
    'LanguageConfig',
    'LanguageStatus',
    'BridgeManager',
    'LanguageCompilerHelper',
    'register_language',
    'get_status',
    'get_compiler_path',
    'get_compiler',
    'get_compiler_executable',
    'get_helper',
    'get_version',
    'setup_runtime',
    'list_languages',
    'list_available',
    'auto_discover',

    # auto_discovery 模块
    'discover_all',
    'discover_local',
    'discover_wsl',
    'get_discovery_report',
    'configure_from_discovery',
    'set_compiler_path',
    'add_compiler_path',
    'set_runtime_path',
    'add_runtime_path',
    'get_all_paths',
    'save_config',
    'load_config',
    'get_config_file_path',

    # c 模块
    'load_dll',
    'call_func',
    'c_dll',
    'CDLLWrapper',

    # cpp 模块
    'cpp',
    'cpp_compiler_available',
    'get_cpp_compiler_info',
    'compile_and_run_cpp',
    'load_cpp_dll',
    'call_cpp_func',

    # nim 模块
    'nim',
    'compile_and_run',
    'nim_compiler_available',
    'is_nim_available',

    # cangjie 模块
    'cangjie',
    'cjc_compiler_available',

    # go 模块
    'go',
    'go_compiler_available',
    'is_go_available',

    # r 模块
    'r',
    'r_compiler_available',

    # ruby 模块
    'ruby',
    'ruby_compiler_available',
    'is_ruby_available',

    # typescript 模块
    'typescript',
    'ts',
    'ts_compiler_available',
    'is_typescript_available',
    'is_node_available',

    # 子模块
    'core',
    'manager',
    'c',
    'nim',
    'rust',
    'cpp',
    'csharp',
    'mojo',
    'freebasic',
    'scala',
    'java',
    'cangjie',
    'go',
    'r',
    'julia',
    'julia_compiler_available',
    'is_julia_available',

    'erlang',
    'erlang_compiler_available',
    'is_erlang_available',

    'elixir',
    'elixir_compiler_available',
    'is_elixir_available',

    'ruby',
    'typescript',
    'vbnet',
    'vb',
    'vbnet_api',
    'perl',
    'pl',
    'lua',
    'zig',
    'kotlin',
    'kt',
    'swift',
    'php',
    'dart',
    'powershell',
    'ps',
    'vbscript',
    'vbs',
    'shell',
    'sh',
    'bash',
]

# 延迟导入子模块，避免导入失败影响整体
_c_loaded = False
_nim_loaded = False
_rust_loaded = False
_cpp_loaded = False
_csharp_loaded = False
_mojo_loaded = False
_freebasic_loaded = False
_scala_loaded = False
_java_loaded = False
_cangjie_loaded = False
_go_loaded = False
_r_loaded = False
_julia_loaded = False
_erlang_loaded = False
_elixir_loaded = False
_ruby_loaded = False
_typescript_loaded = False
_vbnet_loaded = False
_perl_loaded = False
_lua_loaded = False
_zig_loaded = False
_kotlin_loaded = False
_swift_loaded = False
_php_loaded = False
_dart_loaded = False
_powershell_loaded = False
_vbscript_loaded = False
_shell_loaded = False


def _load_c():
    """延迟加载 C 模块"""
    global _c_loaded
    if not _c_loaded:
        try:
            from . import c
            globals()['c'] = c
            globals()['load_dll'] = c.load_dll
            globals()['call_func'] = c.call_func
            globals()['c_dll'] = c.c_dll
            globals()['CDLLWrapper'] = c.CDLLWrapper
            _c_loaded = True
        except Exception:
            _c_loaded = False
    return _c_loaded


def _load_nim():
    """延迟加载 Nim 模块"""
    global _nim_loaded
    if not _nim_loaded:
        try:
            from . import nim
            globals()['nim'] = nim.nim
            globals()['compile_and_run'] = nim.compile_and_run
            globals()['nim_compiler_available'] = nim.nim_compiler_available
            globals()['is_nim_available'] = nim.is_nim_available
            _nim_loaded = True
        except Exception:
            _nim_loaded = False
    return _nim_loaded


def _load_rust():
    """延迟加载 Rust 模块"""
    global _rust_loaded
    if not _rust_loaded:
        try:
            from . import rust
            globals()['rust'] = rust
            _rust_loaded = True
        except Exception:
            _rust_loaded = False
    return _rust_loaded


def _load_cpp():
    """延迟加载 C++ 模块"""
    global _cpp_loaded
    if not _cpp_loaded:
        try:
            from . import cpp
            globals()['cpp'] = cpp.cpp
            globals()['cpp_compiler_available'] = cpp.cpp_compiler_available
            globals()['get_cpp_compiler_info'] = cpp.get_cpp_compiler_info
            globals()['compile_and_run_cpp'] = cpp.compile_and_run
            globals()['load_cpp_dll'] = cpp.load_cpp_dll
            globals()['call_cpp_func'] = cpp.call_cpp_func
            _cpp_loaded = True
        except Exception:
            _cpp_loaded = False
    return _cpp_loaded


def _load_csharp():
    """延迟加载 C# 模块"""
    global _csharp_loaded
    if not _csharp_loaded:
        try:
            from . import csharp
            globals()['csharp'] = csharp
            _csharp_loaded = True
        except Exception:
            _csharp_loaded = False
    return _csharp_loaded


def _load_mojo():
    """延迟加载 Mojo 模块"""
    global _mojo_loaded
    if not _mojo_loaded:
        try:
            from . import mojo
            globals()['mojo'] = mojo
            _mojo_loaded = True
        except Exception:
            _mojo_loaded = False
    return _mojo_loaded


def _load_freebasic():
    """延迟加载 FreeBASIC 模块"""
    global _freebasic_loaded
    if not _freebasic_loaded:
        try:
            from . import freebasic
            globals()['freebasic'] = freebasic
            _freebasic_loaded = True
        except Exception:
            _freebasic_loaded = False
    return _freebasic_loaded


def _load_scala():
    """延迟加载 Scala 模块"""
    global _scala_loaded
    if not _scala_loaded:
        try:
            from . import scala
            globals()['scala'] = scala
            _scala_loaded = True
        except Exception:
            _scala_loaded = False
    return _scala_loaded


def _load_java():
    """延迟加载 Java 模块"""
    global _java_loaded
    if not _java_loaded:
        try:
            from . import java
            globals()['java'] = java
            _java_loaded = True
        except Exception:
            _java_loaded = False
    return _java_loaded


def _load_cangjie():
    """延迟加载仓颉模块"""
    global _cangjie_loaded
    if not _cangjie_loaded:
        try:
            from . import cangjie
            globals()['cangjie'] = cangjie.cangjie
            globals()['cjc_compiler_available'] = cangjie.cjc_compiler_available
            _cangjie_loaded = True
        except Exception:
            _cangjie_loaded = False
    return _cangjie_loaded


def _load_go():
    """延迟加载 Go 模块"""
    global _go_loaded
    if not _go_loaded:
        try:
            from . import go
            globals()['go'] = go
            globals()['go_compiler_available'] = go.go_compiler_available
            globals()['is_go_available'] = go.is_go_available
            _go_loaded = True
        except Exception:
            _go_loaded = False
    return _go_loaded


def _load_r():
    """延迟加载 R 模块"""
    global _r_loaded
    if not _r_loaded:
        try:
            from . import r
            globals()['r'] = r.r
            globals()['r_compiler_available'] = r.r_compiler_available
            _r_loaded = True
        except Exception:
            _r_loaded = False
    return _r_loaded


def _load_julia():
    """延迟加载 Julia 模块"""
    global _julia_loaded
    if not _julia_loaded:
        try:
            from . import julia
            globals()['julia'] = julia
            globals()['julia_compiler_available'] = julia.julia_compiler_available
            globals()['is_julia_available'] = julia.is_julia_available
            _julia_loaded = True
        except Exception:
            _julia_loaded = False
    return _julia_loaded


def _load_erlang():
    """延迟加载 Erlang 模块"""
    global _erlang_loaded
    if _erlang_loaded:
        return True
    try:
        import importlib
        erlang_mod = importlib.import_module('.erlang', __package__)
        globals()['erlang'] = erlang_mod.erlang
        globals()['erlang_compiler_available'] = erlang_mod.erlang_compiler_available
        globals()['is_erlang_available'] = erlang_mod.is_erlang_available
        _erlang_loaded = True
        return True
    except Exception:
        _erlang_loaded = False
        return False


def _load_elixir():
    """延迟加载 Elixir 模块"""
    global _elixir_loaded
    if _elixir_loaded:
        return True
    try:
        import importlib
        elixir_mod = importlib.import_module('.elixir', __package__)
        globals()['elixir'] = elixir_mod.elixir
        globals()['elixir_compiler_available'] = elixir_mod.elixir_compiler_available
        globals()['is_elixir_available'] = elixir_mod.is_elixir_available
        _elixir_loaded = True
        return True
    except Exception:
        _elixir_loaded = False
        return False


def _load_ruby():
    """延迟加载 Ruby 模块"""
    global _ruby_loaded
    if not _ruby_loaded:
        try:
            from . import ruby
            globals()['ruby'] = ruby.ruby
            globals()['ruby_compiler_available'] = ruby.ruby_compiler_available
            globals()['is_ruby_available'] = ruby.is_ruby_available
            _ruby_loaded = True
        except Exception:
            _ruby_loaded = False
    return _ruby_loaded


def _load_typescript():
    """延迟加载 TypeScript 模块"""
    global _typescript_loaded
    if not _typescript_loaded:
        try:
            from . import typescript
            globals()['typescript'] = typescript.typescript
            globals()['ts'] = typescript.ts
            globals()['ts_compiler_available'] = typescript.ts_compiler_available
            globals()['is_typescript_available'] = typescript.is_typescript_available
            globals()['is_node_available'] = typescript.is_node_available
            _typescript_loaded = True
        except Exception:
            _typescript_loaded = False
    return _typescript_loaded


def _load_vbnet():
    """延迟加载 VB.NET 模块"""
    global _vbnet_loaded
    if not _vbnet_loaded:
        try:
            from . import vbnet
            globals()['vbnet'] = vbnet.vbnet
            globals()['vb'] = vbnet.vb
            globals()['vbnet_compiler_available'] = vbnet.vbnet_compiler_available
            try:
                globals()['vbnet_api'] = vbnet.api
            except AttributeError:
                pass
            _vbnet_loaded = True
        except Exception:
            _vbnet_loaded = False
    return _vbnet_loaded


def _load_perl():
    """延迟加载 Perl 模块"""
    global _perl_loaded
    if not _perl_loaded:
        try:
            from . import perl
            globals()['perl'] = perl.perl
            globals()['pl'] = perl.pl
            globals()['perl_compiler_available'] = perl.perl_compiler_available
            _perl_loaded = True
        except Exception:
            _perl_loaded = False
    return _perl_loaded


def _load_lua():
    """延迟加载 Lua 模块"""
    global _lua_loaded
    if not _lua_loaded:
        try:
            from . import lua
            globals()['lua'] = lua.lua
            globals()['luae'] = lua.luae
            globals()['lua_compiler_available'] = lua.lua_compiler_available
            _lua_loaded = True
        except Exception:
            _lua_loaded = False
    return _lua_loaded


def _load_zig():
    """延迟加载 Zig 模块"""
    global _zig_loaded
    if not _zig_loaded:
        try:
            from . import zig
            globals()['zig'] = zig.zig
            globals()['zigc'] = zig.zigc
            globals()['zig_compiler_available'] = zig.zig_compiler_available
            _zig_loaded = True
        except Exception:
            _zig_loaded = False
    return _zig_loaded


def _load_kotlin():
    """延迟加载 Kotlin 模块"""
    global _kotlin_loaded
    if not _kotlin_loaded:
        try:
            from . import kotlin
            globals()['kotlin'] = kotlin.kotlin
            globals()['kt'] = kotlin.kt
            globals()['kotlin_compiler_available'] = kotlin.kotlin_compiler_available
            _kotlin_loaded = True
        except Exception:
            _kotlin_loaded = False
    return _kotlin_loaded


def _load_swift():
    """延迟加载 Swift 模块"""
    global _swift_loaded
    if not _swift_loaded:
        try:
            from . import swift
            globals()['swift'] = swift.swift
            globals()['swiftc'] = swift.swiftc
            globals()['swift_compiler_available'] = swift.swift_compiler_available
            _swift_loaded = True
        except Exception:
            _swift_loaded = False
    return _swift_loaded


def _load_php():
    """延迟加载 PHP 模块"""
    global _php_loaded
    if not _php_loaded:
        try:
            from . import php
            globals()['php'] = php.php
            globals()['phpe'] = php.phpe
            globals()['php_compiler_available'] = php.php_compiler_available
            _php_loaded = True
        except Exception:
            _php_loaded = False
    return _php_loaded


def _load_dart():
    """延迟加载 Dart 模块"""
    global _dart_loaded
    if not _dart_loaded:
        try:
            from . import dart
            globals()['dart'] = dart.dart
            globals()['dartexe'] = dart.dartexe
            globals()['dart_compiler_available'] = dart.dart_compiler_available
            _dart_loaded = True
        except Exception:
            _dart_loaded = False
    return _dart_loaded


def _load_powershell():
    """延迟加载 PowerShell 模块"""
    global _powershell_loaded
    if not _powershell_loaded:
        try:
            from . import powershell
            globals()['powershell'] = powershell.powershell
            globals()['ps'] = powershell.ps
            globals()['powershell_compiler_available'] = powershell.powershell_compiler_available
            _powershell_loaded = True
        except Exception:
            _powershell_loaded = False
    return _powershell_loaded


def _load_vbscript():
    """延迟加载 VBScript 模块"""
    global _vbscript_loaded
    if not _vbscript_loaded:
        try:
            from . import vbscript
            globals()['vbscript'] = vbscript.vbscript
            globals()['vbs'] = vbscript.vbs
            globals()['vbscript_compiler_available'] = vbscript.vbscript_compiler_available
            _vbscript_loaded = True
        except Exception:
            _vbscript_loaded = False
    return _vbscript_loaded


def _load_shell():
    """延迟加载 Shell 模块"""
    global _shell_loaded
    if not _shell_loaded:
        try:
            from . import shell
            globals()['shell'] = shell.shell
            globals()['sh'] = shell.sh
            globals()['bash'] = shell.bash
            globals()['shell_compiler_available'] = shell.shell_compiler_available
            globals()['bash_compiler_available'] = shell.bash_compiler_available
            _shell_loaded = True
        except Exception:
            _shell_loaded = False
    return _shell_loaded


def __getattr__(name):
    """延迟加载属性"""
    if name in ('c', 'load_dll', 'call_func', 'c_dll', 'CDLLWrapper'):
        if _load_c():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('nim', 'compile_and_run', 'nim_compiler_available', 'is_nim_available'):
        if _load_nim():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name == 'rust':
        if _load_rust():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('cpp', 'cpp_compiler_available', 'get_cpp_compiler_info', 
                'compile_and_run_cpp', 'load_cpp_dll', 'call_cpp_func'):
        if _load_cpp():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name == 'csharp':
        if _load_csharp():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name == 'mojo':
        if _load_mojo():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name == 'freebasic':
        if _load_freebasic():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name == 'scala':
        if _load_scala():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name == 'java':
        if _load_java():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('cangjie', 'cjc_compiler_available'):
        if _load_cangjie():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('go', 'go_compiler_available', 'is_go_available'):
        if _load_go():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('r', 'r_compiler_available'):
        if _load_r():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('julia', 'julia_compiler_available', 'is_julia_available'):
        if _load_julia():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('erlang', 'erlang_compiler_available', 'is_erlang_available'):
        if _load_erlang():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('elixir', 'elixir_compiler_available', 'is_elixir_available'):
        if _load_elixir():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('ruby', 'ruby_compiler_available', 'is_ruby_available'):
        if _load_ruby():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('typescript', 'ts', 'ts_compiler_available', 'is_typescript_available', 'is_node_available'):
        if _load_typescript():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('vbnet', 'vb', 'vbnet_compiler_available', 'vbnet_api'):
        if _load_vbnet():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('perl', 'pl', 'perl_compiler_available'):
        if _load_perl():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('lua', 'luae', 'lua_compiler_available'):
        if _load_lua():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('zig', 'zigc', 'zig_compiler_available'):
        if _load_zig():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('kotlin', 'kt', 'kotlin_compiler_available'):
        if _load_kotlin():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('swift', 'swiftc', 'swift_compiler_available'):
        if _load_swift():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('php', 'phpe', 'php_compiler_available'):
        if _load_php():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('dart', 'dartexe', 'dart_compiler_available'):
        if _load_dart():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('powershell', 'ps', 'powershell_compiler_available'):
        if _load_powershell():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('vbscript', 'vbs', 'vbscript_compiler_available'):
        if _load_vbscript():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    if name in ('shell', 'sh', 'bash', 'shell_compiler_available', 'bash_compiler_available'):
        if _load_shell():
            return globals().get(name)
        raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)

    # manager 新功能
    manager_funcs = (
        'set_compiler_path', 'add_compiler_path',
        'set_runtime_path', 'add_runtime_path',
        'get_all_paths', 'save_config', 'load_config',
        'get_config_file_path'
    )
    if name in manager_funcs:
        return getattr(globals()['manager'], name)

    raise AttributeError("module 'vools.bridge' has no attribute '%s'" % name)


def __dir__():
    """返回所有可用的导出名称"""
    return sorted(set(globals().keys()) | set(__all__))
