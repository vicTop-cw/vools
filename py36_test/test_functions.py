"""
测试用函数
放在单独的模块中以确保多进程可以正确导入
"""

import time

try:
    from vools.task import task
except ImportError:
    def task(func=None, db_path="tasks.db"):
        def decorator(f):
            return f
        if func:
            return func
        return decorator


def add(a: int, b: int) -> int:
    """加法函数"""
    time.sleep(0.1)
    return a + b


def multiply(x: int, y: int) -> int:
    """乘法函数"""
    time.sleep(0.1)
    return x * y


def sometimes_fails(should_fail: bool = False) -> str:
    """有时会失败的函数"""
    if should_fail:
        raise ValueError("Intentional failure")
    return "success"


def decorator_test_func(a: int, b: int) -> int:
    """用于测试装饰器的函数"""
    time.sleep(0.1)
    return a + b


@task
def decorated_add(a: int, b: int) -> int:
    """被装饰器装饰的加法函数"""
    time.sleep(0.1)
    return a + b
