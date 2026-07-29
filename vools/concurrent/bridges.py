"""
vools.concurrent.bridges - 跨模块桥接通信

提供不同并发模型之间的桥接和通信机制，支持线程与进程、队列之间、
跨进程通道、共享内存等多种通信方式。

主要组件：
    ThreadProcessBridge - 线程与进程之间的双向通信桥
    QueueBridge         - 队列桥接，自动转发消息
    ChannelBridge       - 基于 Pipe 的跨进程通道
    PipePair            - 双向管道对
    SharedBridge        - 基于共享内存的桥接（大数据量传输）
    EventBridge         - 事件桥接，跨线程/进程传递事件通知
    StreamBridge        - 流式桥接，带背压控制

函数：
    bridge_queues       - 桥接两个队列
"""

from __future__ import annotations

import json
import pickle
import queue
import threading
import time
from typing import (
    Any,
    Callable,
    Generic,
    Iterator,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

import multiprocessing as _mp
from multiprocessing.connection import Connection

__all__ = [
    "ThreadProcessBridge",
    "QueueBridge",
    "ChannelBridge",
    "PipePair",
    "SharedBridge",
    "EventBridge",
    "bridge_queues",
    "StreamBridge",
]

_T = TypeVar("_T")
_U = TypeVar("_U")


def _get_mp_context() -> Any:
    """获取 multiprocessing 上下文，确保 Windows 兼容性。"""
    try:
        return _mp.get_context()
    except Exception:
        return _mp


# ============================================================================
# PipePair - 双向管道对
# ============================================================================


class PipePair:
    """双向管道对，两端都可读写，封装 multiprocessing.Pipe。

    提供两个连接端点（a 和 b），每个端点都可以发送和接收数据。

    示例::

        pair = PipePair()
        pair.a.send("hello")
        msg = pair.b.recv()
        pair.close()
    """

    def __init__(self, duplex: bool = True) -> None:
        ctx = _get_mp_context()
        self._conn_a, self._conn_b = ctx.Pipe(duplex=duplex)

    @property
    def a(self) -> Connection:
        """管道 A 端连接。"""
        return self._conn_a

    @property
    def b(self) -> Connection:
        """管道 B 端连接。"""
        return self._conn_b

    def close(self) -> None:
        """关闭管道两端。"""
        try:
            self._conn_a.close()
        except Exception:
            pass
        try:
            self._conn_b.close()
        except Exception:
            pass

    def __enter__(self) -> "PipePair":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


# ============================================================================
# ThreadProcessBridge - 线程与进程之间的双向通信桥
# ============================================================================


class ThreadProcessBridge:
    """线程与进程之间的双向通信桥。

    内部使用 multiprocessing.Pipe + 线程适配器，支持在线程侧和进程侧
    分别发送和接收消息，支持超时。

    线程侧和进程侧各有一对 send/recv 方法，使用时需要注意调用方所在的
    执行上下文。

    示例::

        bridge = ThreadProcessBridge()

        # 在线程中
        bridge.send_thread_side("hello from thread")

        # 在子进程中
        msg = bridge.recv_process_side()
    """

    def __init__(self) -> None:
        self._pipe_pair = PipePair(duplex=True)
        self._thread_lock = threading.Lock()
        self._closed = False

    # -- 线程侧方法 ---------------------------------------------------------

    def send_thread_side(self, obj: Any, timeout: Optional[float] = None) -> bool:
        """从线程侧发送消息。

        Args:
            obj: 要发送的对象（必须可 pickle）
            timeout: 发送超时时间（秒），None 表示无限等待

        Returns:
            发送成功返回 True，超时返回 False
        """
        if self._closed:
            raise RuntimeError("Bridge is closed")
        try:
            if timeout is not None:
                if not self._pipe_pair.a.poll(timeout):
                    return False
            with self._thread_lock:
                self._pipe_pair.a.send(obj)
            return True
        except (EOFError, OSError, ValueError):
            return False

    def recv_thread_side(self, timeout: Optional[float] = None) -> Optional[Any]:
        """从线程侧接收消息。

        Args:
            timeout: 接收超时时间（秒），None 表示无限等待

        Returns:
            接收到的对象，超时或关闭返回 None
        """
        if self._closed:
            return None
        try:
            if timeout is not None:
                if not self._pipe_pair.a.poll(timeout):
                    return None
            with self._thread_lock:
                return self._pipe_pair.a.recv()
        except (EOFError, OSError, ValueError):
            return None

    # -- 进程侧方法 ---------------------------------------------------------

    def send_process_side(self, obj: Any, timeout: Optional[float] = None) -> bool:
        """从进程侧发送消息。

        Args:
            obj: 要发送的对象（必须可 pickle）
            timeout: 发送超时时间（秒），None 表示无限等待

        Returns:
            发送成功返回 True，超时返回 False
        """
        if self._closed:
            raise RuntimeError("Bridge is closed")
        try:
            if timeout is not None:
                if not self._pipe_pair.b.poll(timeout):
                    return False
            self._pipe_pair.b.send(obj)
            return True
        except (EOFError, OSError, ValueError):
            return False

    def recv_process_side(self, timeout: Optional[float] = None) -> Optional[Any]:
        """从进程侧接收消息。

        Args:
            timeout: 接收超时时间（秒），None 表示无限等待

        Returns:
            接收到的对象，超时或关闭返回 None
        """
        if self._closed:
            return None
        try:
            if timeout is not None:
                if not self._pipe_pair.b.poll(timeout):
                    return None
            return self._pipe_pair.b.recv()
        except (EOFError, OSError, ValueError):
            return None

    # -- 生命周期 -----------------------------------------------------------

    def close(self) -> None:
        """关闭通信桥。"""
        self._closed = True
        self._pipe_pair.close()

    def __enter__(self) -> "ThreadProcessBridge":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


# ============================================================================
# ChannelBridge - 基于 Pipe 的跨进程通道
# ============================================================================


class ChannelBridge:
    """基于 multiprocessing.Pipe 的跨进程通道。

    支持多种序列化方式：
    - 原始对象（pickle 序列化）
    - JSON 格式
    - Pickle 格式（显式控制）

    带超时和关闭语义，支持上下文管理器。

    示例::

        ch = ChannelBridge()
        ch.send_json({"key": "value"})
        data = ch.recv_json()
        ch.close()
    """

    def __init__(self, duplex: bool = True) -> None:
        self._pipe_pair = PipePair(duplex=duplex)
        self._closed = False

    @property
    def connection(self) -> Connection:
        """底层连接对象（本端）。"""
        return self._pipe_pair.a

    @property
    def peer_connection(self) -> Connection:
        """对端连接对象（传给其他进程使用）。"""
        return self._pipe_pair.b

    # -- 基础 send/recv -----------------------------------------------------

    def send(self, obj: Any, timeout: Optional[float] = None) -> bool:
        """发送对象（使用默认 pickle 序列化）。

        Args:
            obj: 要发送的对象
            timeout: 发送超时时间（秒），None 表示无限等待

        Returns:
            发送成功返回 True，超时或关闭返回 False
        """
        if self._closed:
            return False
        try:
            if timeout is not None:
                if not self._pipe_pair.a.poll(timeout):
                    return False
            self._pipe_pair.a.send(obj)
            return True
        except (EOFError, OSError, ValueError):
            return False

    def recv(self, timeout: Optional[float] = None) -> Optional[Any]:
        """接收对象。

        Args:
            timeout: 接收超时时间（秒），None 表示无限等待

        Returns:
            接收到的对象，超时或关闭返回 None
        """
        if self._closed:
            return None
        try:
            if timeout is not None:
                if not self._pipe_pair.a.poll(timeout):
                    return None
            return self._pipe_pair.a.recv()
        except (EOFError, OSError, ValueError):
            return None

    # -- JSON 序列化 --------------------------------------------------------

    def send_json(self, data: Any, timeout: Optional[float] = None) -> bool:
        """发送 JSON 格式数据。

        Args:
            data: 可 JSON 序列化的数据
            timeout: 发送超时时间（秒）

        Returns:
            发送成功返回 True
        """
        try:
            json_str = json.dumps(data, ensure_ascii=False)
            return self.send(("__json__", json_str), timeout=timeout)
        except (TypeError, ValueError):
            return False

    def recv_json(self, timeout: Optional[float] = None) -> Optional[Any]:
        """接收 JSON 格式数据。

        Args:
            timeout: 接收超时时间（秒）

        Returns:
            解析后的数据，超时或格式错误返回 None
        """
        msg = self.recv(timeout=timeout)
        if msg is None:
            return None
        if isinstance(msg, tuple) and len(msg) == 2 and msg[0] == "__json__":
            try:
                return json.loads(msg[1])
            except (json.JSONDecodeError, TypeError):
                return None
        return msg

    # -- Pickle 序列化 ------------------------------------------------------

    def send_pickle(self, obj: Any, timeout: Optional[float] = None) -> bool:
        """发送 pickle 序列化对象。

        Args:
            obj: 可 pickle 序列化的对象
            timeout: 发送超时时间（秒）

        Returns:
            发送成功返回 True
        """
        try:
            pickled = pickle.dumps(obj)
            return self.send(("__pickle__", pickled), timeout=timeout)
        except (pickle.PickleError, TypeError):
            return False

    def recv_pickle(self, timeout: Optional[float] = None) -> Optional[Any]:
        """接收 pickle 序列化对象。

        Args:
            timeout: 接收超时时间（秒）

        Returns:
            反序列化后的对象，超时或错误返回 None
        """
        msg = self.recv(timeout=timeout)
        if msg is None:
            return None
        if isinstance(msg, tuple) and len(msg) == 2 and msg[0] == "__pickle__":
            try:
                return pickle.loads(msg[1])
            except (pickle.UnpicklingError, TypeError, ValueError):
                return None
        return msg

    # -- 状态查询 -----------------------------------------------------------

    def poll(self, timeout: float = 0.0) -> bool:
        """检查是否有数据可读。

        Args:
            timeout: 等待超时时间（秒）

        Returns:
            有数据可读返回 True
        """
        if self._closed:
            return False
        try:
            return self._pipe_pair.a.poll(timeout)
        except (EOFError, OSError, ValueError):
            return False

    @property
    def closed(self) -> bool:
        """通道是否已关闭。"""
        return self._closed

    # -- 生命周期 -----------------------------------------------------------

    def close(self) -> None:
        """关闭通道。"""
        self._closed = True
        self._pipe_pair.close()

    def __enter__(self) -> "ChannelBridge":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


# ============================================================================
# QueueBridge - 队列桥接
# ============================================================================


class QueueBridge(Generic[_T]):
    """将一个队列桥接到另一个队列，自动转发消息。

    支持过滤函数和转换函数，可在转发过程中对消息进行处理。

    示例::

        src = queue.Queue()
        dst = queue.Queue()
        bridge = QueueBridge(
            src, dst,
            filter_fn=lambda x: x > 0,
            transform_fn=lambda x: x * 2,
        )
        bridge.start()
        src.put(5)
        result = dst.get()  # 10
        bridge.stop()
    """

    def __init__(
        self,
        source: Any,
        destination: Any,
        filter_fn: Optional[Callable[[_T], bool]] = None,
        transform_fn: Optional[Callable[[_T], Any]] = None,
        daemon: bool = True,
    ) -> None:
        self._source = source
        self._destination = destination
        self._filter_fn = filter_fn
        self._transform_fn = transform_fn
        self._daemon = daemon
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._source.get(timeout=0.1)
            except (queue.Empty, AttributeError):
                continue

            try:
                if self._filter_fn is not None and not self._filter_fn(item):
                    continue

                if self._transform_fn is not None:
                    item = self._transform_fn(item)

                self._destination.put(item)
            except Exception:
                pass

    def start(self) -> None:
        """启动桥接。"""
        if self._running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=self._daemon)
        self._thread.start()
        self._running = True

    def stop(self, timeout: Optional[float] = None) -> None:
        """停止桥接。

        Args:
            timeout: 等待线程结束的超时时间（秒）
        """
        if not self._running:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._running = False
        self._thread = None

    @property
    def is_running(self) -> bool:
        """桥接是否运行中。"""
        return self._running

    def __enter__(self) -> "QueueBridge[_T]":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()


