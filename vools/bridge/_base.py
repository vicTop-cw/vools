"""
vools.bridge._base - 跨语言桥接抽象接口 (Lang Bridge)

定义统一的 Lang 接口规范，所有语言桥接模块必须实现此接口。

本模块提供了跨语言桥接的核心抽象基础设施，包括：
    - FunctionSpec: 函数规格数据类，封装函数的元信息
    - CompileResult: 编译结果数据类，封装编译状态和产物信息
    - FunctionParser: 函数解析器，从 Python 函数提取规格信息
    - DepResolver: 依赖解析器，处理函数间的依赖关系与拓扑排序
    - LangBridge: 语言桥接抽象基类，定义统一的接口规范

架构：
                    ┌─────────────────────────────────────┐
                    │        LangBridge (ABC)            │
                    │    所有语言的统一抽象接口            │
                    └──────────────┬──────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
         ▼                         ▼                         ▼
  ┌────────────┐           ┌────────────┐           ┌────────────┐
  │  NimBridge │           │  CBridge   │           │ FbcBridge  │
  └──────┬─────┘           └──────┬─────┘           └──────┬─────┘
         │                         │                         │
         ▼                         ▼                         ▼
  各语言具体实现：         各语言具体实现：         各语言具体实现：
  - 代码生成               - 代码生成               - 代码生成
  - 编译调用               - 编译调用               - 编译调用
  - 类型映射               - 类型映射               - 类型映射

统一装饰器用法（所有语言一致）：
    @lang(deps=[helper1, helper2], module_code="...", async_mode=False, fallback=fn)
    def my_func(x: int) -> int:
        return "..."  # 函数体

Typical usage example:
    bridge = SomeLangBridge()

    @bridge.decorator
    def add(x: int, y: int) -> int:
        return "return x + y"

    result = add(1, 2)
"""

import os
import sys
import abc
import hashlib
import tempfile
import functools
import inspect
import asyncio
import ctypes
from concurrent.futures import ThreadPoolExecutor
from typing import (
    Callable, Dict, List, Optional, Any, Union,
    get_type_hints,
)
from vools.core.dataclass_compat import dataclass, field
from vools.core.asyncio_compat import run as asyncio_run


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class FunctionSpec:
    """函数的完整规格。

    包含函数的所有元信息，用于生成目标语言代码。

    Attributes:
        name: 函数名称。
        annotations: 函数参数和返回值的类型注解字典。
        args: 位置参数元组，用于调用函数提取函数体。
        defaults: 参数默认值字典，键为参数名，值为默认值。
        body: 函数体代码字符串，用于生成目标语言代码。
        module_code: 模块级代码，会放在所有函数定义之前。
        dependencies: 依赖的函数规格列表，按依赖顺序排列。
    """
    name: str
    annotations: Dict[str, type]
    args: tuple
    defaults: Dict[str, Any]
    body: str
    module_code: str = ''
    dependencies: List['FunctionSpec'] = field(default_factory=list)


@dataclass
class CompileResult:
    """编译结果。

    封装编译操作的状态和产物信息。

    Attributes:
        success: 编译是否成功。
        lib_path: 编译生成的库文件路径，失败时为 None。
        error: 编译错误信息，成功时为 None。
        warnings: 编译警告信息列表。
    """
    success: bool
    lib_path: Optional[str] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


# ============================================================================
# 函数解析器（工具类，所有语言共用）
# ============================================================================

class FunctionParser:
    """函数解析器 - 从 Python 函数提取规格信息。

    所有语言共用，不需要子类化。提供从 Python 函数对象中
    提取函数名称、类型注解、参数列表、默认值和函数体等
    元信息的静态方法。

    使用 BridgeSigCache 进行签名缓存，提高重复解析的性能。
    """

    _cache = None

    @classmethod
    def _get_cache(cls):
        """获取函数解析器的缓存实例。"""
        if cls._cache is None:
            from .core.sigcache import BridgeSigCache
            cls._cache = BridgeSigCache(lang="parser")
        return cls._cache

    @staticmethod
    def parse(func: Callable, *args: Any, **kwargs: Any) -> FunctionSpec:
        """解析 Python 函数并生成 FunctionSpec。

        提取函数的名称、类型注解、参数默认值，并通过调用函数
        获取函数体代码字符串。

        Args:
            func: 要解析的 Python 函数对象。
            *args: 传递给函数的位置参数，用于调用函数获取函数体。
            **kwargs: 传递给函数的关键字参数，用于调用函数获取函数体。

        Returns:
            FunctionSpec: 包含函数完整规格信息的数据类实例。

        Raises:
            无。调用失败时会静默降级，尝试其他方式获取函数体。
        """
        cache = FunctionParser._get_cache()
        return cache.get_spec(func, args, kwargs)

    @staticmethod
    def from_body(name: str, body: str, annotations: Optional[Dict[str, type]] = None) -> FunctionSpec:
        """从函数体字符串创建 FunctionSpec（用于依赖函数）。

        当已有函数体代码字符串时，直接构建函数规格，
        无需从 Python 函数对象解析。

        Args:
            name: 函数名称。
            body: 函数体代码字符串。
            annotations: 类型注解字典，默认为空字典。

        Returns:
            FunctionSpec: 包含函数规格信息的数据类实例。
        """
        return FunctionSpec(
            name=name,
            annotations=annotations or {},
            args=(),
            defaults={},
            body=body,
        )

    @staticmethod
    def get_arg_names(func: Callable) -> List[str]:
        """获取函数的参数名列表。

        通过 inspect 模块解析函数签名，提取所有参数名称。

        Args:
            func: 要解析的 Python 函数对象。

        Returns:
            List[str]: 参数名称列表，按定义顺序排列。
        """
        cache = FunctionParser._get_cache()
        sig = cache.get_signature(func)
        return list(sig.parameters.keys())

    @staticmethod
    def get_return_type(func: Callable) -> Optional[type]:
        """获取函数的返回类型。

        优先使用 typing.get_type_hints 获取解析后的类型注解，
        失败时回退到原始的 __annotations__ 字典。

        Args:
            func: 要解析的 Python 函数对象。

        Returns:
            Optional[type]: 返回值类型，如果未定义则返回 None。
        """
        cache = FunctionParser._get_cache()
        annotations = cache.get_annotations(func)
        return annotations.get('return')


