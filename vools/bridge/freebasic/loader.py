"""
vools.bridge.freebasic.loader - 预编译 FreeBASIC 库加载器

处理 FreeBASIC 共享库的加载与函数签名初始化，复用 vools.bridge.core.loader。
支持加载第三方 DLL 库（database/graphics/multimedia/gui 等类别）。
"""

import os
import json
import ctypes
import platform
import threading
from ..core.loader import load_library

_FBC_LIBS = {}

_FB_LOAD_LOCK = threading.Lock()
_MANIFEST_CACHE = {}
_MANIFEST_LOCK = threading.Lock()

_LIBS_BASE_DIR = os.path.join(os.path.dirname(__file__), 'libs')


def _get_platform_dir(platform_name=None):
    """
    获取平台目录名

    参数：
        platform_name: 可选，平台名（win64/win32），默认自动检测

    返回：
        平台目录名字符串
    """
    if platform_name:
        return platform_name
    arch = platform.architecture()[0]
    if arch == '64bit':
        return 'win64'
    else:
        return 'win32'


def _load_manifest(platform_name=None):
    """
    读取并缓存 manifest.json

    参数：
        platform_name: 可选，平台名（win64/win32），默认自动检测

    返回：
        manifest 字典，加载失败返回 None
    """
    plat_dir = _get_platform_dir(platform_name)
    if plat_dir in _MANIFEST_CACHE:
        return _MANIFEST_CACHE[plat_dir]

    with _MANIFEST_LOCK:
        if plat_dir in _MANIFEST_CACHE:
            return _MANIFEST_CACHE[plat_dir]

        manifest_path = os.path.join(_LIBS_BASE_DIR, plat_dir, 'manifest.json')
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            _MANIFEST_CACHE[plat_dir] = manifest
            return manifest
        except Exception:
            _MANIFEST_CACHE[plat_dir] = None
            return None


def _find_dll_path(name, category=None, platform_name=None):
    """
    查找 DLL 文件路径

    搜索顺序：
        1. libs/<platform>/<category>/<name>.dll （如果指定了 category）
        2. libs/<platform>/<name>.dll
        3. 根据 manifest 中的 dll 路径查找

    参数：
        name: 库名
        category: 可选，类别
        platform_name: 可选，平台名

    返回：
        DLL 绝对路径，找不到返回 None
    """
    plat_dir = _get_platform_dir(platform_name)
    plat_base = os.path.join(_LIBS_BASE_DIR, plat_dir)

    if category:
        cat_path = os.path.join(plat_base, category, name + '.dll')
        if os.path.exists(cat_path):
            return os.path.abspath(cat_path)

    root_path = os.path.join(plat_base, name + '.dll')
    if os.path.exists(root_path):
        return os.path.abspath(root_path)

    manifest = _load_manifest(platform_name)
    if manifest and 'libraries' in manifest:
        lib_info = manifest['libraries'].get(name)
        if lib_info and 'dll' in lib_info:
            dll_rel_path = lib_info['dll']
            dll_path = os.path.join(plat_base, dll_rel_path)
            if os.path.exists(dll_path):
                return os.path.abspath(dll_path)

    return None


def _get_lib_info(name, platform_name=None):
    """
    从 manifest 获取库信息

    参数：
        name: 库名
        platform_name: 可选，平台名

    返回：
        库信息字典，不存在返回 None
    """
    manifest = _load_manifest(platform_name)
    if manifest and 'libraries' in manifest:
        return manifest['libraries'].get(name)
    return None


