"""
@task装饰器 - 方便地提交任务
"""

__all__ = ['task', 'TaskDecorator']

import functools
from typing import Callable, Any, Optional

from ..core.queue import TaskQueue


class TaskDecorator:
    """任务装饰器"""

    def __init__(self, db_path: str = "tasks.db"):
        self.db_path = db_path

    def __call__(self, func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> int:
            """
            提交任务到队列

            支持的关键字参数:
                - priority: 任务优先级
                - max_retries: 最大重试次数
                - queue: 自定义TaskQueue实例
            """
            queue = kwargs.pop('queue', None) or TaskQueue(self.db_path)
            return queue.submit(func, *args, **kwargs)

        # 添加直接执行函数的能力
        wrapper.direct = func

        # 添加属性
        wrapper.func = func
        wrapper.db_path = self.db_path

        return wrapper


def task(func: Optional[Callable] = None, db_path: str = "tasks.db") -> Any:
    """
    任务装饰器

    使用方式:
        @task
        def my_func(x):
            return x * 2

        # 提交任务
        task_id = my_func(10)

        # 直接执行（不提交）
        result = my_func.direct(10)

        # 指定队列
        from vools.task import TaskQueue
        queue = TaskQueue()
        task_id = my_func(10, queue=queue)
    """
    decorator = TaskDecorator(db_path)
    if func is None:
        return decorator
    return decorator(func)
