"""
vools.bridge.cangjie.loader - 仓颉 DLL 加载器

提供仓颉编译的动态库加载和函数调用能力。

设计目标:
- 加载仓颉编译的 DLL/SO 文件
- 设置函数签名(argtypes, restype)
- 参数转换(str → bytes 等)
"""

import os
import ctypes
import platform
import subprocess

_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'


def _find_cangjie_sdk_path():
    """自动检测仓颉 SDK 安装路径"""
    # 1. 检查环境变量
    sdk_path = os.environ.get('CANGJIE_SDK_PATH')
    if sdk_path and os.path.exists(sdk_path):
        return sdk_path

    # 2. 从 cjc 编译器路径推导
    try:
        if _IS_WINDOWS:
            result = subprocess.run(['where', 'cjc'], capture_output=True, text=True, timeout=5)
        else:
            result = subprocess.run(['which', 'cjc'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            cjc_path = result.stdout.strip().split('\n')[0]
            # cjc 通常在 <sdk>/cangjie/bin/cjc.exe
            # 运行时 DLL 在 <sdk>/cangjie/runtime/lib/windows_x86_64_llvm/
            bin_dir = os.path.dirname(cjc_path)
            cangjie_dir = os.path.dirname(bin_dir)  # <sdk>/cangjie/
            if os.path.exists(cangjie_dir):
                return cangjie_dir
    except Exception:
        pass

    return None


# 仓颉 SDK 路径
_CJ_SDK_PATH = _find_cangjie_sdk_path()

# 仓颉运行时路径
_CJ_RUNTIME_PATHS = []
if _IS_WINDOWS:
    cj_sdk_paths = [
        os.environ.get('CANGJIE_SDK_PATH'),
        _CJ_SDK_PATH,
        os.path.join(os.path.dirname(__file__), 'runtime', 'lib', 'windows_x86_64_llvm'),
        os.path.join(os.path.dirname(__file__), 'runtime', 'lib'),
        os.path.join(os.path.dirname(__file__), 'runtime', 'bin'),
    ]
    # 如果找到了 SDK 路径，添加运行时子目录
    if _CJ_SDK_PATH:
        cj_sdk_paths.insert(0, os.path.join(_CJ_SDK_PATH, 'runtime', 'lib', 'windows_x86_64_llvm'))
        cj_sdk_paths.insert(0, os.path.join(_CJ_SDK_PATH, 'runtime', 'lib'))

    for p in cj_sdk_paths:
        if p and os.path.exists(p):
            if p not in _CJ_RUNTIME_PATHS:
                _CJ_RUNTIME_PATHS.append(p)

# 设置 DLL 搜索路径
if _IS_WINDOWS:
    add_dll_dir = getattr(os, 'add_dll_directory', None)
    if add_dll_dir:
        for p in _CJ_RUNTIME_PATHS:
            if os.path.exists(p):
                try:
                    add_dll_dir(p)
                except OSError:
                    pass

    # 添加到 PATH 环境变量
    cur_path = os.environ.get('PATH', '')
    for p in _CJ_RUNTIME_PATHS:
        if p not in cur_path:
            os.environ['PATH'] = p + os.pathsep + cur_path

# 设置 CANGJIE_SDK_PATH 环境变量
if _CJ_SDK_PATH and 'CANGJIE_SDK_PATH' not in os.environ:
    os.environ['CANGJIE_SDK_PATH'] = _CJ_SDK_PATH

# 已加载的库缓存
_LOADED_LIBS = {}

# 仓颉运行时初始化标志
_RUNTIME_INITIALIZED = False


def _init_cangjie_runtime():
    """初始化仓颉运行时"""
    global _RUNTIME_INITIALIZED
    if _RUNTIME_INITIALIZED:
        return True

    # 尝试加载运行时库并初始化
    for runtime_path in _CJ_RUNTIME_PATHS:
        runtime_dll = os.path.join(runtime_path, 'libcangjie-runtime.dll')
        if os.path.exists(runtime_dll):
            try:
                runtime_lib = ctypes.CDLL(runtime_dll)
                _RUNTIME_INITIALIZED = True
                return True
            except Exception:
                continue

    return False


def load_cj_dll(dll_path):
    """
    加载仓颉编译的 DLL/SO 文件

    参数:
        dll_path: DLL/SO 文件路径

    返回:
        ctypes.CDLL 对象

    异常:
        OSError: 加载失败时抛出
    """
    # 初始化运行时
    _init_cangjie_runtime()

    if dll_path in _LOADED_LIBS:
        return _LOADED_LIBS[dll_path]

    if not os.path.exists(dll_path):
        raise FileNotFoundError(f'仓颉共享库不存在: {dll_path}')

    # 复制运行时 DLL 到 DLL 所在目录(确保依赖可用)
    dll_dir = os.path.dirname(dll_path)
    for runtime_path in _CJ_RUNTIME_PATHS:
        runtime_dlls = [
            'libcangjie-runtime.dll',
            'libcangjie-std-core.dll',
            'libcangjie-std-runtime.dll',
        ]
        for runtime_dll in runtime_dlls:
            src_path = os.path.join(runtime_path, runtime_dll)
            dst_path = os.path.join(dll_dir, runtime_dll)
            if os.path.exists(src_path) and not os.path.exists(dst_path):
                try:
                    import shutil
                    shutil.copy2(src_path, dst_path)
                except Exception:
                    pass

    try:
        lib = ctypes.CDLL(dll_path)
        _LOADED_LIBS[dll_path] = lib
        return lib
    except Exception as e:
        raise OSError(f'加载仓颉共享库失败: {dll_path}, 错误: {e}')


def get_cj_lib(dll_path):
    """
    获取仓颉库(别名函数,兼容命名)

    参数:
        dll_path: DLL/SO 文件路径

    返回:
        ctypes.CDLL 对象
    """
    return load_cj_dll(dll_path)


def is_cj_available(dll_path):
    """
    检查仓颉 DLL 是否可用

    参数:
        dll_path: DLL/SO 文件路径

    返回:
        bool: DLL 存在且可加载返回 True
    """
    try:
        load_cj_dll(dll_path)
        return True
    except Exception:
        return False


def setup_cj_func(lib, func_name, argtypes, restype):
    """
    设置仓颉函数签名

    参数:
        lib: ctypes.CDLL 对象
        func_name: 函数名
        argtypes: 参数类型列表(ctypes 类型)
        restype: 返回类型(ctypes 类型)

    返回:
        设置好签名的函数对象

    异常:
        AttributeError: 函数不存在时抛出
    """
    try:
        func = getattr(lib, func_name)
    except AttributeError:
        raise AttributeError(f'仓颉库中未找到函数: {func_name}')

    # 设置参数类型
    if argtypes:
        valid_argtypes = [t for t in argtypes if t is not None]
        if valid_argtypes and len(valid_argtypes) == len(argtypes):
            func.argtypes = argtypes

    # 设置返回类型
    if restype is not None:
        func.restype = restype

    return func


def convert_args(args, argtypes):
    """
    转换参数以匹配 ctypes 类型要求

    目前支持的转换:
        - str -> bytes (utf-8 编码),当对应类型为 c_char_p 时

    参数:
        args: 原始参数值列表
        argtypes: ctypes 参数类型列表

    返回:
        转换后的参数列表
    """
    result = []
    for arg, c_type in zip(args, argtypes):
        if c_type is ctypes.c_char_p:
            if isinstance(arg, str):
                result.append(arg.encode('utf-8'))
            else:
                result.append(arg)
        else:
            result.append(arg)
    return result


def call_cj_func(dll_path, func_name, args, argtypes=None, restype=None):
    """
    调用仓颉 DLL 中的函数

    参数:
        dll_path: DLL/SO 文件路径
        func_name: 函数名
        args: 参数列表
        argtypes: 参数类型列表(可选)
        restype: 返回类型(可选)

    返回:
        函数返回值
    """
    lib = load_cj_dll(dll_path)
    func = setup_cj_func(lib, func_name, argtypes, restype)

    # 转换参数
    if argtypes:
        converted_args = convert_args(args, argtypes)
    else:
        converted_args = args

    return func(*converted_args)


def convert_result(result, return_type):
    """
    转换返回值以匹配 Python 类型期望

    目前支持的转换:
        - bytes -> str (utf-8 解码),当返回类型注解为 str 时

    参数:
        result: 原始返回值
        return_type: Python 返回类型注解

    返回:
        转换后的返回值
    """
    if return_type is str and isinstance(result, bytes):
        return result.decode('utf-8')
    return result