# ============================================================================
# bridge_queues - 桥接两个队列的函数
# ============================================================================


def bridge_queues(
    q1: Any,
    q2: Any,
    direction: str = "both",
    filter_fn: Optional[Callable[[Any], bool]] = None,
    transform_fn: Optional[Callable[[Any], Any]] = None,
    daemon: bool = True,
) -> Tuple[Optional[QueueBridge], Optional[QueueBridge]]:
    """桥接两个队列，支持双向转发。

    Args:
        q1: 第一个队列
        q2: 第二个队列
        direction: 转发方向
            - "forward": q1 -> q2
            - "backward": q2 -> q1
            - "both": 双向
        filter_fn: 过滤函数，返回 False 的消息不会被转发
        transform_fn: 转换函数，转发前对消息进行转换
        daemon: 桥接线程是否为守护线程

    Returns:
        (forward_bridge, backward_bridge) 元组，未启用的方向为 None
    """
    forward: Optional[QueueBridge] = None
    backward: Optional[QueueBridge] = None

    if direction in ("forward", "both"):
        forward = QueueBridge(
            q1, q2,
            filter_fn=filter_fn,
            transform_fn=transform_fn,
            daemon=daemon,
        )
        forward.start()

    if direction in ("backward", "both"):
        backward = QueueBridge(
            q2, q1,
            filter_fn=filter_fn,
            transform_fn=transform_fn,
            daemon=daemon,
        )
        backward.start()

    return forward, backward


