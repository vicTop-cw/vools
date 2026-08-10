"""
vools.bridge.rust.decorator - Rust 动态编译装饰器

提供 @rust 装饰器，用于将 Python 函数转换为 Rust 代码并编译为 DLL。
支持同步和异步两种模式。
"""

from .compiler import _rust_bridge

rust = _rust_bridge.decorator


def rust_module(
    name: str = None,
    dependencies: dict = None,
    cache_dir: str = None
):
    """
    Rust 模块装饰器

    将一个类标记为 Rust 模块，类中的所有方法自动使用 Rust 实现。

    参数：
        name: 模块名称（可选）
        dependencies: Cargo 依赖字典（可选）
        cache_dir: 编译缓存目录（可选）

    用法：
        @rust_module(name='math_ops')
        class MathOps:
            def add(a: int, b: int) -> int:
                return "a + b"

            def mul(a: float, b: float) -> float:
                return "a * b"
    """

    def decorator(cls):
        # 为类中的每个方法应用 @rust 装饰器
        for method_name in dir(cls):
            if not method_name.startswith('_'):
                method = getattr(cls, method_name)
                if callable(method):
                    # 应用 @rust 装饰器
                    decorated_method = rust(
                        method,
                        cache_dir=cache_dir
                    )
                    setattr(cls, method_name, decorated_method)

        return cls

    return decorator