"""
@task装饰器 - 方便地提交任务

功能特性:
- 支持单个任务提交
- 支持批量任务提交（通过params生成器）
- 支持自定义队列
- 支持优先级和重试配置
"""

__all__ = ['task', 'TaskDecorator', 'batch_execute']

import functools
from typing import Callable, Any, Optional, Generator, Dict, List

from ..core.queue import TaskQueue


class TaskDecorator:
    """任务装饰器类"""

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
                - params: 生成器函数，用于批量提交任务

            Returns:
                如果是单任务提交，返回任务ID(int)
                如果是批量提交(params)，返回任务ID列表(List[int])
            """
            # 检查是否有params参数（批量提交模式）
            params_gen = kwargs.pop('params', None)
            
            if params_gen is not None:
                # 批量提交模式
                queue = kwargs.pop('queue', None) or TaskQueue(self.db_path)
                task_ids = []
                
                # 遍历生成器生成的参数
                for param_dict in params_gen():
                    # 合并基础参数和生成的参数
                    combined_kwargs = kwargs.copy()
                    
                    # 从param_dict中提取args和kwargs
                    gen_args = param_dict.get('args', ())
                    gen_kwargs = param_dict.get('kwargs', {})
                    
                    # 合并参数
                    full_args = args + gen_args
                    combined_kwargs.update(gen_kwargs)
                    
                    # 提交任务
                    task_id = queue.submit(func, *full_args, **combined_kwargs)
                    task_ids.append(task_id)
                
                return task_ids
            
            # 单任务提交模式
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

    1. 基本用法 - 单任务提交
        @task
        def add(a, b):
            return a + b

        # 提交任务
        task_id = add(1, 2)

        # 直接执行（不提交）
        result = add.direct(10)

        # 指定队列
        from vools.task import TaskQueue
        queue = TaskQueue()
        task_id = add(10, queue=queue)

    2. 批量任务提交 - 使用params生成器
        @task
        def process_item(item_id):
            return item_id * 2

        # 定义生成器函数
        def gen_params():
            for i in range(10):
                yield {'args': (i,)}  # 必须包含args或kwargs键

        # 批量提交任务
        task_ids = process_item(params=gen_params)
        # 返回: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    3. 批量提交带优先级和重试配置
        def gen_items():
            for i in range(5):
                yield {
                    'args': (i,),
                    'kwargs': {'priority': i}  # 每个任务可以有不同的优先级
                }

        task_ids = process_item(params=gen_items, max_retries=5)
        # 所有任务共享max_retries=5，但每个任务有自己的priority

    Args:
        func: 要装饰的函数
        db_path: SQLite数据库路径（默认'tasks.db'）

    Returns:
        装饰后的函数或装饰器本身
    """
    decorator = TaskDecorator(db_path)
    if func is None:
        return decorator
    return decorator(func)