# ============================================================================
# SharedBridge - 基于共享内存的桥接
# ============================================================================


class SharedBridge:
    """基于共享内存的桥接，支持大数据量传输。

    使用 multiprocessing.shared_memory 在进程间共享数据，适用于大数组、
    大对象等数据传输，避免 pickle 序列化的开销。

    注意：共享内存需要显式管理生命周期，使用后必须调用 close() 和 unlink()。

    示例::

        bridge = SharedBridge(size=1024 * 1024)
        data = b"hello" * 1000
        bridge.write(data)
        # 在另一个进程中
        bridge2 = SharedBridge(name=bridge.name)
        data = bridge2.read(len(data))
    """

    def __init__(
        self,
        size: Optional[int] = None,
        name: Optional[str] = None,
    ) -> None:
        from multiprocessing import shared_memory

        self._shm: Optional[shared_memory.SharedMemory] = None
        self._name: Optional[str] = None
        self._size = size or 0
        self._owns = name is None

        if name is not None:
            self._shm = shared_memory.SharedMemory(name=name)
            self._name = name
            self._size = self._shm.size
        elif size is not None and size > 0:
            self._shm = shared_memory.SharedMemory(create=True, size=size)
            self._name = self._shm.name

    @property
    def name(self) -> Optional[str]:
        """共享内存名称。"""
        return self._name

    @property
    def size(self) -> int:
        """共享内存大小（字节）。"""
        return self._size

    @property
    def buf(self) -> memoryview:
        """共享内存缓冲区视图。"""
        if self._shm is None:
            raise RuntimeError("Shared memory not initialized")
        return self._shm.buf

    def write(self, data: bytes, offset: int = 0) -> int:
        """写入数据到共享内存。

        Args:
            data: 要写入的字节数据
            offset: 写入偏移量

        Returns:
            实际写入的字节数
        """
        if self._shm is None:
            raise RuntimeError("Shared memory not initialized")
        n = min(len(data), self._size - offset)
        self._shm.buf[offset:offset + n] = data[:n]
        return n

    def read(self, n: int, offset: int = 0) -> bytes:
        """从共享内存读取数据。

        Args:
            n: 要读取的字节数
            offset: 读取偏移量

        Returns:
            读取的字节数据
        """
        if self._shm is None:
            raise RuntimeError("Shared memory not initialized")
        n = min(n, self._size - offset)
        return bytes(self._shm.buf[offset:offset + n])

    def write_object(self, obj: Any, offset: int = 0) -> int:
        """写入 pickle 序列化对象。

        Args:
            obj: 要写入的对象
            offset: 写入偏移量

        Returns:
            实际写入的字节数
        """
        data = pickle.dumps(obj)
        return self.write(data, offset)

    def read_object(self, n: int, offset: int = 0) -> Any:
        """读取 pickle 序列化对象。

        Args:
            n: 要读取的字节数
            offset: 读取偏移量

        Returns:
            反序列化后的对象
        """
        data = self.read(n, offset)
        return pickle.loads(data)

    def close(self) -> None:
        """关闭共享内存访问。"""
        if self._shm is not None:
            try:
                self._shm.close()
            except Exception:
                pass
            self._shm = None

    def unlink(self) -> None:
        """释放共享内存（创建者调用）。"""
        if self._shm is not None and self._owns:
            try:
                self._shm.close()
                self._shm.unlink()
            except Exception:
                pass
            self._shm = None

    def __enter__(self) -> "SharedBridge":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._owns:
            self.unlink()
        else:
            self.close()


