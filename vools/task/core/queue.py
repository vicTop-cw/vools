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
from ...core.base import VoolsBase


def _normalize_depends_on(value: Any) -> Set[int]:
    """校验并归一化 depends_on（BUG-431）。

    原实现 ``set(kwargs.pop('depends_on', None) or ())`` 对非法输入极不友好：

    * ``depends_on=999``  -> ``TypeError: 'int' object is not iterable``；
    * ``depends_on='abc'`` -> 被**逐字符**展开成 'a','b','c' 三个"任务ID"，
      报 ``DagValidationError: Dependency task b not found``，完全看不出原因；
    * ``depends_on=['x']`` -> 报 Dependency task x not found（误把字符串当 ID）。

    现要求：``None`` -> 空集；可迭代且元素为整数任务ID（bool 除外）。
    任务ID是否存在仍由既有 :meth:`TaskQueue._validate_dag` 负责。
    """
    if value is None:
        return set()
    if isinstance(value, (str, bytes)) or isinstance(value, int):
        raise TypeError(
            f"depends_on 需要可迭代的整数任务ID列表，收到 "
            f"{type(value).__name__}: {value!r}")
    try:
        deps = list(value)
    except TypeError:
        raise TypeError(
            f"depends_on 需要可迭代的整数任务ID列表，收到 "
            f"{type(value).__name__}: {value!r}")
    out: Set[int] = set()
    for dep in deps:
        if isinstance(dep, bool) or not isinstance(dep, int):
            raise TypeError(
                f"depends_on 的元素需要整数任务ID，收到 "
                f"{type(dep).__name__}: {dep!r}")
        out.add(dep)
    return out


