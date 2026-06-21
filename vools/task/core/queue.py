"""
任务队列核心逻辑
"""

__all__ = ['TaskQueue']

import pickle
import base64
import time
from typing import Any, Callable, Optional, List, Set, Dict
from functools import partial

from .models import Task, TaskStatus, DagValidationError
from .storage import TaskStorage


class TaskQueue:
    """任务队列管理器"""

    def __init__(self, db_path: str = "tasks.db"):
        self.storage = TaskStorage(db_path)
        self._func_registry = {}

    def __getstate__(self):
        return {'storage': self.storage, '_func_registry': self._func_registry}
    def __setstate__(self, state):
        self.storage = state['storage']
        self._func_registry = state['_func_registry']

    def submit(self, func: Callable, *args, **kwargs) -> int:
        """
        提交任务

        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数，支持特殊参数:
                - priority: 任务优先级
                - max_retries: 最大重试次数

        Returns:
            任务ID
        """
        # 提取特殊参数
        priority = kwargs.pop('priority', 0)
        max_retries = kwargs.pop('max_retries', 3)
        depends_on: Set[int] = kwargs.pop('depends_on', None) or set()

        # 序列化函数
        func_data = self._serialize_func(func)

        # 创建任务
        task = Task(
            task_name=func.__name__,
            task_func=func_data,
            args=list(args),
            kwargs=kwargs,
            status=TaskStatus.PENDING,
            priority=priority,
            max_retries=max_retries,
            dependencies=depends_on,
        )

        # DAG依赖校验
        if depends_on:
            self._validate_dag(task)

        return self.storage.insert_task(task)

    def get_task(self, task_id: int) -> Optional[Task]:
        """获取任务详情"""
        return self.storage.get_task(task_id)

    def get_task_status(self, task_id: int) -> Optional[TaskStatus]:
        """获取任务状态"""
        task = self.get_task(task_id)
        return task.status if task else None

    def get_result(self, task_id: int, timeout: Optional[float] = None) -> Any:
        """
        获取任务结果（阻塞等待）

        Args:
            task_id: 任务ID
            timeout: 超时时间（秒），None表示无限等待

        Returns:
            任务执行结果

        Raises:
            Exception: 任务执行失败时抛出异常
            TimeoutError: 超时时抛出
        """
        start_time = time.time()
        while True:
            task = self.get_task(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")

            if task.status == TaskStatus.SUCCESS:
                return task.result
            elif task.status == TaskStatus.FAILED:
                raise Exception(f"Task failed: {task.error_message}")
            elif task.status == TaskStatus.CANCEL:
                raise Exception(f"Task cancelled")

            if timeout is not None and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Task {task_id} timed out")

            time.sleep(0.1)

    def wait_for_completion(self, task_id: int, timeout: Optional[float] = None) -> bool:
        """
        等待任务完成（不抛出异常）

        Returns:
            True表示成功，False表示失败或取消
        """
        try:
            self.get_result(task_id, timeout)
            return True
        except Exception:
            return False

    def cancel_task(self, task_id: int) -> bool:
        """取消任务"""
        return self.storage.cancel_task(task_id)

    def retry_task(self, task_id: int) -> bool:
        """重试失败任务"""
        return self.storage.retry_task(task_id)

    def get_pending_tasks(self) -> List[Task]:
        """获取所有待处理任务"""
        return self.storage.get_tasks_by_status(TaskStatus.PENDING)

    def get_failed_tasks(self) -> List[Task]:
        """获取所有失败任务"""
        return self.storage.get_tasks_by_status(TaskStatus.FAILED)

    def cleanup_old_tasks(self, days: int = 7) -> int:
        """清理旧任务"""
        return self.storage.cleanup_old_tasks(days)

    def _serialize_func(self, func: Callable) -> str:
        """序列化函数"""
        # 获取原始函数（处理装饰器包装的情况）
        func_to_serialize = getattr(func, '__wrapped__', func)
        
        # 优先使用函数路径方式，这样可以正确处理装饰器
        try:
            return f"{func_to_serialize.__module__}:{func_to_serialize.__name__}"
        except Exception as e:
            pass
        
        # 如果函数在 __main__ 模块中，尝试使用 pickle
        if func_to_serialize.__module__ == '__main__':
            try:
                pickle_data = pickle.dumps(func_to_serialize)
                return base64.b64encode(pickle_data).decode('utf-8')
            except Exception as e:
                raise ValueError(f"Cannot pickle function in __main__: {e}")
        
        try:
            pickle_data = pickle.dumps(func_to_serialize)
            return base64.b64encode(pickle_data).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Cannot serialize function: {e}")

    def _deserialize_func(self, func_data: str) -> Callable:
        """反序列化函数"""
        if ':' in func_data and not func_data.startswith('g'):
            # 函数路径格式
            module_path, func_name = func_data.split(':', 1)
            import importlib
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
            # 如果函数被装饰器包装，获取原始函数
            return getattr(func, '__wrapped__', func)
        else:
            # pickle格式
            pickle_data = base64.b64decode(func_data.encode('utf-8'))
            return pickle.loads(pickle_data)

    def execute_task(self, task: Task) -> Any:
        """
        执行单个任务（内部使用）

        Returns:
            任务执行结果
        """
        func = self._deserialize_func(task.task_func)
        return func(*task.args, **task.kwargs)


    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
    def _validate_dag(self, task: Task) -> None:
        """
        DAG依赖校验：检查依赖ID是否存在，以及是否存在循环依赖

        Args:
            task: 待校验的任务

        Raises:
            DagValidationError: 依赖校验失败
        """
        visited: Set[int] = set()

        def dfs(current_id: int, chain: Set[int]) -> None:
            """DFS检查循环依赖"""
            if current_id in chain:
                raise DagValidationError(
                    f"Circular dependency detected: task {task.id} "
                    f"depends on task {current_id} which is already "
                    f"in the dependency chain {chain}"
                )

            if current_id in visited:
                return
            visited.add(current_id)

            # 检查依赖任务是否存在
            dep_task = self.get_task(current_id)
            if dep_task is None:
                raise DagValidationError(
                    f"Dependency task {current_id} not found"
                )

            # 递归检查上游依赖
            if dep_task.dependencies:
                for dep_id in dep_task.dependencies:
                    dfs(dep_id, chain | {current_id})

        for dep_id in task.dependencies:
            dfs(dep_id, {task.id})
