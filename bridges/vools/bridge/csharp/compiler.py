"""
vools.bridge.csharp.compiler - C# 动态编译器

提供 @csharp 装饰器，支持：
- 自动生成 C# 代码和项目文件
- 调用 dotnet publish (NativeAOT) 编译原生 DLL
- 基于 MD5 的代码缓存
- ctypes 调用导出函数
- 异步执行支持

使用 manager 统一管理编译器配置。
"""


__all__ = [
    "csharp_compiler_available",
    "compile_and_run",
    "CSharpBridge",
    "CsharpFuture",
]

import os
import subprocess
import hashlib
import tempfile
import ctypes
import platform
import inspect
import threading
import shutil
from typing import Any

from ..manager import get_helper
from ..probe import _run_cmd_timeout
from .._base import LangBridge, FunctionSpec
from ..core.types import LangType
from .types import get_cs_type, get_cs_ctype, infer_cs_argtypes, PY_TO_CS_TYPE, CS_TO_CTYPES
from .templates import generate_cs_method, generate_cs_class, generate_csproj, generate_cs_program

_IS_WINDOWS = platform.system() == 'Windows'

# 使用 manager 的编译器辅助
_csharp_helper = get_helper('csharp')

# 缓存目录
_CS_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_csharp_cache')

# 编译锁：防止并发编译同一项目时的文件竞争
_compile_lock = threading.Lock()

def csharp_compiler_available():
    """
    检查 C# 编译器是否可用

    使用 manager 统一管理。

    返回：
        bool: dotnet 是否可用
    """
    return _csharp_helper.is_available()


def _exe_path_for(dll_path):
    """由 DLL 路径推导同目录、同名的可执行文件路径（_call_csharp_func 依赖它）。"""
    base = os.path.splitext(dll_path)[0]
    return (base + '.exe') if _IS_WINDOWS else base


def _cache_entry_valid(cache_dir, dll_name):
    """缓存条目是否完整可用：DLL 与其同名可执行文件都在。

    _call_csharp_func 实际跑的是同目录同名的 apphost/exe，只用
    `os.path.exists(dll_path)` 判缓存会让"有 DLL 无 exe"的半截缓存命中，
    返回一个点不到的路径 -> 调用期 FileNotFoundError（本会话 test_csharp_bridge
    在 py3.6 就是这样失败：dotnet publish 偶发只留 .dll 未产出/被清掉 .exe）。
    这里要求 .dll 与 .exe 同时存在才算命中，否则视为需要重编。
    """
    dll_path = os.path.join(cache_dir, dll_name + '.dll')
    if not os.path.exists(dll_path):
        return False
    return os.path.exists(_exe_path_for(dll_path))