# ============================================================================
# 依赖解析器（工具类，所有语言共用）
# ============================================================================

class DepResolver:
    """依赖解析器 - 处理函数间的依赖关系。

    所有语言共用，不需要子类化。负责注册依赖函数、解析显式依赖、
    提取依赖函数的函数体，以及对函数规格进行拓扑排序。

    Attributes:
        _dep_registry: 依赖函数注册表，键为函数名，值为函数对象。
    """

    def __init__(self) -> None:
        """初始化依赖解析器。"""
        self._dep_registry: Dict[str, Callable] = {}

    def register(self, func: Callable) -> str:
        """注册一个依赖函数到注册表。

        将函数以其名称为键存入内部注册表，供其他函数引用。

        Args:
            func: 要注册的 Python 函数对象。

        Returns:
            str: 注册的函数名称。
        """
        name = func.__name__
        self._dep_registry[name] = func
        return name

    def resolve(self, spec: FunctionSpec, explicit_deps: Optional[List[Callable]] = None) -> FunctionSpec:
        """解析函数的依赖关系并填充到 spec.dependencies 中。

        遍历显式依赖函数列表，提取每个依赖函数的函数体和类型注解，
        生成对应的 FunctionSpec 并添加到 spec 的 dependencies 列表中。

        Args:
            spec: 要解析依赖的函数规格。
            explicit_deps: 显式指定的依赖函数列表，默认为 None。

        Returns:
            FunctionSpec: 填充了依赖关系的函数规格（原地修改并返回）。
        """
        dependencies = []

        if explicit_deps:
            for dep_func in explicit_deps:
                dep_spec = FunctionParser.from_body(
                    dep_func.__name__,
                    self._get_dep_body(dep_func),
                    self._get_dep_annotations(dep_func),
                )
                dependencies.append(dep_spec)

        spec.dependencies = dependencies
        return spec

    def _get_dep_body(self, func: Callable) -> str:
        """获取依赖函数的函数体代码。

        按以下优先级尝试获取函数体：
        1. 无参调用函数获取返回值
        2. 使用 AST 解析源代码，提取 return 语句后的字符串
        3. 读取函数的 __body__ 属性
        4. 读取函数的 docstring

        Args:
            func: 要提取函数体的函数对象。

        Returns:
            str: 提取到的函数体代码字符串，提取失败返回空字符串。
        """
        try:
            result = func()
            if result is not None:
                return str(result)
        except TypeError:
            pass
        except Exception:
            pass

        try:
            import ast
            import textwrap
            source = inspect.getsource(func)
            source = textwrap.dedent(source)
            tree = ast.parse(source)
            func_def = None
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_def = node
                    break
            if func_def:
                for node in ast.walk(func_def):
                    if isinstance(node, ast.Return):
                        if isinstance(node.value, ast.Constant):
                            return str(node.value.value)
                        elif isinstance(node.value, ast.JoinedStr):
                            parts = []
                            for v in node.value.values:
                                if isinstance(v, ast.Constant):
                                    parts.append(str(v.value))
                            return ''.join(parts)
        except Exception:
            pass

        body = getattr(func, '__body__', '')
        if body:
            return body

        if func.__doc__:
            return func.__doc__

        return ''

    def _get_dep_annotations(self, func: Callable) -> Dict[str, type]:
        """获取依赖函数的类型注解。

        优先使用 typing.get_type_hints 获取解析后的类型注解，
        失败时回退到原始的 __annotations__ 字典。

        Args:
            func: 要获取注解的函数对象。

        Returns:
            Dict[str, type]: 类型注解字典，键为参数名或 'return'。
        """
        try:
            return get_type_hints(func)
        except Exception:
            return func.__annotations__

    def topological_sort(self, specs: List[FunctionSpec]) -> List[FunctionSpec]:
        """对函数规格列表进行拓扑排序。

        根据函数间的依赖关系进行 Kahn 拓扑排序，确保被依赖的函数
        排在依赖者之前。

        Args:
            specs: 要排序的函数规格列表。

        Returns:
            List[FunctionSpec]: 按依赖顺序排列的函数规格列表。
        """
        name_to_spec = {s.name: s for s in specs}
        in_degree = {s.name: 0 for s in specs}
        graph = {s.name: [] for s in specs}

        for spec in specs:
            for dep in spec.dependencies:
                if dep.name in name_to_spec:
                    graph[dep.name].append(spec.name)
                    in_degree[spec.name] += 1

        queue = [name for name, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(name_to_spec[node])
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result


# ============================================================================
# LangBridge 抽象基类（核心接口）
# ============================================================================

class LangBridge(abc.ABC):
    """语言桥接抽象基类。

    所有语言桥接模块必须继承此类并实现抽象方法。
    提供统一的装饰器接口、编译缓存、依赖解析等公共功能。

    子类必须实现：
        - name: str                    语言名称
        - file_ext: str                源文件扩展名
        - lib_ext: str                 库文件扩展名 (.dll/.so/.dylib)
        - compiler_available() -> bool  编译器是否可用
        - generate_code(spec) -> str   生成目标语言代码
        - compile_code(code, name, cache_dir) -> str  编译代码，返回库路径
        - call_func(lib_path, func_name, args, ret_type) -> Any  调用函数

    子类可以重写：
        - supports_nested_functions -> bool  是否支持函数嵌套（默认 True）
        - default_cache_dir -> str           默认缓存目录

    Attributes:
        name: 语言名称标识。
        file_ext: 源文件扩展名（如 '.c', '.nim', '.bas'）。
        lib_ext: 编译产物库文件扩展名（如 '.dll', '.so', '.dylib'）。
        _dep_resolver: 依赖解析器实例。
        _cache_dir: 用户指定的缓存目录，为 None 时使用默认目录。
        _executor: 异步执行用的线程池实例，懒加载。
    """

    name: str = ''
    file_ext: str = ''
    lib_ext: str = ''

    def __init__(self) -> None:
        """初始化语言桥接器。"""
        self._dep_resolver: DepResolver = DepResolver()
        self._cache_dir: Optional[str] = None
        self._executor: Optional[ThreadPoolExecutor] = None

    # ------------------------------------------------------------------
    # 抽象方法（子类必须实现）
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def compiler_available(self) -> bool:
        """检查目标语言编译器是否可用。

        Returns:
            bool: 编译器可用返回 True，否则返回 False。
        """
        ...

    @abc.abstractmethod
    def generate_code(self, spec: FunctionSpec) -> str:
        """根据函数规格生成目标语言源代码。

        Args:
            spec: 函数规格，包含函数名、参数、类型注解、函数体等信息。

        Returns:
            str: 完整的目标语言源文件代码。
        """
        ...

    @abc.abstractmethod
    def compile_code(self, code: str, func_name: str, cache_dir: Optional[str] = None) -> str:
        """编译源代码为动态库。

        Args:
            code: 目标语言源代码字符串。
            func_name: 函数名，用于生成临时文件名。
            cache_dir: 缓存目录，为 None 时使用默认缓存目录。

        Returns:
            str: 编译生成的动态库文件路径。

        Raises:
            RuntimeError: 编译失败时抛出。
        """
        ...

    @abc.abstractmethod
    def compile_project(self, project_dir: str, entry: str, output_dir: Optional[str] = None) -> str:
        """编译整个项目目录。

        Args:
            project_dir: 项目根目录路径。
            entry: 入口函数名，'main' 表示编译为可执行文件。
            output_dir: 输出目录，为 None 时使用默认输出目录。

        Returns:
            str: 编译产物路径（可执行文件或动态库）。

        Raises:
            RuntimeError: 编译失败时抛出。
        """
        ...

    @abc.abstractmethod
    def call_func(self, lib_path: str, func_name: str,
                  args: tuple, ret_type: Optional[type] = None) -> Any:
        """调用编译后的动态库中的函数。

        Args:
            lib_path: 动态库文件路径。
            func_name: 要调用的函数名称。
            args: 传递给函数的参数元组。
            ret_type: 返回值类型，用于类型转换，为 None 时使用默认转换。

        Returns:
            Any: 函数执行后的返回值。
        """
        ...

    # ------------------------------------------------------------------
    # 可重写方法（子类可以选择性重写）
    # ------------------------------------------------------------------

    def supports_nested_functions(self) -> bool:
        """判断该语言是否支持函数嵌套定义。

        Returns:
            bool: 支持返回 True，不支持返回 False。默认为 True。
        """
        return True

    def default_cache_dir(self) -> str:
        """获取默认的编译缓存目录路径。

        Returns:
            str: 默认缓存目录的绝对路径，位于系统临时目录下。
        """
        return os.path.join(tempfile.gettempdir(), f'vools_{self.name}_cache')

    def get_lib_filename(self, func_name: str) -> str:
        """根据函数名生成库文件名。

        根据操作系统自动添加前缀：Windows 下无 'lib' 前缀，
        Unix/Linux/macOS 下添加 'lib' 前缀。

        Args:
            func_name: 函数名称。

        Returns:
            str: 库文件名称（不含路径）。
        """
        if os.name == 'nt':
            return f'{func_name}{self.lib_ext}'
        else:
            return f'lib{func_name}{self.lib_ext}'

    def get_source_filename(self, func_name: str) -> str:
        """根据函数名生成源文件名。

        Args:
            func_name: 函数名称。

        Returns:
            str: 源文件名称（不含路径）。
        """
        return f'{func_name}{self.file_ext}'

    # ------------------------------------------------------------------
    # 公共方法（装饰器使用，不需要重写）
    # ------------------------------------------------------------------

    def get_cache_dir(self, override: Optional[str] = None) -> str:
        """获取并确保缓存目录存在。

        优先级：override > self._cache_dir > default_cache_dir()。

        Args:
            override: 可选的缓存目录覆盖路径。

        Returns:
            str: 缓存目录的绝对路径（已创建）。
        """
        cache_dir = override or self._cache_dir or self.default_cache_dir()
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def get_cache_key(self, code: str, func_name: str) -> str:
        """根据代码内容和函数名生成缓存键。

        使用 MD5 哈希代码内容，确保相同代码生成相同缓存键。

        Args:
            code: 源代码字符串。
            func_name: 函数名称。

        Returns:
            str: 缓存键字符串，格式为 '{func_name}_{md5_hash}'。
        """
        code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()
        return f'{func_name}_{code_hash}'

    def check_cache(self, code: str, func_name: str, cache_dir: Optional[str] = None) -> Optional[str]:
        """检查编译缓存是否存在。

        根据代码内容计算缓存键，查找对应的库文件。

        Args:
            code: 源代码字符串。
            func_name: 函数名称。
            cache_dir: 缓存目录，为 None 时使用默认目录。

        Returns:
            Optional[str]: 缓存的库文件路径，不存在则返回 None。
        """
        cache_dir = self.get_cache_dir(cache_dir)
        cache_key = self.get_cache_key(code, func_name)
        lib_path = os.path.join(cache_dir, self.get_lib_filename(cache_key))
        if os.path.exists(lib_path):
            return lib_path
        return None

    def save_to_cache(self, code: str, func_name: str,
                      lib_path: str, cache_dir: Optional[str] = None) -> str:
        """将编译产物保存到缓存目录。

        复制编译生成的库文件到缓存目录，使用代码哈希作为文件名。

        Args:
            code: 源代码字符串。
            func_name: 函数名称。
            lib_path: 编译生成的库文件路径。
            cache_dir: 缓存目录，为 None 时使用默认目录。

        Returns:
            str: 缓存中的库文件路径。
        """
        cache_dir = self.get_cache_dir(cache_dir)
        cache_key = self.get_cache_key(code, func_name)
        cached_path = os.path.join(cache_dir, self.get_lib_filename(cache_key))

        import shutil
        try:
            shutil.copy2(lib_path, cached_path)
        except Exception:
            pass

        return cached_path

    # ------------------------------------------------------------------
    # 装饰器工厂
    # ------------------------------------------------------------------

    def decorator(
        self,
        func: Optional[Callable] = None,
        *,
        mode: str = 'NORMAL',
        deps: Optional[List[Callable]] = None,
        module_code: Optional[str] = None,
        async_mode: bool = False,
        fallback: Optional[Callable] = None,
        cache_dir: Optional[str] = None,
        ret_type: Optional[type] = None,
        only_code: bool = False,
        output_file: Optional[str] = None,
        write_mode: str = 'overwrite',
        prefix: str = '',
        suffix: str = '',
        project_dir: Optional[str] = None,
        entry: str = 'main',
    ) -> Callable:
        """装饰器工厂函数。

        统一的装饰器接口，所有语言桥接实现保持一致。
        支持带参数和不带参数两种调用方式。

        Args:
            func: 被装饰的函数对象，无参数使用装饰器时自动传入。
            mode: 运行模式，可选值：
                - 'NORMAL': 正常模式，命中缓存跳过编译；未命中则编译
                - 'DEBUG': 强制重新编译并执行
                - 'FORCE': 强制重新编译但不执行
                - 'ONLY_RUN': 只在有缓存时执行；没有则报错
                - 'ONLY_CODE': 只生成源码，不编译
            deps: 显式依赖函数列表，这些函数会在目标函数之前生成。
            module_code: 模块级代码，会放在所有函数定义之前。
            async_mode: 是否启用异步模式，为 True 时返回 async 包装器。
            fallback: 回退函数，编译器不可用或编译失败时调用。
            cache_dir: 编译缓存目录，为 None 时使用默认缓存目录。
            ret_type: 返回值类型，用于 ctypes 返回类型转换。
            only_code: 仅代码模式，不编译，只生成目标语言代码。
            output_file: 输出文件路径，仅代码模式下将代码写入该文件。
            write_mode: 写入模式，可选值：
                - 'overwrite': 覆盖整个文件
                - 'append': 追加到文件末尾
                - 'insert:NN': 插入到第 NN 行之后
                - 'replace:MM-NN': 替换第 MM 到 NN 行
            prefix: 代码前缀，仅代码模式下包裹在生成代码之前。
            suffix: 代码后缀，仅代码模式下包裹在生成代码之后。
            project_dir: 项目目录路径，设置后进入项目模式。
            entry: 入口函数名，项目模式下使用，默认为 'main'。

        Returns:
            Callable: 装饰后的函数包装器。

        Examples:
            基础用法::

                @bridge.decorator
                def add(x: int, y: int) -> int:
                    return "return x + y"

            带依赖和模块代码::

                @bridge.decorator(deps=[helper], module_code="...")
                def complex(x: int) -> int:
                    return "..."

            仅代码模式::

                @bridge.decorator(only_code=True, output_file="out.bas")
                def example(x: int) -> int:
                    return "..."

            项目模式::

                @bridge.decorator(project_dir="./my_project", entry="main")
                def my_app():
                    pass
        """
        def decorator(f: Callable) -> Callable:
            func_name = f.__name__

            self._dep_resolver.register(f)

            @functools.wraps(f)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return self._run_sync(
                    f, args, kwargs, mode, deps, module_code,
                    fallback, cache_dir, ret_type,
                    only_code, output_file, write_mode, prefix, suffix,
                    project_dir, entry
                )

            @functools.wraps(f)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await self._run_async(
                    f, args, kwargs, mode, deps, module_code,
                    fallback, cache_dir, ret_type,
                    only_code, output_file, write_mode, prefix, suffix,
                    project_dir, entry
                )

            if async_mode:
                return async_wrapper
            return wrapper

        if func is not None:
            return decorator(func)
        return decorator

    # ------------------------------------------------------------------
    # 内部执行逻辑
    # ------------------------------------------------------------------

    def _run_sync(self, func: Callable, args: tuple, kwargs: dict,
                  mode: str, deps: Optional[List[Callable]], module_code: Optional[str],
                  fallback: Optional[Callable], cache_dir: Optional[str],
                  ret_type: Optional[type],
                  only_code: bool = False, output_file: Optional[str] = None,
                  write_mode: str = 'overwrite',
                  prefix: str = '', suffix: str = '',
                  project_dir: Optional[str] = None, entry: str = 'main') -> Any:
        """同步执行被装饰的函数。

        根据参数选择执行模式：项目模式、仅代码模式或完整编译执行模式。

        Args:
            func: 被装饰的 Python 函数。
            args: 位置参数元组。
            kwargs: 关键字参数字典。
            mode: 运行模式（NORMAL/DEBUG/FORCE/ONLY_RUN/ONLY_CODE）。
            deps: 显式依赖函数列表。
            module_code: 模块级代码。
            fallback: 回退函数。
            cache_dir: 编译缓存目录。
            ret_type: 返回值类型。
            only_code: 是否仅代码模式。
            output_file: 输出文件路径。
            write_mode: 文件写入模式。
            prefix: 代码前缀。
            suffix: 代码后缀。
            project_dir: 项目目录路径。
            entry: 入口函数名。

        Returns:
            Any: 执行结果，可能是函数返回值、代码字符串或文件路径。

        Raises:
            RuntimeError: 编译器不可用且无回退函数时抛出。
            Exception: 编译或执行异常且无回退函数时重新抛出。
        """
        mode_upper = mode.upper() if isinstance(mode, str) else 'NORMAL'
        if mode_upper == 'ONLY_CODE':
            only_code = True

        if project_dir is not None:
            return self._run_project_sync(
                func, args, kwargs, project_dir, entry,
                fallback, cache_dir, ret_type, mode_upper
            )

        if only_code:
            return self._run_only_code(
                func, args, kwargs, deps, module_code,
                output_file, write_mode, prefix, suffix
            )

        if not self.compiler_available():
            if fallback:
                return fallback(*args, **kwargs)
            raise RuntimeError(
                f"{self.name} compiler not available "
                f"and no fallback provided for '{func.__name__}'"
            )

        try:
            spec = FunctionParser.parse(func, *args, **kwargs)
            if module_code:
                spec.module_code = module_code

            spec = self._dep_resolver.resolve(spec, deps)

            code = self.generate_code(spec)

            force_recompile = mode_upper in ('DEBUG', 'FORCE')
            if force_recompile:
                lib_path = self._compile_force(code, func.__name__, cache_dir)
            else:
                lib_path = self._compile_with_cache(code, func.__name__, cache_dir)

            if mode_upper == 'FORCE':
                return lib_path

            return self.call_func(lib_path, func.__name__, args, ret_type)

        except Exception:
            if fallback:
                return fallback(*args, **kwargs)
            raise

    async def _run_async(self, func: Callable, args: tuple, kwargs: dict,
                         mode: str, deps: Optional[List[Callable]], module_code: Optional[str],
                         fallback: Optional[Callable], cache_dir: Optional[str],
                         ret_type: Optional[type],
                         only_code: bool = False, output_file: Optional[str] = None,
                         write_mode: str = 'overwrite',
                         prefix: str = '', suffix: str = '',
                         project_dir: Optional[str] = None, entry: str = 'main') -> Any:
        """异步执行被装饰的函数。

        项目模式和仅代码模式直接异步执行，编译模式通过线程池同步执行。

        Args:
            func: 被装饰的 Python 函数。
            args: 位置参数元组。
            kwargs: 关键字参数字典。
            mode: 运行模式（NORMAL/DEBUG/FORCE/ONLY_RUN/ONLY_CODE）。
            deps: 显式依赖函数列表。
            module_code: 模块级代码。
            fallback: 回退函数。
            cache_dir: 编译缓存目录。
            ret_type: 返回值类型。
            only_code: 是否仅代码模式。
            output_file: 输出文件路径。
            write_mode: 文件写入模式。
            prefix: 代码前缀。
            suffix: 代码后缀。
            project_dir: 项目目录路径。
            entry: 入口函数名。

        Returns:
            Any: 执行结果。
        """
        mode_upper = mode.upper() if isinstance(mode, str) else 'NORMAL'
        if mode_upper == 'ONLY_CODE':
            only_code = True

        if project_dir is not None:
            return await self._run_project_async(
                func, args, kwargs, project_dir, entry,
                fallback, cache_dir, ret_type, mode_upper
            )

        if only_code:
            return await self._run_only_code_async(
                func, args, kwargs, deps, module_code,
                output_file, write_mode, prefix, suffix
            )

        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=4)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._run_sync(
                func, args, kwargs, mode, deps, module_code,
                fallback, cache_dir, ret_type,
                only_code, output_file, write_mode, prefix, suffix,
                project_dir, entry
            )
        )

    def _run_only_code(self, func: Callable, args: tuple, kwargs: dict,
                       deps: Optional[List[Callable]], module_code: Optional[str],
                       output_file: Optional[str], write_mode: str,
                       prefix: str, suffix: str) -> Any:
        """仅代码模式（同步执行）。

        生成目标语言代码但不编译，可选择写入文件。

        Args:
            func: 被装饰的 Python 函数。
            args: 位置参数元组。
            kwargs: 关键字参数字典。
            deps: 显式依赖函数列表。
            module_code: 模块级代码。
            output_file: 输出文件路径，为 None 则返回代码字符串。
            write_mode: 文件写入模式。
            prefix: 代码前缀。
            suffix: 代码后缀。

        Returns:
            Any: 指定了 output_file 则返回文件路径，否则返回代码字符串。
        """
        if inspect.iscoroutinefunction(func):
            body = asyncio_run(func(*args, **kwargs))
            spec = FunctionParser.from_body(func.__name__, body, self._get_func_annotations(func))
        else:
            spec = FunctionParser.parse(func, *args, **kwargs)

        if module_code:
            spec.module_code = module_code

        spec = self._dep_resolver.resolve(spec, deps)

        code = self.generate_code(spec)

        final_code = prefix + code + suffix

        if output_file:
            self._write_code_to_file(final_code, output_file, write_mode)
            return output_file

        return final_code

    async def _run_only_code_async(self, func: Callable, args: tuple, kwargs: dict,
                                   deps: Optional[List[Callable]], module_code: Optional[str],
                                   output_file: Optional[str], write_mode: str,
                                   prefix: str, suffix: str) -> Any:
        """仅代码模式（异步执行）。

        生成目标语言代码但不编译，可选择写入文件。

        Args:
            func: 被装饰的 Python 函数。
            args: 位置参数元组。
            kwargs: 关键字参数字典。
            deps: 显式依赖函数列表。
            module_code: 模块级代码。
            output_file: 输出文件路径，为 None 则返回代码字符串。
            write_mode: 文件写入模式。
            prefix: 代码前缀。
            suffix: 代码后缀。

        Returns:
            Any: 指定了 output_file 则返回文件路径，否则返回代码字符串。
        """
        if inspect.iscoroutinefunction(func):
            body = await func(*args, **kwargs)
            spec = FunctionParser.from_body(func.__name__, body, self._get_func_annotations(func))
        else:
            spec = FunctionParser.parse(func, *args, **kwargs)

        if module_code:
            spec.module_code = module_code

        spec = self._dep_resolver.resolve(spec, deps)

        code = self.generate_code(spec)

        final_code = prefix + code + suffix

        if output_file:
            self._write_code_to_file(final_code, output_file, write_mode)
            return output_file

        return final_code

    @staticmethod
    def _get_func_annotations(func: Callable) -> Dict[str, type]:
        """获取函数的类型注解字典。

        优先使用 typing.get_type_hints，失败时回退到 __annotations__。

        Args:
            func: 要获取注解的函数对象。

        Returns:
            Dict[str, type]: 类型注解字典。
        """
        try:
            return get_type_hints(func)
        except Exception:
            return func.__annotations__

    @staticmethod
    def _write_code_to_file(code: str, file_path: str, write_mode: str = 'overwrite') -> str:
        """将代码写入文件，支持多种写入模式。

        Args:
            code: 要写入的代码字符串。
            file_path: 输出文件路径。
            write_mode: 写入模式，可选值：
                - 'overwrite': 覆盖整个文件
                - 'append': 追加到文件末尾
                - 'insert:NN': 插入到第 NN 行之后（行号从 1 开始）
                - 'replace:MM-NN': 替换第 MM 到 NN 行（包含两端）

        Returns:
            str: 写入后的文件路径。

        Raises:
            ValueError: 写入模式未知时抛出。
        """
        os.makedirs(os.path.dirname(os.path.abspath(file_path)) or '.', exist_ok=True)

        if write_mode == 'overwrite':
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)
            return file_path

        if write_mode == 'append':
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(code)
            return file_path

        if write_mode.startswith('insert:'):
            line_num = int(write_mode.split(':')[1])
            existing_lines = []
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_lines = f.readlines()

            insert_pos = min(line_num, len(existing_lines))
            code_lines = code.splitlines(keepends=True)
            if code_lines and not code_lines[-1].endswith('\n'):
                code_lines[-1] += '\n'
            new_lines = existing_lines[:insert_pos] + code_lines + existing_lines[insert_pos:]

            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            return file_path

        if write_mode.startswith('replace:'):
            range_str = write_mode.split(':')[1]
            start_str, end_str = range_str.split('-')
            start_line = int(start_str)
            end_line = int(end_str)

            existing_lines = []
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_lines = f.readlines()

            start_idx = max(0, start_line - 1)
            end_idx = min(end_line, len(existing_lines))

            code_lines = code.splitlines(keepends=True)
            if code_lines and not code_lines[-1].endswith('\n'):
                code_lines[-1] += '\n'
            new_lines = existing_lines[:start_idx] + code_lines + existing_lines[end_idx:]

            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            return file_path

        raise ValueError(f"Unknown write_mode: {write_mode}")

    def _compile_with_cache(self, code: str, func_name: str,
                            cache_dir: Optional[str] = None) -> str:
        """带缓存的编译。

        先检查缓存是否存在，存在则直接返回缓存路径，
        否则编译并保存到缓存。

        Args:
            code: 源代码字符串。
            func_name: 函数名称。
            cache_dir: 缓存目录，为 None 时使用默认目录。

        Returns:
            str: 编译后的库文件路径。
        """
        cached = self.check_cache(code, func_name, cache_dir)
        if cached:
            return cached

        lib_path = self.compile_code(code, func_name, cache_dir)

        return self.save_to_cache(code, func_name, lib_path, cache_dir)

    def _compile_force(self, code: str, func_name: str,
                        cache_dir: Optional[str] = None) -> str:
        """强制编译（忽略缓存）。

        忽略缓存直接编译，并保存到缓存。

        Args:
            code: 源代码字符串。
            func_name: 函数名称。
            cache_dir: 缓存目录，为 None 时使用默认目录。

        Returns:
            str: 编译后的库文件路径。
        """
        lib_path = self.compile_code(code, func_name, cache_dir)
        return self.save_to_cache(code, func_name, lib_path, cache_dir)

    # ------------------------------------------------------------------
    # 项目模式相关方法
    # ------------------------------------------------------------------

    def _get_project_hash(self, project_dir: str) -> str:
        """计算项目所有源文件的内容哈希。

        遍历项目目录下所有该语言的源文件，按文件名排序后
        依次读取内容计算 MD5 哈希，用于缓存键的生成。

        Args:
            project_dir: 项目根目录路径。

        Returns:
            str: 项目源文件内容的 MD5 哈希值。
        """
        hasher = hashlib.md5()
        if not os.path.isdir(project_dir):
            return hasher.hexdigest()

        src_files = []
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f.endswith(self.file_ext):
                    src_files.append(os.path.join(root, f))

        src_files.sort()

        for filepath in src_files:
            try:
                with open(filepath, 'rb') as f:
                    hasher.update(f.read())
            except Exception:
                pass

        return hasher.hexdigest()

    def _get_project_cache_key(self, project_dir: str, entry: str) -> str:
        """获取项目编译的缓存键。

        结合项目名称、入口函数名和源文件内容哈希生成唯一缓存键。

        Args:
            project_dir: 项目根目录路径。
            entry: 入口函数名。

        Returns:
            str: 项目缓存键字符串。
        """
        project_hash = self._get_project_hash(project_dir)
        project_name = os.path.basename(os.path.abspath(project_dir))
        return f'proj_{project_name}_{entry}_{project_hash}'

    def _check_project_cache(self, project_dir: str, entry: str,
                             cache_dir: str) -> Optional[str]:
        """检查项目编译缓存是否存在。

        Args:
            project_dir: 项目根目录路径。
            entry: 入口函数名。
            cache_dir: 缓存目录路径。

        Returns:
            Optional[str]: 缓存的产物文件路径，不存在则返回 None。
        """
        cache_dir = self.get_cache_dir(cache_dir)
        cache_key = self._get_project_cache_key(project_dir, entry)

        if entry == 'main':
            ext = '.exe' if os.name == 'nt' else ''
            artifact_path = os.path.join(cache_dir, f'{cache_key}{ext}')
        else:
            artifact_path = os.path.join(cache_dir, self.get_lib_filename(cache_key))

        if os.path.exists(artifact_path):
            return artifact_path
        return None

    def _save_project_cache(self, project_dir: str, entry: str,
                            artifact_path: str, cache_dir: Optional[str] = None) -> str:
        """保存项目编译产物到缓存目录。

        Args:
            project_dir: 项目根目录路径。
            entry: 入口函数名。
            artifact_path: 编译产物文件路径。
            cache_dir: 缓存目录，为 None 时使用默认目录。

        Returns:
            str: 缓存中的产物文件路径。
        """
        import shutil
        cache_dir = self.get_cache_dir(cache_dir)
        cache_key = self._get_project_cache_key(project_dir, entry)

        if entry == 'main':
            ext = '.exe' if os.name == 'nt' else ''
            cached_path = os.path.join(cache_dir, f'{cache_key}{ext}')
        else:
            cached_path = os.path.join(cache_dir, self.get_lib_filename(cache_key))

        try:
            shutil.copy2(artifact_path, cached_path)
        except Exception:
            pass

        return cached_path

    def _compile_project_with_cache(self, project_dir: str, entry: str,
                                    cache_dir: Optional[str] = None) -> str:
        """带缓存的项目编译。

        先检查缓存是否存在，存在则直接返回缓存路径，
        否则编译项目并保存到缓存。

        Args:
            project_dir: 项目根目录路径。
            entry: 入口函数名。
            cache_dir: 缓存目录，为 None 时使用默认目录。

        Returns:
            str: 编译产物文件路径。
        """
        cached = self._check_project_cache(project_dir, entry, cache_dir)
        if cached:
            return cached

        artifact_path = self.compile_project(project_dir, entry, cache_dir)

        return self._save_project_cache(project_dir, entry, artifact_path, cache_dir)

    def _compile_project_force(self, project_dir: str, entry: str,
                                cache_dir: Optional[str] = None) -> str:
        """强制编译项目（忽略缓存）。

        忽略缓存直接编译项目，并保存到缓存。

        Args:
            project_dir: 项目根目录路径。
            entry: 入口函数名。
            cache_dir: 缓存目录，为 None 时使用默认目录。

        Returns:
            str: 编译产物文件路径。
        """
        artifact_path = self.compile_project(project_dir, entry, cache_dir)
        return self._save_project_cache(project_dir, entry, artifact_path, cache_dir)

    def _run_project_sync(self, func: Callable, args: tuple, kwargs: dict,
                          project_dir: str, entry: str,
                          fallback: Optional[Callable], cache_dir: Optional[str],
                          ret_type: Optional[type], mode: str = 'NORMAL') -> Any:
        """同步执行项目模式。

        编译项目目录并运行入口函数或可执行文件。

        Args:
            func: 被装饰的 Python 函数。
            args: 位置参数元组。
            kwargs: 关键字参数字典。
            project_dir: 项目根目录路径。
            entry: 入口函数名。
            fallback: 回退函数。
            cache_dir: 编译缓存目录。
            ret_type: 返回值类型（仅用于库调用模式）。
            mode: 运行模式（NORMAL/DEBUG/FORCE/ONLY_RUN/ONLY_CODE）。

        Returns:
            Any: 执行结果。入口为 'main' 时返回 (returncode, stdout, stderr) 元组，
                 否则返回函数调用结果。

        Raises:
            RuntimeError: 编译器不可用且无回退函数时抛出。
            Exception: 编译或执行异常且无回退函数时重新抛出。
        """
        if not self.compiler_available():
            if fallback:
                return fallback(*args, **kwargs)
            raise RuntimeError(
                f"{self.name} compiler not available "
                f"and no fallback provided for project '{project_dir}'"
            )

        try:
            force_recompile = mode in ('DEBUG', 'FORCE')
            if force_recompile:
                artifact_path = self._compile_project_force(
                    project_dir, entry, cache_dir
                )
            else:
                artifact_path = self._compile_project_with_cache(
                    project_dir, entry, cache_dir
                )

            if mode == 'FORCE':
                return artifact_path

            if entry == 'main':
                return self._run_executable(artifact_path, args)
            else:
                return self.call_func(artifact_path, entry, args, ret_type)

        except Exception:
            if fallback:
                return fallback(*args, **kwargs)
            raise

    async def _run_project_async(self, func: Callable, args: tuple, kwargs: dict,
                                 project_dir: str, entry: str,
                                 fallback: Optional[Callable], cache_dir: Optional[str],
                                 ret_type: Optional[type], mode: str = 'NORMAL') -> Any:
        """异步执行项目模式。

        通过线程池同步执行项目编译和运行。

        Args:
            func: 被装饰的 Python 函数。
            args: 位置参数元组。
            kwargs: 关键字参数字典。
            project_dir: 项目根目录路径。
            entry: 入口函数名。
            fallback: 回退函数。
            cache_dir: 编译缓存目录。
            ret_type: 返回值类型。
            mode: 运行模式。

        Returns:
            Any: 执行结果。
        """
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=4)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._run_project_sync(
                func, args, kwargs, project_dir, entry,
                fallback, cache_dir, ret_type, mode
            )
        )

    def _run_executable(self, exe_path: str, args: tuple) -> tuple:
        """运行可执行文件并返回执行结果。

        Args:
            exe_path: 可执行文件路径。
            args: 传递给可执行文件的命令行参数元组。

        Returns:
            tuple: 三元组 (returncode, stdout, stderr)，分别为
                退出码、标准输出、标准错误输出。
        """
        import subprocess
        result = subprocess.run(
            [exe_path] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True
        )
        return (result.returncode, result.stdout, result.stderr)


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    'FunctionSpec',
    'CompileResult',
    'FunctionParser',
    'DepResolver',
    'LangBridge',
]