class TaskQueue(VoolsBase):
    """任务队列管理器"""

    # 类属性：_func_registry 在所有实例间共享（同一进程内线程安全）
    _func_registry = {}

    def __init__(self, db_path: str = "tasks.db"):
        self.storage = TaskStorage(db_path)

    def __getstate__(self):
        return {'storage': self.storage}
    def __setstate__(self, state):
        self.storage = state['storage']

    # BUG-385: 这些 kwargs 名字是**任务选项**，与函数形参同名时会被静默吞掉。
    _TASK_OPTION_KEYS = ('priority', 'max_retries', 'depends_on')

    @staticmethod
    def _func_accepts_names(func: Callable, names) -> list:
        """返回 names 中该函数**确实会接收**的名字（形参或 **kwargs）。"""
        import inspect as _inspect

        try:
            _sig = _inspect.signature(func)
        except (TypeError, ValueError):
            return []
        _params = _sig.parameters
        _has_var_kw = any(p.kind is _inspect.Parameter.VAR_KEYWORD
                          for p in _params.values())
        if _has_var_kw:
            return list(names)
        return [n for n in names if n in _params and
                _params[n].kind in (_inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                    _inspect.Parameter.KEYWORD_ONLY)]

    def submit(self, func: Callable, *args, task_options: Optional[dict] = None,
               **kwargs) -> int:
        """
        提交任务

        Args:
            func: 要执行的函数
            *args: 位置参数
            task_options: 显式任务选项 dict（可选），支持键：
                ``priority`` / ``max_retries`` / ``depends_on``。
                提供后 **kwargs 全部作为函数参数转发，不再从中提取选项。
            **kwargs: 关键字参数；其中 ``priority`` / ``max_retries`` /
                ``depends_on`` 会被当作**任务选项**提取（若函数本身有同名形参/
                ``**kwargs``，会显式报错以免静默吞参——改用 task_options）。

        Returns:
            任务ID
        """
        # BUG-431: task_options 类型校验必须在提取之前（原实现先 task_options.get，
        # 传 'x'/123 会抛 AttributeError: 'str' object has no attribute 'get'）。
        if task_options is not None and not isinstance(task_options, dict):
            raise TypeError(
                f"submit() 的 task_options 需要 dict 或 None，收到 "
                f"{type(task_options).__name__}: {task_options!r}")

        if task_options is not None:
            # 显式通道：kwargs 全部转发给函数
            priority = task_options.get('priority', 0)
            max_retries = task_options.get('max_retries', 3)
            depends_on: Set[int] = _normalize_depends_on(
                task_options.get('depends_on'))
        else:
            # BUG-385: 同名冲突检测——原实现直接 pop，函数永远收不到这些参数
            _collided = [k for k in self._TASK_OPTION_KEYS if k in kwargs]
            if _collided:
                _accepted = self._func_accepts_names(func, _collided)
                if _accepted:
                    raise ValueError(
                        f"submit 参数冲突：{_accepted} 既是任务选项又是函数 "
                        f"{getattr(func, '__name__', func)!r} 的参数名，原实现会把它们"
                        f"静默吞掉（函数收不到）。请改用 "
                        f"submit(func, ..., task_options={{...}}) 显式传任务选项，"
                        f"或重命名函数形参。")
            priority = kwargs.pop('priority', 0)
            max_retries = kwargs.pop('max_retries', 3)
            depends_on = _normalize_depends_on(
                kwargs.pop('depends_on', None))

        # BUG-431: 任务选项类型校验（原实现只做了 BUG-385 的同名冲突检测）
        if not callable(func):
            raise TypeError(
                f"submit() 的 func 必须可调用，收到 "
                f"{type(func).__name__}: {func!r}")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise TypeError(
                f"submit() 的 priority 需要整数，收到 "
                f"{type(priority).__name__}: {priority!r}")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int):
            raise TypeError(
                f"submit() 的 max_retries 需要整数，收到 "
                f"{type(max_retries).__name__}: {max_retries!r}")
        if max_retries < 0:
            raise ValueError(f"submit() 的 max_retries 不能为负，收到 {max_retries}")

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
        func_name = getattr(func_to_serialize, '__name__', '')

        # BUG-C 修复：lambda 与 __main__ 函数优先用 pickle+base64 编码，
        # 使其在 spawn 子进程中可恢复（旧版 __registry__ 依赖进程内注册表，不可达）。
        # pickle 失败时（如局部函数、闭包）回退到 __registry__ 格式。
        if func_name == '<lambda>' or getattr(func_to_serialize, '__module__', '') == '__main__':
            try:
                data = pickle.dumps(func_to_serialize)
                encoded = base64.b64encode(data).decode('ascii')
                return f"__pickle__:{encoded}"
            except Exception:
                # pickle 失败（局部函数/闭包），回退到 registry 格式（同进程可用）
                key = id(func_to_serialize)
                self._func_registry[key] = func_to_serialize
                return f"__registry__:{key}"

        # 优先使用函数路径方式，这样可以正确处理装饰器
        try:
            return f"{func_to_serialize.__module__}:{func_name}"
        except Exception as e:
            raise ValueError(f"Cannot serialize function: {e}")

    def _deserialize_func(self, func_data: str) -> Callable:
        """反序列化函数"""
        if func_data.startswith('__pickle__:'):
            # BUG-C：pickle+base64 编码的函数，跨进程安全
            encoded = func_data.split(':', 1)[1]
            data = base64.b64decode(encoded)
            return pickle.loads(data)
        if func_data.startswith('__registry__:'):
            # 旧格式兼容：同进程注册表（已弃用）
            key = int(func_data.split(':', 1)[1])
            try:
                return self._func_registry[key]
            except KeyError:
                raise ValueError(
                    f"Registry function {key} not found; "
                    f"lambda/local function is not persistent across processes"
                )
        if ':' in func_data and not func_data.startswith('g'):
            # 函数路径格式
            module_path, func_name = func_data.split(':', 1)
            import importlib
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
            # 如果函数被装饰器包装，获取原始函数
            return getattr(func, '__wrapped__', func)
        # BUG-207: pickle 反序列化会执行 __reduce__ gadget（任意代码执行 RCE），已禁用。
        # 函数仅通过 __pickle__:<base64>（安全，受信任源）或 <module>:<func> 路径恢复。
        raise ValueError(
            f"unsupported func_data format (BUG-207): {func_data[:40]!r}"
        )

    def execute_task(self, task: Task) -> Any:
        """
        执行单个任务（内部使用）

        Returns:
            任务执行结果
        """
        func = self._deserialize_func(task.task_func)
        return func(*task.args, **task.kwargs)


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