class FbLibraryLoader:
    """
    FreeBASIC 第三方 DLL 库加载器

    封装 DLL 查找、加载、依赖处理逻辑，支持单例模式和线程安全。
    """

    def __init__(self, platform_name=None):
        """
        初始化加载器

        参数：
            platform_name: 可选，平台名（win64/win32）
        """
        self.platform = _get_platform_dir(platform_name)
        self._loaded_libs = {}

    def _load_dependencies(self, name, loading_stack=None):
        """
        递归加载依赖库

        参数：
            name: 库名
            loading_stack: 正在加载中的库集合（用于检测循环依赖）

        返回：
            加载成功返回 True，失败返回 False
        """
        if loading_stack is None:
            loading_stack = set()

        if name in loading_stack:
            return True

        lib_info = _get_lib_info(name, self.platform)
        if not lib_info:
            return False

        dependencies = lib_info.get('dependencies', [])
        for dep_name in dependencies:
            if dep_name in self._loaded_libs:
                if self._loaded_libs[dep_name] is None:
                    return False
                continue

            if dep_name in loading_stack:
                continue

            loading_stack.add(dep_name)
            dep_lib = self._load_single(dep_name, loading_stack)
            loading_stack.discard(dep_name)

            if dep_lib is None:
                return False

        return True

    def _load_single(self, name, loading_stack=None):
        """
        加载单个 DLL 库（内部方法，无锁）

        参数：
            name: 库名
            loading_stack: 正在加载中的库集合

        返回：
            CDLL 实例，失败返回 None
        """
        if name in self._loaded_libs:
            return self._loaded_libs[name]

        if loading_stack is None:
            loading_stack = set()

        if name in loading_stack:
            return None

        loading_stack.add(name)

        if not self._load_dependencies(name, loading_stack):
            loading_stack.discard(name)
            self._loaded_libs[name] = None
            return None

        lib_info = _get_lib_info(name, self.platform)
        category = None
        if lib_info:
            category = lib_info.get('category')

        dll_path = _find_dll_path(name, category, self.platform)
        if dll_path is None:
            loading_stack.discard(name)
            self._loaded_libs[name] = None
            return None

        try:
            lib = ctypes.CDLL(dll_path)
            self._loaded_libs[name] = lib
            loading_stack.discard(name)
            return lib
        except Exception:
            loading_stack.discard(name)
            self._loaded_libs[name] = None
            return None

    def load(self, name, category=None):
        """
        加载 DLL 库（线程安全，带缓存）

        参数：
            name: 库名（如 'sqlite3', 'cairo', 'SDL3'）
            category: 可选，类别（database/graphics/multimedia/gui/web/utils）

        返回：
            ctypes.CDLL 实例，失败返回 None
        """
        if name in self._loaded_libs:
            return self._loaded_libs[name]

        with _FB_LOAD_LOCK:
            if name in self._loaded_libs:
                return self._loaded_libs[name]

            loading_stack = set()
            result = self._load_single(name, loading_stack)
            return result

    def is_available(self, name):
        """
        检查库是否可用

        参数：
            name: 库名

        返回：
            可用返回 True，否则返回 False
        """
        return self.load(name) is not None

    def list_libs(self, category=None):
        """
        列出所有可用的 DLL 库

        参数：
            category: 可选，按类别过滤

        返回：
            库名列表
        """
        manifest = _load_manifest(self.platform)
        if not manifest or 'libraries' not in manifest:
            return []

        libs = manifest['libraries']
        if category is None:
            return list(libs.keys())

        result = []
        for name, info in libs.items():
            if info.get('category') == category:
                result.append(name)
        return result


_global_fb_loader = None
_global_fb_loader_lock = threading.Lock()


def _get_global_fb_loader():
    """
    获取全局 FbLibraryLoader 实例（单例）

    返回：
        FbLibraryLoader 实例
    """
    global _global_fb_loader
    if _global_fb_loader is not None:
        return _global_fb_loader

    with _global_fb_loader_lock:
        if _global_fb_loader is None:
            _global_fb_loader = FbLibraryLoader()
        return _global_fb_loader


def get_fb_lib(name, category=None, platform=None):
    """
    获取 FreeBASIC 第三方 DLL 库

    从 libs/ 目录加载第三方 DLL，支持自动加载依赖，单例模式。

    参数：
        name: 库名（如 'sqlite3', 'cairo', 'SDL3'）
        category: 可选，类别（database/graphics/multimedia/gui/web/utils）
        platform: 可选，平台（win64/win32），默认根据当前系统判断

    返回：
        ctypes.CDLL 实例，失败返回 None
    """
    if platform is not None and platform != _get_platform_dir():
        loader = FbLibraryLoader(platform)
        return loader.load(name, category)

    loader = _get_global_fb_loader()
    return loader.load(name, category)


def list_fb_libs(category=None):
    """
    列出所有可用的第三方 DLL 库

    参数：
        category: 可选，按类别过滤（database/graphics/multimedia/gui/web/utils）

    返回：
        库名列表
    """
    loader = _get_global_fb_loader()
    return loader.list_libs(category)


def get_fbc_lib(name, setup_func=None):
    """
    获取 FreeBASIC 预编译共享库

    参数：
        name: 库名（如 'vools_fbc_demo'）
        setup_func: 可选的初始化函数（设置 argtypes/restype）

    返回：
        加载成功返回 CDLL 实例，失败返回 None
    """
    if name in _FBC_LIBS:
        return _FBC_LIBS[name]
    lib = load_library('fbc', name, setup_func)
    _FBC_LIBS[name] = lib
    return lib


def is_fbc_available():
    """
    检查 FreeBASIC 预编译库是否可用

    约定探测库名 `vools_fbc_demo`；若 vools/lib/ 下不存在则返回 False，
    调用方应回退到 Python 实现。
    """
    return get_fbc_lib('vools_fbc_demo') is not None