def _compile_csharp_code(cs_code, func_name, cache_dir=None):
    """
    编译 C# 代码为 DLL

    流程：
    1. 计算代码 MD5 哈希
    2. 检查缓存是否已存在 DLL
    3. 创建临时项目目录
    4. 写入 .cs 和 .csproj 文件
    5. 运行 dotnet publish (NativeAOT)
    6. 返回 DLL 路径

    参数：
        cs_code: C# 类代码（完整类定义）
        func_name: 函数名称（用于命名 DLL）
        cache_dir: 缓存目录，默认使用全局缓存

    返回：
        DLL 文件路径

    异常：
        RuntimeError: 编译失败时抛出
    """
    if cache_dir is None:
        cache_dir = _CS_CACHE_DIR

    os.makedirs(cache_dir, exist_ok=True)

    # 计算哈希（使用完整 32 字符，与 LangBridge 缓存键保持一致，避免 apphost 重命名后找不到 DLL）
    code_hash = hashlib.md5(cs_code.encode('utf-8')).hexdigest()
    dll_name = f'{func_name}_{code_hash}'

    # 检查缓存
    dll_path = os.path.join(cache_dir, dll_name + '.dll')
    if _cache_entry_valid(cache_dir, dll_name):
        return dll_path

    # 创建项目目录
    project_dir = os.path.join(cache_dir, dll_name)
    os.makedirs(project_dir, exist_ok=True)

    # 写入文件
    cs_file = os.path.join(project_dir, 'Bridge.cs')
    csproj_file = os.path.join(project_dir, 'Bridge.csproj')
    program_file = os.path.join(project_dir, 'Program.cs')

    with open(cs_file, 'w', encoding='utf-8') as f:
        f.write(cs_code)

    with open(csproj_file, 'w', encoding='utf-8') as f:
        f.write(generate_csproj(dll_name))

    with open(program_file, 'w', encoding='utf-8') as f:
        f.write(generate_cs_program())

    # 编译（使用锁防止并发编译同一项目时的文件竞争）
    with _compile_lock:
        # 双重检查：可能在等待锁期间其他线程已完成编译
        if _cache_entry_valid(cache_dir, dll_name):
            return dll_path

        # 半截产物被中断（如批跑杀 dotnet）后，project_dir 的 obj/bin 里已有
        # 「编译完成」标记，直接再 publish 会被 dotnet 判为 up-to-date 而跳过
        # apphost(.exe) 生成，自愈变空转（实测：毒缓存下重发后仍缺 exe）。
        # 重发前清掉增量目录，强制完整构建。
        for _stale in ('obj', 'bin'):
            _sd = os.path.join(project_dir, _stale)
            if os.path.isdir(_sd):
                shutil.rmtree(_sd, ignore_errors=True)

        # 同理清掉 cache_dir 里「同名 .dll 无 .exe」的半截条目（含伴生文件），
        # 否则 publish 即使成功，陈旧半截 dll 也可能让命中逻辑指到坏文件。
        _exe_path = _exe_path_for(dll_path)
        if os.path.exists(dll_path) and not os.path.exists(_exe_path):
            for _stale in (dll_path,
                           os.path.splitext(dll_path)[0] + '.pdb',
                           dll_path + '.runtimeconfig.json'):
                if os.path.exists(_stale):
                    try:
                        os.remove(_stale)
                    except OSError:
                        pass

        result = _run_cmd_timeout(
            ['dotnet', 'publish', '-c', 'Release', '-o', cache_dir],
            cwd=project_dir,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(f'C# 编译失败:\n{result.stderr.decode("utf-8", errors="replace")}\n{result.stdout.decode("utf-8", errors="replace")}')

    # 验证产物齐全。_call_csharp_func 实际跑的是【同目录同名的 apphost/exe】
    # （见下方 line 184 的调用期检查），而 dotnet publish 偶发只产出 .dll 不产出
    # .exe。旧实现只用 os.path.exists(dll_path) 验 DLL，半截产物被原样返回、
    # 调用期才抛 FileNotFoundError——报错不指向真因。这里按调用方真实不变式校验：
    # DLL 与同名 exe 必须同时存在；仍不齐才抛带上下文的 RuntimeError。
    if _cache_entry_valid(cache_dir, dll_name):
        return dll_path

    # 兼容旧命名：dotnet 可能以 cs_ 前缀产出 DLL。找到「DLL + 同名 exe」齐全的一份。
    for file in sorted(os.listdir(cache_dir)):
        if file.endswith('.dll') and file.startswith('cs_'):
            cand = os.path.join(cache_dir, file)
            if os.path.exists(_exe_path_for(cand)):
                return cand

    raise RuntimeError(
        f'C# 编译产物不完整：{dll_path} 及其同名 .exe 必须同时存在（_call_csharp_func '
        f'跑的是 exe），但重发后仍缺失。\nstderr:\n{result.stderr}\nstdout:\n{result.stdout}'
    )


def _call_csharp_func(dll_path, func_name, args, ret_type=None):
    """
    调用 C# 编译产物中的函数

    当前环境缺少 NativeAOT 链接器，无法通过 ctypes 直接调用 DLL 导出符号；
    改为启动生成的可执行文件，通过 JSON stdin/stdout 调用托管方法。

    参数：
        dll_path: 编译生成的 DLL 文件路径（exe 与其同名）
        func_name: 函数名称
        args: 参数列表
        ret_type: Python 返回类型注解（仅用于结果转换）

    返回：
        函数返回值
    """
    import json

    # 根据 DLL 路径推导同目录下的可执行文件路径
    base_path = os.path.splitext(dll_path)[0]
    if _IS_WINDOWS:
        exe_path = base_path + '.exe'
    else:
        exe_path = base_path

    if not os.path.exists(exe_path):
        raise FileNotFoundError(f'C# 可执行文件不存在: {exe_path}')

    payload = json.dumps({'func': func_name, 'args': list(args)}, ensure_ascii=False)

    result = _run_cmd_timeout(
        [exe_path],
        input_data=payload + '\n',
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f'C# 进程调用失败 (exit {result.returncode}):\n'
            f'stdout: {result.stdout.decode("utf-8", errors="replace")}\nstderr: {result.stderr.decode("utf-8", errors="replace")}'
        )

    output = result.stdout.decode('utf-8', errors='replace').strip()
    if not output:
        return None

    # 尝试按 JSON 解析输出；失败时按字符串返回
    try:
        return json.loads(output)
    except Exception:
        return output


def compile_and_run(cs_code, func_name='main', args=(), ret_type=int, cache_dir=None):
    """
    便捷函数：编译并运行 C# 代码

    参数：
        cs_code: C# 方法体代码
        func_name: 函数名称
        args: 参数列表
        ret_type: 返回类型
        cache_dir: 缓存目录

    返回：
        函数返回值
    """
    # 生成完整代码
    params = []
    for i, arg in enumerate(args):
        cs_type = get_cs_type(type(arg), arg)
        params.append((f'arg{i}', cs_type))

    cs_ret = get_cs_type(ret_type)
    method_code = generate_cs_method(func_name, params, cs_ret, cs_code)
    class_code = generate_cs_class([method_code])

    dll_path = _compile_csharp_code(class_code, func_name, cache_dir)
    return _call_csharp_func(dll_path, func_name, args, ret_type)


# ============================================================================
# CSharpBridge - C# 桥接实现（继承 LangBridge）
# ============================================================================

class CSharpBridge(LangBridge):
    """
    C# 语言桥接实现

    继承 LangBridge 抽象基类，实现 C# 特定的代码生成、编译和调用。
    """

    name = 'csharp'
    file_ext = '.cs'
    lib_ext = '.dll'
    lang_type = LangType.DOTNET

    def __init__(self):
        super().__init__()

    def compiler_available(self) -> bool:
        """编译器是否可用"""
        return csharp_compiler_available()

    def check_cache(self, code, func_name, cache_dir=None):
        """C# 缓存命中判定：DLL 与【同名 .exe】必须同时存在。

        基类 check_cache 只用 os.path.exists 验 .dll；而 _call_csharp_func 实际跑的是
        同目录同名的 apphost/.exe。当缓存被半截产物污染（dotnet publish 被中断、只留下
        .dll 没有 .exe）时，基类会返回这个坏路径，调用期抛 FileNotFoundError——@csharp
        装饰器走的是这条基类缓存路径（csharp = _csharp_bridge.decorator），实测批跑中断
        dotnet 后就是这样失败。这里覆盖判定：要求 .dll 与 .exe 都在，否则视为未命中，
        让上层 _compile_with_cache 触发重新编译（自愈）。
        """
        cache_dir = self.get_cache_dir(cache_dir)
        cache_key = self.get_cache_key(code, func_name)
        dll_name = cache_key  # get_lib_filename 追加 .dll
        if _cache_entry_valid(cache_dir, dll_name):
            return os.path.join(cache_dir, self.get_lib_filename(cache_key))
        return None

    def generate_code(self, spec: FunctionSpec) -> str:
        """
        生成 C# 代码

        包含：
        1. module_code（用户提供的模块级代码）
        2. 依赖函数（从 deps 参数生成）
        3. 主函数
        """
        methods = []

        # 依赖函数（按顺序生成）
        for dep in spec.dependencies:
            dep_method = self._generate_method(dep)
            if dep_method:
                methods.append(dep_method)

        # 主函数
        main_method = self._generate_method(spec)
        methods.append(main_method)

        # 生成类代码
        class_code = generate_cs_class(methods)

        # 如果有 module_code，暂时放在类前面（C# 中可以有额外的 using 或 namespace 代码）
        if spec.module_code:
            return spec.module_code + '\n' + class_code

        return class_code

    def _generate_method(self, spec: FunctionSpec) -> str:
        """生成单个方法的 C# 代码"""
        params = []

        for name, ann in spec.annotations.items():
            if name == 'return':
                continue
            if ann is None or ann is inspect.Parameter.empty:
                cs_type = 'int'
            else:
                cs_type = PY_TO_CS_TYPE.get(ann, 'int')
            params.append((name, cs_type))

        ret_type = 'int'
        if 'return' in spec.annotations:
            ann = spec.annotations['return']
            if ann is type(None) or str(ann).lower() == 'none':
                ret_type = 'void'
            else:
                ret_type = PY_TO_CS_TYPE.get(ann, 'int')

        return generate_cs_method(spec.name, params, ret_type, spec.body)

    def compile_code(self, code: str, func_name: str, cache_dir: str = None) -> str:
        """编译 C# 代码"""
        return _compile_csharp_code(code, func_name, cache_dir)

    def save_to_cache(self, code: str, func_name: str,
                      lib_path: str, cache_dir: str = None) -> str:
        """保存编译产物到缓存。

        编译时已直接生成到最终缓存文件名，因此当路径相同时跳过移动，
        避免 .NET apphost 因 DLL/EXE 重命名而找不到程序集。
        """
        cache_dir = self.get_cache_dir(cache_dir)
        cache_key = self.get_cache_key(code, func_name)
        cached_path = os.path.join(cache_dir, self.get_lib_filename(cache_key))
        if os.path.normcase(os.path.abspath(lib_path)) == os.path.normcase(os.path.abspath(cached_path)):
            return cached_path
        return super().save_to_cache(code, func_name, lib_path, cache_dir)

    def compile_project(self, project_dir: str, entry: str, output_dir: str = None) -> str:
        """
        编译 C# 项目

        使用 dotnet build 编译整个项目。
        entry='main' 时生成 exe，否则生成 dll。
        """
        output_dir = output_dir or _CS_CACHE_DIR
        os.makedirs(output_dir, exist_ok=True)

        # 检查是否有 .csproj 文件
        csproj_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith('.csproj'):
                    csproj_files.append(os.path.join(root, f))

        if not csproj_files:
            raise RuntimeError(f'No .csproj file found in project directory: {project_dir}')

        csproj_file = csproj_files[0]
        project_dir = os.path.dirname(csproj_file)

        # 编译（使用 NativeAOT 发布）
        result = _run_cmd_timeout(
            ['dotnet', 'publish', '-c', 'Release', '-o', output_dir],
            cwd=project_dir,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f'C# project compilation failed:\n'
                f'stderr:\n{result.stderr.decode("utf-8", errors="replace")}\n'
                f'stdout:\n{result.stdout.decode("utf-8", errors="replace")}'
            )

        # 查找生成的产物
        project_name = os.path.splitext(os.path.basename(csproj_file))[0]

        if entry == 'main':
            if _IS_WINDOWS:
                output_path = os.path.join(output_dir, f'{project_name}.exe')
            else:
                output_path = os.path.join(output_dir, project_name)
        else:
            output_path = os.path.join(output_dir, f'{project_name}.dll')

        if not os.path.exists(output_path):
            # 尝试查找其他可能的输出
            for f in os.listdir(output_dir):
                if entry == 'main':
                    if f.endswith('.exe') or (not _IS_WINDOWS and not f.endswith('.dll') and os.path.isfile(os.path.join(output_dir, f))):
                        output_path = os.path.join(output_dir, f)
                        break
                else:
                    if f.endswith('.dll') and not f.endswith('.runtimeconfig.dev.json'):
                        output_path = os.path.join(output_dir, f)
                        break

        return output_path

    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type=None) -> Any:
        """调用 C# 编译的函数

        Args:
            lib_path: DLL 文件路径。
            func_name: 函数名称。
            args: 参数元组。
            ret_type: Python 返回类型，用于类型转换。

        Returns:
            函数返回值。
        """
        return _call_csharp_func(lib_path, func_name, args, ret_type)


