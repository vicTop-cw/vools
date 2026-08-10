"""
vools.bridge.core.loader - 统一共享库加载器

提供跨平台的共享库加载能力，支持 Windows (.dll) 和 Linux (.so)。

注意：编译器和运行时环境配置已移至 bridge.manager 模块。
"""

import os
import sys
import ctypes
import platform
import threading

# 延迟导入 manager，避免循环依赖
_manager = None

def _get_manager():
    """获取 manager 实例（延迟加载）"""
    global _manager
    if _manager is None:
        from .. import manager as _m
        _manager = _m.manager
    return _manager

_PLATFORM = platform.system()
_IS_WINDOWS = _PLATFORM == 'Windows'
_IS_LINUX = _PLATFORM == 'Linux'

_LOADED_LIBS = {}
_LOAD_LOCK = threading.Lock()

_lib_base = os.path.join(os.path.dirname(__file__), '..', '..', 'lib')
if _IS_WINDOWS:
    _LIB_DIR = os.path.join(_lib_base, 'windows')
elif _IS_LINUX:
    _LIB_DIR = os.path.join(_lib_base, 'linux')
else:
    _LIB_DIR = _lib_base
_LIB_DIR = os.path.abspath(_LIB_DIR)

# 初始化时设置所有语言的运行时环境
def _setup_all_runtimes():
    """设置所有已注册语言的运行时环境"""
    try:
        mgr = _get_manager()
        if mgr:
            mgr.setup_all_runtimes()
    except Exception:
        pass

# 尝试初始化（可能在 manager 未加载时失败，不影响功能）
try:
    _setup_all_runtimes()
except Exception:
    pass


class SharedLibrary:
    """
    通用共享库封装类

    封装 ctypes.CDLL，提供更便捷的函数调用方式，
    支持自动类型推断和参数转换。

    属性：
        path: 共享库文件路径
        _lib: 底层 ctypes.CDLL 实例
        _func_cache: 函数缓存字典
    """

    def __init__(self, path, setup_func=None):
        """
        初始化 SharedLibrary

        参数：
            path: 共享库文件路径
            setup_func: 可选的设置函数，用于初始化库函数签名

        异常：
            OSError: 库加载失败时抛出
        """
        self.path = os.path.abspath(path)
        self._lib = ctypes.CDLL(self.path)
        self._func_cache = {}
        if setup_func:
            setup_func(self._lib)

    def get_function(self, name, argtypes=None, restype=None):
        """
        获取库中的函数

        参数：
            name: 函数名称
            argtypes: 参数类型列表（可选）
            restype: 返回值类型（可选）

        返回：
            ctypes 函数对象

        异常：
            AttributeError: 函数不存在时抛出
        """
        if name in self._func_cache:
            return self._func_cache[name]

        func = getattr(self._lib, name)
        if argtypes is not None:
            func.argtypes = argtypes
        if restype is not None:
            func.restype = restype
        self._func_cache[name] = func
        return func

    def call(self, name, *args, **kwargs):
        """
        调用库中的函数

        参数：
            name: 函数名称
            *args: 位置参数
            **kwargs: 关键字参数
                argtypes: 参数类型列表
                restype: 返回值类型

        返回：
            函数返回值
        """
        argtypes = kwargs.pop('argtypes', None)
        restype = kwargs.pop('restype', None)
        func = self.get_function(name, argtypes=argtypes, restype=restype)
        return func(*args, **kwargs)

    def __getattr__(self, name):
        """
        便捷属性访问，直接通过属性名获取函数

        参数：
            name: 函数名称

        返回：
            ctypes 函数对象
        """
        if name.startswith('_'):
            raise AttributeError(name)
        try:
            return self.get_function(name)
        except AttributeError:
            raise AttributeError(
                "'SharedLibrary' object has no attribute '%s'" % name
            )

    def __repr__(self):
        """返回对象的字符串表示"""
        return "SharedLibrary('%s')" % self.path


def load_from_path(path, setup_func=None):
    """
    从指定路径加载共享库

    参数：
        path: 共享库文件路径
        setup_func: 可选的设置函数

    返回：
        SharedLibrary 实例，加载失败返回 None
    """
    try:
        return SharedLibrary(path, setup_func=setup_func)
    except Exception:
        return None


class LibraryLoader:
    """统一共享库加载器"""

    def __init__(self, language):
        self.language = language
        self._loaded_libs = {}

    def _find_lib(self, name):
        """查找共享库路径"""
        if name is None:
            return None
        if _IS_WINDOWS:
            for ext in ('.dll', '.so', '.pyd'):
                path = os.path.join(_LIB_DIR, name + ext)
                if os.path.exists(path):
                    return path
        elif _IS_LINUX:
            path = os.path.join(_LIB_DIR, 'lib' + name + '.so')
            if os.path.exists(path):
                return path
            path2 = os.path.join(_LIB_DIR, name + '.so')
            if os.path.exists(path2):
                return path2
        return None

    def load(self, name, setup_func=None):
        """加载共享库"""
        if name in self._loaded_libs:
            return self._loaded_libs[name]

        with _LOAD_LOCK:
            if name in self._loaded_libs:
                return self._loaded_libs[name]

            path = self._find_lib(name)
            if path is None:
                self._loaded_libs[name] = None
                return None

            try:
                lib = ctypes.CDLL(path)
                if setup_func:
                    setup_func(lib)
                self._loaded_libs[name] = lib
                return lib
            except Exception:
                self._loaded_libs[name] = None
                return None

    def is_available(self, name):
        """检查库是否可用"""
        return self.load(name) is not None


_global_loaders = {}


def get_loader(language):
    """获取指定语言的加载器"""
    if language not in _global_loaders:
        _global_loaders[language] = LibraryLoader(language)
    return _global_loaders[language]


def load_library(language, name, setup_func=None):
    """加载指定语言的共享库"""
    return get_loader(language).load(name, setup_func)


def is_available(language):
    """检查指定语言是否有可用的桥接库"""
    loader = get_loader(language)
    if language == 'nim':
        return loader.is_available('vools_crypto')
    elif language == 'scala':
        from ..scala.loader import is_scala_available
        return is_scala_available()
    elif language == 'java':
        from ..java.loader import is_java_available
        return is_java_available()
    return False


# 向后兼容 API - 旧的 _nim_loader.py 使用这些函数
def load_nim_lib(name, setup_func=None):
    """加载 Nim 共享库（向后兼容）"""
    return load_library('nim', name, setup_func)


def is_nim_available():
    """检查 Nim 是否可用（向后兼容）"""
    return is_available('nim')