# ============================================================================
# EventBridge - 事件桥接
# ============================================================================


class EventBridge:
    """事件桥接，跨线程/进程传递事件通知。

    基于 multiprocessing.Event 实现，支持 set()/clear()/wait() 操作，
    可跨线程和跨进程使用。

    示例::

        evt = EventBridge()

        # 在子进程/线程中
        evt.set()

        # 在主进程中
        evt.wait(timeout=5.0)
    """

    def __init__(self, event: Optional[Any] = None) -> None:
        ctx = _get_mp_context()
        if event is not None:
            self._event = event
        else:
            self._event = ctx.Event()

    def set(self) -> None:
        """设置事件，通知所有等待者。"""
        self._event.set()

    def clear(self) -> None:
        """清除事件。"""
        self._event.clear()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """等待事件被设置。

        Args:
            timeout: 超时时间（秒），None 表示无限等待

        Returns:
            事件已设置返回 True，超时返回 False
        """
        return self._event.wait(timeout=timeout)

    def is_set(self) -> bool:
        """事件是否已设置。"""
        return self._event.is_set()

    @property
    def event(self) -> Any:
        """底层 multiprocessing.Event 对象。"""
        return self._event

    def __enter__(self) -> "EventBridge":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            self._event.clear()
        except Exception:
            pass


