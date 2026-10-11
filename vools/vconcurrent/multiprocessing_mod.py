"""
multiprocessing_mod - 对 Python 标准库 multiprocessing 的高级封装

提供增强版进程类、进程池、共享内存封装、管道通信通道和装饰器。
所有类均支持上下文管理器协议，便于资源管理。

Windows 平台注意事项：
    1. Windows 默认使用 spawn 启动方式，传递给子进程的函数和参数必须可被 pickle 序列化
       （即模块级函数，不能用 lambda 或闭包）。
    2. 本模块不在导入时创建任何子进程，可安全 import。
    3. 实际创建子进程的代码应放在 if __name__ == '__main__' 块中。
"""

from __future__ import annotations

import multiprocessing
import os
import queue as _queue
import traceback
from functools import wraps
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

__all__ = [
    'VProcess',
    'VProcessPool',
    'SharedValue',
    'SharedDict',
    'SharedList',
    'PipeChannel',
    'process_pool',
    'run_in_process',
    'cpu_count',
]


# ============================================================================
# 工具函数
# ============================================================================

def cpu_count() -> int:
    """获取 CPU 核心数，至少返回 1。

    Returns:
        CPU 核心数。当无法获取时返回 1。
    """
    try:
        n = os.cpu_count()
    except NotImplementedError:
        n = None
    if n is None or n < 1:
        return 1
    return n


# ============================================================================
# VProcess - 增强版进程类
# ============================================================================

def _vp_worker(
    target: Callable[..., Any],
    args: Tuple,
    kwargs: Dict[str, Any],
    result_queue: Any,
) -> None:
    """VProcess 的工作函数（模块级，可被 pickle）。

    执行用户函数，并将返回值或异常通过队列传回父进程。
    """
    try:
        result = target(*args, **kwargs)
        result_queue.put(('ok', result))
    except Exception as e:
        result_queue.put(('err', e, traceback.format_exc()))


class VProcess(multiprocessing.Process):
    """增强版进程类。

    继承 multiprocessing.Process，支持：
      - 返回值获取：通过队列获取子进程函数的返回值
      - 超时等待：wait() / get_result() 均支持超时
      - 异常捕获：子进程抛出的异常会被捕获并通过 get_result 重新抛出
      - 优雅终止：terminate_gracefully() 先 terminate 再 kill

    使用方式：
        # 方式 1: 上下文管理器（推荐）
        with VProcess(target=func, args=(1, 2)) as proc:
            result = proc.get_result()

        # 方式 2: 手动管理
        proc = VProcess(target=func, args=(1, 2))
        proc.start()
        result = proc.get_result(timeout=10)
        proc.terminate_gracefully()

    注意：target 函数及其参数必须可被 pickle 序列化（Windows spawn 要求）。
    """

    def __init__(
        self,
        target: Callable[..., Any],
        args: Tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        *,
        name: Optional[str] = None,
        daemon: Optional[bool] = None,
    ) -> None:
        # 结果队列：在 super().__init__ 之前创建，并作为参数传递给子进程
        self._result_queue: Any = multiprocessing.Queue()
        super().__init__(
            target=_vp_worker,
            args=(target, tuple(args), dict(kwargs or {}), self._result_queue),
            name=name,
            daemon=daemon,
        )
        # 父进程侧的缓存状态
        self._vresult: Any = None
        self._vexception: Optional[BaseException] = None
        self._vtb: Optional[str] = None
        self._vfetched: bool = False
        self._vstarted: bool = False

    def start(self) -> None:
        """启动进程。"""
        super().start()
        self._vstarted = True

    def get_result(self, timeout: Optional[float] = None) -> Any:
        """获取子进程函数的返回值。

        首次调用会从结果队列中读取（阻塞），后续调用返回缓存的值。
        若子进程抛出异常，则在此处重新抛出。

        Args:
            timeout: 超时秒数，None 表示无限等待。

        Returns:
            子进程函数的返回值。

        Raises:
            TimeoutError: 超时未获取到结果。
            Exception: 子进程抛出的异常（重新抛出）。
        """
        if not self._vfetched:
            try:
                msg = self._result_queue.get(timeout=timeout)
            except _queue.Empty:
                raise TimeoutError(
                    f"VProcess {self.name!r} get_result timeout after {timeout}s"
                )
            status = msg[0]
            if status == 'ok':
                self._vresult = msg[1]
            else:
                self._vexception = msg[1]
                self._vtb = msg[2]
            self._vfetched = True
        if self._vexception is not None:
            raise self._vexception
        return self._vresult

    def wait(self, timeout: Optional[float] = None) -> bool:
        """等待进程结束。

        Args:
            timeout: 超时秒数，None 表示无限等待。

        Returns:
            是否在超时前结束。
        """
        self.join(timeout=timeout)
        return not self.is_alive()

    def terminate_gracefully(self, timeout: float = 2.0) -> None:
        """优雅终止进程：先 terminate，再 join，仍存活则 kill。

        Args:
            timeout: terminate 后等待 join 的超时秒数。
        """
        if self.is_alive():
            self.terminate()
            self.join(timeout=timeout)
            if self.is_alive():
                # Python 3.7+ 提供 kill()
                try:
                    self.kill()
                except AttributeError:
                    pass
                self.join(timeout=1.0)

    @property
    def exception(self) -> Optional[BaseException]:
        """子进程抛出的异常（需先调用 get_result）。"""
        return self._vexception

    @property
    def traceback_str(self) -> Optional[str]:
        """子进程异常的 traceback 字符串。"""
        return self._vtb

    @property
    def result_queue(self) -> Any:
        """底层结果队列（高级用法）。"""
        return self._result_queue

    def __enter__(self) -> 'VProcess':
        if not self._vstarted:
            self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._vstarted:
            if self.is_alive():
                self.terminate_gracefully()
            else:
                self.join(timeout=1.0)
        try:
            self._result_queue.close()
            self._result_queue.join_thread()
        except Exception:
            pass


