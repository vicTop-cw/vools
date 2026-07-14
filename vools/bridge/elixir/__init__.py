"""
vools.bridge.elixir - Elixir 语言桥接模块

提供 Elixir 动态编译与跨语言桥接能力，对齐 vools.bridge.go 的 API 形态。

设计目标：免序列化（serialization-free）交互
- 列表参数走 Elixir 列表字面量
- 字符串参数走 binary（UTF-8）
- 通过 elixirc 编译为 .beam，elixir 执行

使用示例::

    from vools.bridge.elixir import elixir, elixir_compiler_available

    if elixir_compiler_available():
        @elixir
        def add(a: int, b: int) -> int:
            return "a + b"

        print(add(2, 3))   # -> 5

        @elixir(async_mode=True)
        def fib(n: int) -> int:
            return '''
            cond do
              n <= 1 -> 1
              true -> fib(n-1) + fib(n-2)
            end
            '''

        import asyncio
        print(asyncio.run(fib(10)))   # -> 89

参数（与 LangBridge 基类对齐）：
    mode: 运行模式
        DEBUG: 强制重编译并执行
        FORCE: 强制重编译但不执行
        NORMAL: 命中缓存跳过编译；未命中则编译
        ONLY_RUN: 只在有缓存时执行；没有则报错
        ONLY_CODE: 只生成 Elixir 源码，不编译
    cache_dir: 编译缓存目录，None 则使用系统临时目录
    ret_type: 返回类型 ('integer', 'float', 'string', 'bool')，None 时从注解推断
    async_mode: 是否返回 ElixirFuture（默认 False）
    deps: 依赖函数列表
    module_code: 模块级代码

前置条件:
- 安装 Elixir (>= 1.14)，并将 elixir/elixirc 加入 PATH
- Windows 推荐: D:\\Elixir
- 参考: https://elixir-lang.org/
"""

from .compiler import (
    elixir,
    elixir_compiler_available,
    is_elixir_available,
    compile_and_run,
    ElixirFuture,
    PY_TO_ELIXIR_TYPE,
    ELIXIR_TO_CTYPES,
    get_elixir_type,
    infer_elixir_argtypes,
    is_array_type,
    get_ctype_for,
    ElixirBridge,
    _elixir_bridge,
    _compile_elixir_code,
    _call_elixir_function,
    _generate_elixir_source,
    _ELIXIR_CACHE_DIR,
)

__all__ = [
    # 装饰器
    'elixir',
    # 编译器检测
    'elixir_compiler_available',
    'is_elixir_available',
    # 便捷入口
    'compile_and_run',
    # 异步 Future
    'ElixirFuture',
    # 类型映射
    'PY_TO_ELIXIR_TYPE',
    'ELIXIR_TO_CTYPES',
    'get_elixir_type',
    'infer_elixir_argtypes',
    'is_array_type',
    'get_ctype_for',
    # Bridge 类
    'ElixirBridge',
    '_elixir_bridge',
    # 内部（暴露用于测试 / 高级用法）
    '_compile_elixir_code',
    '_call_elixir_function',
    '_generate_elixir_source',
    '_ELIXIR_CACHE_DIR',
]