# ============================================================================
# StreamBridge - 流式桥接
# ============================================================================


class StreamBridge(Generic[_T]):
    """流式桥接，支持流式数据转发，带背压控制和缓冲区大小。

    使用队列作为缓冲区，当缓冲区满时阻塞写入，实现背压控制。

    示例::

        stream = StreamBridge(buffer_size=100)
        stream.start()

        # 生产者
        for i in range(1000):
            stream.send(i)

        # 消费者
        for item in stream:
            process(item)
    """

    _SENTINEL = object()

    def __init__(
        self,
        buffer_size: int = 0,
        transform_fn: Optional[Callable[[_T], Any]] = None,
    ) -> None:
        self._buffer_size = buffer_size
        self._transform_fn = transform_fn
        self._queue: queue.Queue = queue.Queue(maxsize=buffer_size)
        self._closed = False
        self._lock = threading.Lock()

    @property
    def buffer_size(self) -> int:
        """缓冲区大小。"""
        return self._buffer_size

    @property
    def qsize(self) -> int:
        """当前队列中的元素数量。"""
        return self._queue.qsize()

    def send(self, item: _T, timeout: Optional[float] = None) -> bool:
        """发送数据项。

        Args:
            item: 数据项
            timeout: 发送超时时间（秒），None 表示无限等待

        Returns:
            发送成功返回 True，超时或关闭返回 False
        """
        if self._closed:
            return False
        try:
            if self._transform_fn is not None:
                item = self._transform_fn(item)
            self._queue.put(item, timeout=timeout if timeout is not None else True)
            return True
        except queue.Full:
            return False

    def recv(self, timeout: Optional[float] = None) -> Optional[_T]:
        """接收数据项。

        Args:
            timeout: 接收超时时间（秒），None 表示无限等待

        Returns:
            数据项，超时或流结束返回 None
        """
        try:
            item = self._queue.get(timeout=timeout if timeout is not None else 0.1)
            if item is self._SENTINEL:
                self._queue.put(self._SENTINEL)
                return None
            return item
        except queue.Empty:
            return None

    def close(self) -> None:
        """关闭流，发送结束标记。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._queue.put_nowait(self._SENTINEL)
            except queue.Full:
                pass

    def __iter__(self) -> Iterator[_T]:
        """迭代接收数据。"""
        while True:
            item = self.recv()
            if item is None:
                break
            yield item

    def __enter__(self) -> "StreamBridge[_T]":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