# ============================================================================
# VProcessPool - 进程池
# ============================================================================

class VProcessPool:
    """进程池。

    封装 multiprocessing.Pool，支持：
      - 动态添加任务：add_task / apply_async
      - 结果收集：gather（收集所有已添加任务的结果）
      - 超时控制
      - 上下文管理器

    注意：传递的函数必须是模块级函数（可被 pickle），不能使用 lambda 或闭包。

    使用方式：
        with VProcessPool(processes=4) as pool:
            r1 = pool.add_task(func1, 1, 2)
            r2 = pool.add_task(func2, 'a')
            # 单独获取
            print(r1.get(timeout=10))
            # 批量收集
            print(pool.gather())
    """

    def __init__(self, processes: Optional[int] = None) -> None:
        self._nproc: int = processes or cpu_count()
        self._pool: Optional[Any] = None
        self._async_results: List[Any] = []

    def _ensure_pool(self) -> None:
        if self._pool is None:
            ctx = multiprocessing.get_context()
            self._pool = ctx.Pool(processes=self._nproc)

    def start(self) -> None:
        """启动进程池。"""
        self._ensure_pool()

    def add_task(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """添加任务到进程池。

        Args:
            func: 要执行的函数（必须可被 pickle）。
            *args: 函数位置参数。
            **kwargs: 函数关键字参数。

        Returns:
            multiprocessing.pool.AsyncResult 对象，可调用 .get() 获取结果。
        """
        self._ensure_pool()
        r = self._pool.apply_async(func, args, kwargs)
        self._async_results.append(r)
        return r

    def apply_async(
        self,
        func: Callable[..., Any],
        args: Tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """异步执行函数。

        Args:
            func: 要执行的函数。
            args: 位置参数元组。
            kwargs: 关键字参数字典。

        Returns:
            AsyncResult 对象。
        """
        self._ensure_pool()
        return self._pool.apply_async(func, tuple(args), kwargs or {})

    def map(
        self,
        func: Callable[..., Any],
        iterable: Iterable[Any],
        timeout: Optional[float] = None,
    ) -> List[Any]:
        """并行 map，阻塞直到所有完成。

        Args:
            func: 要执行的函数。
            iterable: 可迭代对象。
            timeout: 超时秒数。

        Returns:
            结果列表。
        """
        self._ensure_pool()
        result = self._pool.map_async(func, list(iterable))
        return result.get(timeout=timeout)

    def gather(self, timeout: Optional[float] = None) -> List[Any]:
        """收集所有已通过 add_task 添加的任务结果。

        Args:
            timeout: 单个任务结果获取的超时秒数。

        Returns:
            结果列表（按 add_task 调用顺序）。
        """
        results: List[Any] = []
        for r in self._async_results:
            results.append(r.get(timeout=timeout))
        return results

    def close(self) -> None:
        """关闭进程池，等待所有已提交任务完成。"""
        if self._pool is not None:
            self._pool.close()
            self._pool.join()
            self._pool = None
        self._async_results.clear()

    def terminate(self) -> None:
        """立即终止进程池，不等待任务完成。"""
        if self._pool is not None:
            self._pool.terminate()
            self._pool = None
        self._async_results.clear()

    @property
    def processes(self) -> int:
        """进程池大小。"""
        return self._nproc

    def __enter__(self) -> 'VProcessPool':
        self._ensure_pool()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.terminate()
        else:
            self.close()


# ============================================================================
# 共享内存封装
# ============================================================================

class SharedValue:
    """共享内存值封装。

    基于 multiprocessing.Value，支持 get()/set() 和上下文管理。
    适用于进程间共享单个标量值。

    使用方式：
        with SharedValue('i', 0) as sv:
            sv.set(42)
            print(sv.get())  # 42

        # 在子进程中使用：将 sv.raw 传给子进程，子进程通过 .value 读写
    """

    def __init__(self, typecode: str = 'i', default: Any = 0, *, lock: bool = True) -> None:
        self._value: Any = multiprocessing.Value(typecode, default, lock=lock)

    def get(self) -> Any:
        """获取当前值（加锁）。"""
        with self._value.get_lock():
            return self._value.value

    def set(self, value: Any) -> None:
        """设置值（加锁）。"""
        with self._value.get_lock():
            self._value.value = value

    @property
    def raw(self) -> Any:
        """原始 multiprocessing.Value 对象（用于传递给子进程）。"""
        return self._value

    def __enter__(self) -> 'SharedValue':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


class SharedDict:
    """共享内存字典。

    基于 multiprocessing.Manager.dict，支持跨进程读写。

    使用方式：
        with SharedDict() as sd:
            sd['a'] = 1
            print(sd['a'])  # 1
            print(sd.get('b', 0))  # 0

    注意：每次创建都会启动一个 Manager 服务进程，使用完毕后应通过
    上下文管理器或 close() 关闭以释放资源。
    """

    def __init__(self, initial: Optional[Dict[Any, Any]] = None) -> None:
        self._manager: Any = multiprocessing.Manager()
        self._dict: Any = self._manager.dict(initial or {})

    def __getitem__(self, key: Any) -> Any:
        return self._dict[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        self._dict[key] = value

    def __delitem__(self, key: Any) -> None:
        del self._dict[key]

    def __contains__(self, key: Any) -> bool:
        return key in self._dict

    def __len__(self) -> int:
        return len(self._dict)

    def __iter__(self):
        return iter(self._dict)

    def get(self, key: Any, default: Any = None) -> Any:
        """获取键值，不存在时返回 default。"""
        return self._dict.get(key, default)

    def keys(self):
        """返回所有键。"""
        return self._dict.keys()

    def values(self):
        """返回所有值。"""
        return self._dict.values()

    def items(self):
        """返回所有键值对。"""
        return self._dict.items()

    def update(self, other: Dict[Any, Any]) -> None:
        """批量更新。"""
        self._dict.update(other)

    def to_dict(self) -> Dict[Any, Any]:
        """转换为普通字典。"""
        return dict(self._dict)

    @property
    def raw(self) -> Any:
        """原始 Manager.dict 对象。"""
        return self._dict

    def close(self) -> None:
        """关闭底层 Manager 服务进程。"""
        try:
            self._manager.shutdown()
        except Exception:
            pass

    def __enter__(self) -> 'SharedDict':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class SharedList:
    """共享内存列表。

    基于 multiprocessing.Manager.list，支持跨进程读写。

    使用方式：
        with SharedList() as sl:
            sl.append(1)
            sl.append(2)
            print(sl[0])  # 1
            print(len(sl))  # 2

    注意：每次创建都会启动一个 Manager 服务进程，使用完毕后应通过
    上下文管理器或 close() 关闭以释放资源。
    """

    def __init__(self, initial: Optional[List[Any]] = None) -> None:
        self._manager: Any = multiprocessing.Manager()
        self._list: Any = self._manager.list(initial or [])

    def __getitem__(self, index: Any) -> Any:
        return self._list[index]

    def __setitem__(self, index: Any, value: Any) -> None:
        self._list[index] = value

    def __delitem__(self, index: Any) -> None:
        del self._list[index]

    def __len__(self) -> int:
        return len(self._list)

    def __iter__(self):
        return iter(self._list)

    def append(self, value: Any) -> None:
        """追加元素。"""
        self._list.append(value)

    def extend(self, other: Iterable[Any]) -> None:
        """批量追加。"""
        self._list.extend(other)

    def pop(self, index: int = -1) -> Any:
        """弹出并返回指定位置的元素。"""
        return self._list.pop(index)

    def to_list(self) -> List[Any]:
        """转换为普通列表。"""
        return list(self._list)

    @property
    def raw(self) -> Any:
        """原始 Manager.list 对象。"""
        return self._list

    def close(self) -> None:
        """关闭底层 Manager 服务进程。"""
        try:
            self._manager.shutdown()
        except Exception:
            pass

    def __enter__(self) -> 'SharedList':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ============================================================================
# PipeChannel - 双向管道通信通道
# ============================================================================

class PipeChannel:
    """双向管道通信通道。

    基于 multiprocessing.Pipe，支持 send/recv/send_bytes/recv_bytes，带超时。

    通道持有两个 Connection：parent_conn（主进程使用）和 child_conn（子进程使用）。
    send/recv/send_bytes/recv_bytes 操作 parent_conn 端；
    子进程应通过 child_conn 属性获取另一端进行通信。

    使用方式：
        def child_fn(conn):
            msg = conn.recv()
            conn.send(f"echo: {msg}")

        with PipeChannel() as ch:
            proc = multiprocessing.Process(
                target=child_fn, args=(ch.child_conn,)
            )
            proc.start()
            ch.send("hello")
            print(ch.recv(timeout=10))  # echo: hello
            proc.join()

    Args:
        duplex: 是否为双向管道。True 时两端均可收发；False 时 parent_conn 只能收，
            child_conn 只能发。
    """

    def __init__(self, duplex: bool = True) -> None:
        self._parent_conn: Any
        self._child_conn: Any
        self._parent_conn, self._child_conn = multiprocessing.Pipe(duplex=duplex)
        self._duplex: bool = duplex

    def send(self, obj: Any) -> None:
        """从父端发送对象。

        Args:
            obj: 可被 pickle 序列化的对象。
        """
        self._parent_conn.send(obj)

    def recv(self, timeout: Optional[float] = None) -> Any:
        """从父端接收对象。

        Args:
            timeout: 超时秒数，None 表示无限等待。

        Returns:
            接收到的对象。

        Raises:
            TimeoutError: 超时未收到数据。
            EOFError: 连接已关闭且无数据可读。
        """
        if timeout is None:
            return self._parent_conn.recv()
        if not self._parent_conn.poll(timeout):
            raise TimeoutError(f"PipeChannel recv timeout after {timeout}s")
        return self._parent_conn.recv()

    def send_bytes(self, buf: bytes) -> None:
        """从父端发送字节串。

        Args:
            buf: 字节串。
        """
        self._parent_conn.send_bytes(buf)

    def recv_bytes(self, timeout: Optional[float] = None) -> bytes:
        """从父端接收字节串。

        Args:
            timeout: 超时秒数，None 表示无限等待。

        Returns:
            接收到的字节串。

        Raises:
            TimeoutError: 超时未收到数据。
            EOFError: 连接已关闭且无数据可读。
        """
        if timeout is None:
            return self._parent_conn.recv_bytes()
        if not self._parent_conn.poll(timeout):
            raise TimeoutError(f"PipeChannel recv_bytes timeout after {timeout}s")
        return self._parent_conn.recv_bytes()

    @property
    def parent_conn(self) -> Any:
        """父端 Connection（主进程使用）。"""
        return self._parent_conn

    @property
    def child_conn(self) -> Any:
        """子端 Connection（传给子进程使用）。"""
        return self._child_conn

    @property
    def duplex(self) -> bool:
        """是否为双向管道。"""
        return self._duplex

    def close(self) -> None:
        """关闭两端连接。"""
        try:
            self._parent_conn.close()
        except Exception:
            pass
        try:
            self._child_conn.close()
        except Exception:
            pass

    def __enter__(self) -> 'PipeChannel':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ============================================================================
# 装饰器
# ============================================================================
#
# Windows spawn 兼容性说明：
# 装饰器返回的 wrapper 会替换模块命名空间中原始函数的引用，导致 multiprocessing
# 按 (__module__, __qualname__) 查找时找到 wrapper 而非原始函数，pickle 失败。
# 为此，装饰器在装饰时将原始函数注册到模块级注册表 _decorated_funcs，并向子进程
# 传递一个可 pickle 的 _RegisteredCaller 实例（仅携带字符串 key）。子进程（spawn
# 模式）重新导入用户模块时会再次执行装饰器，从而重新填充子进程自身的注册表，
# 使 key 在父子进程间保持一致，_RegisteredCaller 即可正确派发到真实函数。

# 模块级注册表：key 格式 "<normalized_module>:<qualname>"
_decorated_funcs: Dict[str, Callable[..., Any]] = {}


def _register_decorated(func: Callable[..., Any]) -> str:
    """注册被装饰函数，返回跨进程稳定的 key。

    spawn 模式下子进程会把 __main__ 重新导入为 __mp_main__，这里做归一化
    以保证父子进程生成相同的 key。
    """
    mod = func.__module__ or ''
    if mod in ('__main__', '__mp_main__'):
        mod = '__main__'
    key = f"{mod}:{func.__qualname__}"
    _decorated_funcs[key] = func
    return key


class _RegisteredCaller:
    """可 pickle 的调用器：通过 key 从注册表查找真实函数并调用。"""

    def __init__(self, key: str) -> None:
        self._key = key

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        try:
            fn = _decorated_funcs[self._key]
        except KeyError:
            raise RuntimeError(
                f"已注册函数 {self._key!r} 在当前进程中未找到。"
                "请确保定义该函数的模块在子进程中被正确导入。"
            ) from None
        return fn(*args, **kwargs)


def process_pool(
    processes: Optional[int] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """装饰器：用进程池执行被装饰函数。

    每次调用都会创建临时进程池并阻塞等待结果。
    适用于将 CPU 密集型函数卸载到独立进程执行。

    被装饰函数的参数和返回值必须可被 pickle 序列化。装饰器内部通过
    注册表机制保证在 Windows spawn 模式下也能正常工作。

    Args:
        processes: 进程池大小，默认为 CPU 核心数。

    使用方式：
        @process_pool(processes=4)
        def heavy_compute(x):
            return x * x

        result = heavy_compute(10)  # 在进程池中执行，返回 100
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        key = _register_decorated(func)
        caller = _RegisteredCaller(key)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with VProcessPool(processes=processes) as pool:
                return pool.apply_async(caller, args, kwargs).get()

        wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        return wrapper

    return decorator


def run_in_process(
    *,
    daemon: Optional[bool] = None,
    timeout: Optional[float] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """装饰器：将函数在新进程中运行。

    每次调用都会启动一个新进程执行被装饰函数，并阻塞等待结果。
    适用于需要进程级隔离（如绕过 GIL、独立内存空间）的场景。

    被装饰函数的参数和返回值必须可被 pickle 序列化。装饰器内部通过
    注册表机制保证在 Windows spawn 模式下也能正常工作。

    Args:
        daemon: 是否为守护进程。守护进程会在父进程退出时被强制终止。
        timeout: 获取结果的超时秒数，None 表示无限等待。

    使用方式：
        @run_in_process(timeout=30)
        def isolated_task(x):
            return x + 1

        result = isolated_task(10)  # 在新进程中执行，返回 11
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        key = _register_decorated(func)
        caller = _RegisteredCaller(key)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with VProcess(
                target=caller, args=args, kwargs=kwargs, daemon=daemon
            ) as proc:
                return proc.get_result(timeout=timeout)

        wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        return wrapper

    return decorator
