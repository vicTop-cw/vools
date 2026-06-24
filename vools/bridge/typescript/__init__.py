"""
vools.bridge.typescript - TypeScript/JavaScript 语言桥接模块

通过 Node.js 子进程执行 TS/JS 代码，使用 JSON 序列化进行数据交换。
适合 I/O 密集型任务（Web、Node.js 生态调用）。

设计要点：
- 通过 `node` 启动子进程执行编译后的 JS
- TypeScript 编译：`tsc <source> --outDir <dir>` 编译为 JS
- 数据交换：JSON over stdin/stdout
- 异步支持：基于 Promise 的 async_mode
- 缓存机制：基于代码 MD5 哈希的缓存

使用示例::

    from vools.bridge.typescript import ts, ts_compiler_available

    if ts_compiler_available():
        @ts
        def greet(name: str) -> str:
            return '''
            return `Hello, ${name}!`;
            '''

        print(greet("World"))  # -> Hello, World!

        @ts(async_mode=True)
        def fetch_data(url: str) -> dict:
            return '''
            const response = await fetch(url);
            return await response.json();
            '''

        import asyncio
        result = asyncio.run(fetch_data("https://api.example.com/data"))
"""

from .compiler import (
    # 装饰器
    ts,
    typescript,
    # 编译器检测
    ts_compiler_available,
    is_typescript_available,
    is_node_available,
    get_node_version,
    get_tsc_version,
    # 便捷入口
    compile_and_run,
    # 异步 Future
    TSFuture,
    # 类型映射
    PY_TO_TS_TYPE,
    TS_TO_PY_TYPE,
    get_ts_type,
    # Bridge 类
    TypeScriptBridge,
    # 全局实例
    _ts_bridge,
    # 内部
    _compile_ts_code,
    _call_ts_function,
    _generate_ts_source,
    _TS_CACHE_DIR,
)

__all__ = [
    # 装饰器
    'ts',
    'typescript',
    # 编译器检测
    'ts_compiler_available',
    'is_typescript_available',
    'is_node_available',
    'get_node_version',
    'get_tsc_version',
    # 便捷入口
    'compile_and_run',
    # 异步 Future
    'TSFuture',
    # 类型映射
    'PY_TO_TS_TYPE',
    'TS_TO_PY_TYPE',
    'get_ts_type',
    # Bridge 类
    'TypeScriptBridge',
    # 全局实例
    '_ts_bridge',
    # 内部
    '_compile_ts_code',
    '_call_ts_function',
    '_generate_ts_source',
    '_TS_CACHE_DIR',
]
