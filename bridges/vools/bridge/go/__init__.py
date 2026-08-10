"""
vools.bridge.go - Go 语言桥接模块

提供 Go 动态编译与跨语言桥接能力，对齐 vools.bridge.mojo / freebasic 的 API 形态。

设计目标：免序列化（serialization-free）交互
- 列表/切片参数走 unsafe.Pointer + 长度（C.longlong），不走 CSV/JSON
- 字符串参数走 *C.char（c_char_p），cgo 端由 //export 包装层做 C.CString/C.GoString 转换
- 通过 pygo 风格的 cgo + ctypes 模式：编译为 c-shared，ctypes 加载

异步 / 并行 / 并发：
- async_mode=True: 装饰器返回 GoFuture（薄包装 ThreadPoolExecutor.Future），
  既可 .result() 阻塞取结果，也可 await（实现 __await__）
- 并行：ctypes 在 native 调用前后释放 GIL，多个 ctypes 调用天然并行；
  配合 asyncio.gather 即可在事件循环中并发调度 N 个 Go 函数调用
- 并发：共享 _executor (ThreadPoolExecutor, max_workers=4)，
  多次提交 GoFuture 可真正并行执行

使用示例::

    from vools.bridge.go import go, compile_and_run, go_compiler_available

    if go_compiler_available():
        @go
        def add(a: int, b: int) -> int:
            return "return int64(a) + int64(b)"

        print(add(2, 3))   # -> 5

        @go(async_mode=True)
        def fib(n: int) -> int:
            return '''
            if int64(n) <= 1 { return 1 }
            return int64(fib(n-1) + fib(n-2))
            '''

        import asyncio
        print(asyncio.run(fib(10)))   # -> 89

        # 并发调用 20 次
        async def many():
            return await asyncio.gather(*[add(i, i) for i in range(20)])
        print(asyncio.run(many()))   # -> [0, 2, 4, ..., 38]

参数（与 LangBridge 基类对齐，扩展参数以 * 标注）：
    * mode: 运行模式
        DEBUG: 强制重编译并执行
        FORCE: 强制重编译但不执行
        NORMAL: 命中缓存跳过编译；未命中则编译
        ONLY_RUN: 只在有缓存时执行；没有则报错
        ONLY_CODE: 只生成 Go 源码，不编译 .so/.dll
    cache_dir: 编译缓存目录，None 则使用系统临时目录
    ret_type: 返回类型 ('int64', 'float64', 'string', 'bool')，None 时从注解推断
    async_mode: 是否返回 GoFuture（默认 False）
    auto_signature: 是否自动根据参数类型生成签名（默认 True）
    deps: 依赖函数列表（LangBridge 兼容）
    module_code: 模块级代码（LangBridge 兼容）
    fallback: 回退函数（LangBridge 兼容）
    only_code: 是否仅生成代码（LangBridge 兼容）
    output_file: 输出文件路径（LangBridge 兼容）

前置条件:
- 安装 Go（>= 1.18），并将 go 加入 PATH
- 参考: https://go.dev/
"""

from .compiler import (
    # 装饰器（复用基类 decorator）
    go,
    # 编译器检测
    go_compiler_available,
    is_go_available,
    # 便捷入口
    compile_and_run,
    # 异步 Future
    GoFuture,
    # 类型映射
    PY_TO_GO_TYPE,
    GO_TO_CTYPES,
    get_go_type,
    infer_go_argtypes,
    is_array_type,
    get_ctype_for,
    # Bridge 类
    GoBridge,
    # 全局实例
    _go_bridge,
    # 内部（暴露用于测试 / 高级用法）
    _compile_go_code,
    _call_go_function,
    _generate_go_source,
    _GO_CACHE_DIR,
)

__all__ = [
    # 装饰器
    'go',
    # 编译器检测
    'go_compiler_available',
    'is_go_available',
    # 便捷入口
    'compile_and_run',
    # 异步 Future
    'GoFuture',
    # 类型映射
    'PY_TO_GO_TYPE',
    'GO_TO_CTYPES',
    'get_go_type',
    'infer_go_argtypes',
    'is_array_type',
    'get_ctype_for',
    # Bridge 类
    'GoBridge',
    # 内部（暴露用于测试 / 高级用法）
    '_compile_go_code',
    '_call_go_function',
    '_generate_go_source',
    '_GO_CACHE_DIR',
]