# ============================================================================
# CsharpFuture - 异步 Future 包装器
# ============================================================================

class CsharpFuture:
    """C# 异步执行结果包装器。

    包装 concurrent.futures.Future，提供 result() 和 __await__ 支持，
    使 C# 函数调用可以在异步上下文中使用 await。

    Attributes:
        _future: 底层的 concurrent.futures.Future 对象。
        _dll_path: 编译生成的 DLL 文件路径。
        _func_name: 调用的函数名称。
        _ret_type: Python 返回值类型。
    """

    def __init__(self, future, dll_path, func_name, ret_type=None):
        """初始化 CsharpFuture。

        Args:
            future: concurrent.futures.Future 实例。
            dll_path: DLL 文件路径。
            func_name: 函数名称。
            ret_type: Python 返回值类型。
        """
        self._future = future
        self._dll_path = dll_path
        self._func_name = func_name
        self._ret_type = ret_type

    def result(self, timeout=None):
        """获取执行结果。

        Args:
            timeout: 超时时间（秒），None 表示无限等待。

        Returns:
            Any: 函数执行结果。
        """
        return self._future.result(timeout=timeout)

    def __await__(self):
        """支持 await 语法。

        通过 asyncio 将 Future 包装为可等待对象。
        """
        import asyncio
        return asyncio.wrap_future(self._future).__await__()


# 全局 CSharpBridge 实例
_csharp_bridge = CSharpBridge()

# 统一装饰器接口（使用 LangBridge 标准装饰器）
csharp = _csharp_bridge.decorator
cs = csharp
