"""
vools.bridge.haskell - Haskell 语言桥接模块

提供 Haskell 动态编译与跨语言桥接能力，对齐 vools.bridge.go 的 API 形态。

设计目标：免序列化（serialization-free）交互
- 整数、浮点、布尔、字符串、列表等基础类型直接映射为 Haskell 类型
- 通过 GHC 编译为可执行文件，stdin 传参，stdout 返回 show 结果

使用示例::

    from vools.bridge.haskell import haskell, haskell_compiler_available

    if haskell_compiler_available():
        @haskell
        def add(a: int, b: int) -> int:
            return "a + b"

        print(add(2, 3))   # -> 5

        @haskell(async_mode=True)
        def fib(n: int) -> int:
            return '''
            if n <= 1 then 1
            else fib(n-1) + fib(n-2)
            '''

        import asyncio
        print(asyncio.run(fib(10)))   # -> 89

参数（与 LangBridge 基类对齐）：
    mode: 运行模式
        DEBUG: 强制重编译并执行
        FORCE: 强制重编译但不执行
        NORMAL: 命中缓存跳过编译；未命中则编译
        ONLY_RUN: 只在有缓存时执行；没有则报错
        ONLY_CODE: 只生成 Haskell 源码，不编译
    cache_dir: 编译缓存目录，None 则使用系统临时目录
    ret_type: 返回类型 ('Int', 'Double', 'String', 'Bool')，None 时从注解推断
    async_mode: 是否返回 HaskellFuture（默认 False）
    deps: 依赖函数列表
    module_code: 模块级代码

前置条件:
- 安装 GHC (>= 9.0)，并将 ghc 加入 PATH
- Windows 推荐: D:\\GHC
- 参考: https://www.haskell.org/ghc/
"""

from .compiler import (
    haskell,
    haskell_compiler_available,
    is_haskell_available,
    compile_and_run,
    HaskellFuture,
    PY_TO_HASKELL_TYPE,
    HASKELL_TO_CTYPES,
    get_haskell_type,
    infer_haskell_argtypes,
    is_array_type,
    get_ctype_for,
    HaskellBridge,
    _haskell_bridge,
    _compile_haskell_code,
    _call_haskell_function,
    _generate_haskell_source,
    _HASKELL_CACHE_DIR,
)

__all__ = [
    # 装饰器
    'haskell',
    # 编译器检测
    'haskell_compiler_available',
    'is_haskell_available',
    # 便捷入口
    'compile_and_run',
    # 异步 Future
    'HaskellFuture',
    # 类型映射
    'PY_TO_HASKELL_TYPE',
    'HASKELL_TO_CTYPES',
    'get_haskell_type',
    'infer_haskell_argtypes',
    'is_array_type',
    'get_ctype_for',
    # Bridge 类
    'HaskellBridge',
    '_haskell_bridge',
    # 内部（暴露用于测试 / 高级用法）
    '_compile_haskell_code',
    '_call_haskell_function',
    '_generate_haskell_source',
    '_HASKELL_CACHE_DIR',
]