def batch_execute(func: Optional[Callable] = None, 
                  task_args: List[tuple] = None, 
                  task_kwargs: List[Dict[str, Any]] = None,
                  db_path: str = "tasks.db",
                  priority: int = 0,
                  max_retries: int = 3,
                  queue: TaskQueue = None,
                  is_worker: bool = False,
                  worker_nums: int = 1) -> Any:
    """
    批量执行装饰器 - 对同一个函数使用不同参数批量执行
    
    功能特性:
        - 支持两种使用方式：装饰器参数模式和调用时参数模式
        - 支持批量执行函数，每次使用不同的参数
        - 可以单独提供位置参数列表或关键字参数列表
        - 如果同时提供，两者长度必须相同
        - 支持任务队列模式（is_worker=True）和直接执行模式（默认）
        - 支持多进程并行执行（worker_nums > 1）
    
    使用方式:
    
    方式1: 装饰器参数模式
        @batch_execute(task_args=[(1,), (2,), (3,)])
        def do(value):
            return value * 2
        
        result = do()  # → [2, 4, 6]
    
    方式2: 调用时参数模式
        @batch_execute
        def do(value):
            return value * 2
        
        result = do(task_args=[(1,), (2,), (3,)])  # → [2, 4, 6]
    
    方式3: 任务队列模式
        @batch_execute(task_args=[(1,), (2,), (3,)], is_worker=True, db_path="tasks.db")
        def do(value):
            return value * 2
        
        task_ids = do()  # → [1, 2, 3]
    
    方式4: 多进程并行执行
        @batch_execute(task_args=[(1,), (2,), (3,)], worker_nums=3)
        def process(item):
            return item * 2
        
        result = process()  # → [2, 4, 6]（并行执行）
    
    Args:
        func: 要装饰的函数
        task_args: 位置参数列表，每个元素是一个tuple，表示一次调用的位置参数
        task_kwargs: 关键字参数列表，每个元素是一个dict，表示一次调用的关键字参数
        db_path: SQLite数据库路径（默认'tasks.db'），仅在is_worker=True时生效
        priority: 任务优先级（默认0），仅在is_worker=True时生效
        max_retries: 最大重试次数（默认3），仅在is_worker=True时生效
        queue: 自定义TaskQueue实例，仅在is_worker=True时生效
        is_worker: 是否以工作进程模式运行（默认False），True时提交任务到队列
        worker_nums: 并行执行的进程/线程数（默认1），仅在is_worker=False时生效
    
    Returns:
        如果func为None，返回装饰器；否则返回装饰后的函数
        
        调用装饰后的函数时:
            - is_worker=False: 返回执行结果列表 [result1, result2, ...]
            - is_worker=True: 返回任务ID列表 [task_id1, task_id2, ...]
    
    Raises:
        ValueError: 同时提供task_args和task_kwargs但长度不一致
        ValueError: 既未提供task_args也未提供task_kwargs
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> List[Any]:
            # 提取调用时传入的 task_args 和 task_kwargs
            call_task_args = kwargs.pop('task_args', None)
            call_task_kwargs = kwargs.pop('task_kwargs', None)
            
            # 确定使用装饰器参数还是调用时参数
            # 优先使用调用时参数，如果没有则使用装饰器参数
            use_args = call_task_args if call_task_args is not None else task_args
            use_kwargs = call_task_kwargs if call_task_kwargs is not None else task_kwargs
            
            # 确定执行次数和参数来源
            if use_args is not None and use_kwargs is not None:
                if len(use_args) != len(use_kwargs):
                    raise ValueError(
                        f"task_args and task_kwargs must have same length. "
                        f"Got {len(use_args)} and {len(use_kwargs)}"
                    )
                iterations = len(use_args)
            elif use_args is not None:
                iterations = len(use_args)
            elif use_kwargs is not None:
                iterations = len(use_kwargs)
            else:
                raise ValueError("Either task_args or task_kwargs must be provided")
            
            # 工作进程模式：提交任务到队列
            if is_worker:
                task_queue = queue or TaskQueue(db_path)
                task_ids = []
                
                for i in range(iterations):
                    current_args = use_args[i] if use_args else ()
                    current_kwargs = use_kwargs[i] if use_kwargs else {}
                    
                    # 合并参数
                    full_args = args + current_args
                    full_kwargs = {**current_kwargs, **kwargs}
                    
                    # 添加优先级和重试配置
                    full_kwargs.setdefault('priority', priority)
                    full_kwargs.setdefault('max_retries', max_retries)
                    
                    # 提交任务
                    task_id = task_queue.submit(fn, *full_args, **full_kwargs)
                    task_ids.append(task_id)
                
                return task_ids
            
            # 直接执行模式：直接执行函数
            if worker_nums > 1:
                # 多线程并行执行（使用线程池避免序列化问题）
                from concurrent.futures import ThreadPoolExecutor
                
                def execute_task(i):
                    current_args = use_args[i] if use_args else ()
                    current_kwargs = use_kwargs[i] if use_kwargs else {}
                    full_args = args + current_args
                    full_kwargs = {**current_kwargs, **kwargs}
                    return fn(*full_args, **full_kwargs)
                
                with ThreadPoolExecutor(max_workers=worker_nums) as executor:
                    results = list(executor.map(execute_task, range(iterations)))
                return results
            else:
                # 单进程顺序执行
                results = []
                for i in range(iterations):
                    current_args = use_args[i] if use_args else ()
                    current_kwargs = use_kwargs[i] if use_kwargs else {}
                    
                    full_args = args + current_args
                    full_kwargs = {**current_kwargs, **kwargs}
                    
                    result = fn(*full_args, **full_kwargs)
                    results.append(result)
                
                return results
        
        # 保留原始函数引用
        wrapper.direct = fn
        return wrapper
    
    if func is None:
        return decorator
    return decorator(func)


