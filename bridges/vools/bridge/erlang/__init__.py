"""
vools.bridge.erlang - Erlang 语言桥接模块

提供 Erlang 动态编译与跨语言桥接能力，对齐 vools.bridge.go 的 API 形态。

设计目标：免序列化（serialization-free）交互
- 列表参数走 binary 数据 + 长度，或转换为 Erlang 列表字面量
- 字符串参数走 binary（UTF-8），Erlang 端直接处理
- 通过 erlc 编译为 .beam，erl 执行
- 复杂类型通过 ERL_NIF 编译为 C 共享库

使用示例::

    from vools.bridge.erlang import erlang, erlang_compiler_available

    if erlang_compiler_available():
        @erlang
        def add(a: int, b: int) -> int:
            return "A + B."

        print(add(2, 3))   # -> 5

        @erlang(async_mode=True)
        def fib(n: int) -> int:
            return '''
            if N =< 1 -> 1;
               true -> fib(N-1) + fib(N-2)
            end.
            '''

        import asyncio
        print(asyncio.run(fib(10)))   # -> 89

参数（与 LangBridge 基类对齐）：
    mode: 运行模式
        DEBUG: 强制重编译并执行
        FORCE: 强制重编译但不执行
        NORMAL: 命中缓存跳过编译；未命中则编译
        ONLY_RUN: 只在有缓存时执行；没有则报错
        ONLY_CODE: 只生成 Erlang 源码，不编译
    cache_dir: 编译缓存目录，None 则使用系统临时目录
    ret_type: 返回类型 ('integer', 'float', 'string', 'bool')，None 时从注解推断
    async_mode: 是否返回 ErlangFuture（默认 False）
    deps: 依赖函数列表
    module_code: 模块级代码

前置条件:
- 安装 Erlang (>= 25)，并将 erl/erlc 加入 PATH
- Windows 推荐: D:\\Erlang
- 参考: https://www.erlang.org/
"""

from .compiler import (
    erlang,
    erlang_compiler_available,
    is_erlang_available,
    compile_and_run,
    ErlangFuture,
    PY_TO_ERLANG_TYPE,
    ERLANG_TO_CTYPES,
    get_erlang_type,
    infer_erlang_argtypes,
    is_array_type,
    get_ctype_for,
    ErlangBridge,
    _erlang_bridge,
    _compile_erlang_code,
    _call_erlang_function,
    _generate_erlang_source,
    _ERLANG_CACHE_DIR,
)

__all__ = [
    # 装饰器
    'erlang',
    # 编译器检测
    'erlang_compiler_available',
    'is_erlang_available',
    # 便捷入口
    'compile_and_run',
    # 异步 Future
    'ErlangFuture',
    # 类型映射
    'PY_TO_ERLANG_TYPE',
    'ERLANG_TO_CTYPES',
    'get_erlang_type',
    'infer_erlang_argtypes',
    'is_array_type',
    'get_ctype_for',
    # Bridge 类
    'ErlangBridge',
    '_erlang_bridge',
    # 内部（暴露用于测试 / 高级用法）
    '_compile_erlang_code',
    '_call_erlang_function',
    '_generate_erlang_source',
    '_ERLANG_CACHE_DIR',
]
