"""
vools.concurrent.queues - 队列高级封装

对 Python 标准库的队列和双端队列进行高级封装，提供更丰富的 API 和关闭语义。

主要组件：
    VQueue        - 增强版 FIFO 队列
    VPriorityQueue - 优先队列
    VLifoQueue    - LIFO 栈式队列
    VDeque        - 线程安全双端队列
    BoundedChannel - 有界通道（生产者消费者模式，带关闭语义）
    merge_queues  - 合并多个队列，轮询读取
    queue_to_generator - 将队列转为生成器
"""

from __future__ import annotations

import heapq
import queue
import threading
from collections import deque
from typing import Any, Callable, Generator, Iterable, List, Optional, Tuple, TypeVar

__all__ = [
    "VQueue",
    "VPriorityQueue",
    "VLifoQueue",
    "VDeque",
    "BoundedChannel",
    "merge_queues",
    "queue_to_generator",
]

_T = TypeVar("_T")


# ============================================================================
# VQueue - 增强版 FIFO 队列
# ============================================================================


class VQueue:
    """增强版 FIFO 队列，基于 ``queue.Queue``。

    在标准队列基础上增加：
        - 超时版 put/get：``put_timeout`` / ``get_timeout``
        - 查看队首：``peek``
        - 转列表：``to_list``
        - 清空：``clear``
        - 状态查询：``is_full`` / ``is_empty``
        - 批量操作：``put_many`` / ``get_many``

    示例::

        q = VQueue(maxsize=10)
        q.put_timeout(item, timeout=1.0)
        item = q.get_timeout(timeout=1.0)
        first = q.peek()
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: "queue.Queue[_T]" = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 基础操作
    # ------------------------------------------------------------------
    def put(self, item: _T, block: bool = True, timeout: Optional[float] = None) -> None:
        """放入元素。

        Args:
            item: 要放入的元素。
            block: 是否阻塞等待。
            timeout: 阻塞超时（秒），``None`` 表示无限等待。
        """
        self._queue.put(item, block=block, timeout=timeout)

    def put_timeout(self, item: _T, timeout: float) -> bool:
        """尝试在指定时间内放入元素。

        Args:
            item: 要放入的元素。
            timeout: 超时时间（秒）。

        Returns:
            bool: 是否成功放入。
        """
        try:
            self._queue.put(item, timeout=timeout)
            return True
        except queue.Full:
            return False

    def get(self, block: bool = True, timeout: Optional[float] = None) -> _T:
        """取出元素。

        Args:
            block: 是否阻塞等待。
            timeout: 阻塞超时（秒），``None`` 表示无限等待。

        Returns:
            取出的元素。
        """
        return self._queue.get(block=block, timeout=timeout)

    def get_timeout(self, timeout: float) -> Optional[_T]:
        """尝试在指定时间内取出元素。

        Args:
            timeout: 超时时间（秒）。

        Returns:
            取出的元素，超时返回 ``None``。
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def peek(self) -> Optional[_T]:
        """查看队首元素，不移除。

        Returns:
            队首元素，队列为空时返回 ``None``。
        """
        with self._queue.mutex:
            if self._queue.queue:
                return self._queue.queue[0]
            return None

    def task_done(self) -> None:
        """标记任务完成（用于消费者通知 join）。"""
        self._queue.task_done()

    def join(self) -> None:
        """阻塞直到队列中所有任务都被标记为完成。"""
        self._queue.join()

    # ------------------------------------------------------------------
    # 批量操作
    # ------------------------------------------------------------------
    def put_many(self, items: Iterable[_T], timeout: Optional[float] = None) -> int:
        """批量放入元素。

        Args:
            items: 可迭代的元素序列。
            timeout: 每个元素的放入超时（秒），``None`` 表示无限等待。

        Returns:
            int: 成功放入的元素数量。
        """
        count = 0
        for item in items:
            if timeout is None:
                self._queue.put(item)
                count += 1
            else:
                if self.put_timeout(item, timeout):
                    count += 1
                else:
                    break
        return count

    def get_many(self, n: int, timeout: Optional[float] = None) -> List[_T]:
        """批量取出元素。

        Args:
            n: 最多取出的元素数量。
            timeout: 每个元素的取出超时（秒），``None`` 表示仅取当前可用的。

        Returns:
            List[_T]: 取出的元素列表。
        """
        items: List[_T] = []
        for _ in range(n):
            if timeout is None:
                try:
                    items.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            else:
                try:
                    items.append(self._queue.get(timeout=timeout))
                except queue.Empty:
                    break
        return items

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def qsize(self) -> int:
        """返回队列当前大小（近似值）。"""
        return self._queue.qsize()

    def is_empty(self) -> bool:
        """队列是否为空。"""
        return self._queue.empty()

    def is_full(self) -> bool:
        """队列是否已满。"""
        return self._queue.full()

    def clear(self) -> None:
        """清空队列。"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def to_list(self) -> List[_T]:
        """将队列内容转为列表（不消耗队列）。

        Returns:
            List[_T]: 队列元素的列表副本。
        """
        with self._queue.mutex:
            return list(self._queue.queue)

    @property
    def maxsize(self) -> int:
        """队列最大容量。"""
        return self._queue.maxsize

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------
    def __enter__(self) -> "VQueue[_T]":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.clear()
        return False

    def __len__(self) -> int:
        return self.qsize()

    def __bool__(self) -> bool:
        return not self.is_empty()

    def __repr__(self) -> str:
        return f"<VQueue size={self.qsize()} maxsize={self.maxsize}>"


# ============================================================================
# VPriorityQueue - 优先队列
# ============================================================================


class VPriorityQueue:
    """优先队列，基于 ``heapq`` 实现，线程安全。

    小顶堆：优先级数值越小，优先级越高，越先出队。

    示例::

        pq = VPriorityQueue()
        pq.put("low priority", priority=10)
        pq.put("high priority", priority=1)
        item = pq.get()  # "high priority"
    """

    def __init__(self) -> None:
        self._heap: List[Tuple[float, int, _T]] = []
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._counter = 0

    # ------------------------------------------------------------------
    # 基础操作
    # ------------------------------------------------------------------
    def put(self, item: _T, priority: float = 0) -> None:
        """放入元素。

        Args:
            item: 要放入的元素。
            priority: 优先级，数值越小优先级越高。
        """
        with self._not_empty:
            self._counter += 1
            heapq.heappush(self._heap, (priority, self._counter, item))
            self._not_empty.notify()

    def get(self, block: bool = True, timeout: Optional[float] = None) -> _T:
        """取出最高优先级的元素。

        Args:
            block: 是否阻塞等待。
            timeout: 阻塞超时（秒）。

        Returns:
            取出的元素。

        Raises:
            IndexError: 队列为空且不阻塞时。
        """
        with self._not_empty:
            if not self._heap:
                if not block:
                    raise IndexError("get from empty priority queue")
                if not self._not_empty.wait(timeout=timeout):
                    raise IndexError("get from empty priority queue (timeout)")
            _, _, item = heapq.heappop(self._heap)
            return item

    def get_timeout(self, timeout: float) -> Optional[_T]:
        """尝试在指定时间内取出最高优先级的元素。

        Args:
            timeout: 超时时间（秒）。

        Returns:
            取出的元素，超时返回 ``None``。
        """
        try:
            return self.get(block=True, timeout=timeout)
        except IndexError:
            return None

    def peek(self) -> Optional[_T]:
        """查看最高优先级的元素，不移除。

        Returns:
            最高优先级元素，队列为空时返回 ``None``。
        """
        with self._lock:
            if not self._heap:
                return None
            return self._heap[0][2]

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def qsize(self) -> int:
        """返回队列当前大小。"""
        with self._lock:
            return len(self._heap)

    def is_empty(self) -> bool:
        """队列是否为空。"""
        with self._lock:
            return len(self._heap) == 0

    def clear(self) -> None:
        """清空队列。"""
        with self._not_empty:
            self._heap.clear()

    def to_list(self) -> List[_T]:
        """将队列内容转为列表（按优先级排序，不消耗队列）。

        Returns:
            List[_T]: 按优先级排序的元素列表。
        """
        with self._lock:
            sorted_heap = sorted(self._heap)
            return [item for _, _, item in sorted_heap]

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------
    def __enter__(self) -> "VPriorityQueue[_T]":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.clear()
        return False

    def __len__(self) -> int:
        return self.qsize()

    def __bool__(self) -> bool:
        return not self.is_empty()

    def __repr__(self) -> str:
        return f"<VPriorityQueue size={self.qsize()}>"


# ============================================================================
# VLifoQueue - LIFO 栈式队列
# ============================================================================


class VLifoQueue:
    """LIFO 栈式队列（后进先出）。

    基于 ``queue.LifoQueue`` 的增强封装。

    示例::

        s = VLifoQueue()
        s.put(1)
        s.put(2)
        s.get()  # 2
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._stack: "queue.LifoQueue[_T]" = queue.LifoQueue(maxsize=maxsize)

    # ------------------------------------------------------------------
    # 基础操作
    # ------------------------------------------------------------------
    def put(self, item: _T, block: bool = True, timeout: Optional[float] = None) -> None:
        """压入元素。"""
        self._stack.put(item, block=block, timeout=timeout)

    def put_timeout(self, item: _T, timeout: float) -> bool:
        """尝试在指定时间内压入元素。"""
        try:
            self._stack.put(item, timeout=timeout)
            return True
        except queue.Full:
            return False

    def get(self, block: bool = True, timeout: Optional[float] = None) -> _T:
        """弹出元素。"""
        return self._stack.get(block=block, timeout=timeout)

    def get_timeout(self, timeout: float) -> Optional[_T]:
        """尝试在指定时间内弹出元素。"""
        try:
            return self._stack.get(timeout=timeout)
        except queue.Empty:
            return None

    def peek(self) -> Optional[_T]:
        """查看栈顶元素，不弹出。"""
        with self._stack.mutex:
            if self._stack.queue:
                return self._stack.queue[-1]
            return None

    def push(self, item: _T) -> None:
        """压入元素（put 的别名）。"""
        self.put(item)

    def pop(self) -> _T:
        """弹出元素（get 的别名）。"""
        return self.get()

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def qsize(self) -> int:
        """返回栈当前大小。"""
        return self._stack.qsize()

    def is_empty(self) -> bool:
        """栈是否为空。"""
        return self._stack.empty()

    def is_full(self) -> bool:
        """栈是否已满。"""
        return self._stack.full()

    def clear(self) -> None:
        """清空栈。"""
        while not self._stack.empty():
            try:
                self._stack.get_nowait()
            except queue.Empty:
                break

    def to_list(self) -> List[_T]:
        """将栈内容转为列表（栈顶在前，不消耗栈）。"""
        with self._stack.mutex:
            return list(reversed(self._stack.queue))

    @property
    def maxsize(self) -> int:
        """栈最大容量。"""
        return self._stack.maxsize

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------
    def __enter__(self) -> "VLifoQueue[_T]":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.clear()
        return False

    def __len__(self) -> int:
        return self.qsize()

    def __bool__(self) -> bool:
        return not self.is_empty()

    def __repr__(self) -> str:
        return f"<VLifoQueue size={self.qsize()} maxsize={self.maxsize}>"


# ============================================================================
# VDeque - 线程安全双端队列
# ============================================================================


class VDeque:
    """线程安全的双端队列，基于 ``collections.deque``。

    支持两端的高效插入和删除，以及旋转等操作。

    示例::

        dq = VDeque(maxlen=10)
        dq.append_right(1)
        dq.append_left(0)
        dq.pop_right()  # 1
        dq.pop_left()   # 0
    """

    def __init__(
        self,
        iterable: Optional[Iterable[_T]] = None,
        maxlen: Optional[int] = None,
    ) -> None:
        if iterable is not None:
            self._deque: deque[_T] = deque(iterable, maxlen=maxlen)
        else:
            self._deque = deque(maxlen=maxlen)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 左端操作
    # ------------------------------------------------------------------
    def append_left(self, item: _T) -> None:
        """在左端添加元素。"""
        with self._lock:
            self._deque.appendleft(item)

    def append_left_many(self, items: Iterable[_T]) -> None:
        """在左端批量添加元素（按迭代顺序，第一个元素最后在最左端）。"""
        with self._lock:
            for item in items:
                self._deque.appendleft(item)

    def pop_left(self) -> _T:
        """从左端弹出元素。

        Raises:
            IndexError: 队列为空时。
        """
        with self._lock:
            return self._deque.popleft()

    def pop_left_timeout(self, timeout: float) -> Optional[_T]:
        """尝试在指定时间内从左端弹出元素。

        Args:
            timeout: 超时时间（秒）。

        Returns:
            弹出的元素，超时返回 ``None``。
        """
        import time

        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                if self._deque:
                    return self._deque.popleft()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(remaining, 0.01))

    def peek_left(self) -> Optional[_T]:
        """查看左端元素，不弹出。"""
        with self._lock:
            if not self._deque:
                return None
            return self._deque[0]

    # ------------------------------------------------------------------
    # 右端操作
    # ------------------------------------------------------------------
    def append_right(self, item: _T) -> None:
        """在右端添加元素。"""
        with self._lock:
            self._deque.append(item)

    def append_right_many(self, items: Iterable[_T]) -> None:
        """在右端批量添加元素。"""
        with self._lock:
            self._deque.extend(items)

    def pop_right(self) -> _T:
        """从右端弹出元素。

        Raises:
            IndexError: 队列为空时。
        """
        with self._lock:
            return self._deque.pop()

    def pop_right_timeout(self, timeout: float) -> Optional[_T]:
        """尝试在指定时间内从右端弹出元素。

        Args:
            timeout: 超时时间（秒）。

        Returns:
            弹出的元素，超时返回 ``None``。
        """
        import time

        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                if self._deque:
                    return self._deque.pop()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(remaining, 0.01))

    def peek_right(self) -> Optional[_T]:
        """查看右端元素，不弹出。"""
        with self._lock:
            if not self._deque:
                return None
            return self._deque[-1]

    # ------------------------------------------------------------------
    # 其它操作
    # ------------------------------------------------------------------
    def rotate(self, n: int = 1) -> None:
        """旋转队列。

        正数向右旋转（右端元素移到左端），负数向左旋转。

        Args:
            n: 旋转步数。
        """
        with self._lock:
            self._deque.rotate(n)

    def reverse(self) -> None:
        """反转队列。"""
        with self._lock:
            self._deque.reverse()

    def clear(self) -> None:
        """清空队列。"""
        with self._lock:
            self._deque.clear()

    def count(self, item: _T) -> int:
        """统计元素出现次数。"""
        with self._lock:
            return self._deque.count(item)

    def remove(self, item: _T) -> None:
        """移除第一个匹配的元素。

        Raises:
            ValueError: 元素不存在时。
        """
        with self._lock:
            self._deque.remove(item)

    def __contains__(self, item: object) -> bool:
        with self._lock:
            return item in self._deque

    def __len__(self) -> int:
        with self._lock:
            return len(self._deque)

    def __bool__(self) -> bool:
        with self._lock:
            return len(self._deque) > 0

    def __getitem__(self, index: int) -> _T:
        with self._lock:
            return self._deque[index]

    def __iter__(self) -> Generator[_T, None, None]:
        with self._lock:
            items = list(self._deque)
        for item in items:
            yield item

    def __reversed__(self) -> Generator[_T, None, None]:
        with self._lock:
            items = list(reversed(self._deque))
        for item in items:
            yield item

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    @property
    def maxlen(self) -> Optional[int]:
        """最大长度限制。"""
        return self._deque.maxlen

    def is_empty(self) -> bool:
        """队列是否为空。"""
        with self._lock:
            return len(self._deque) == 0

    def is_full(self) -> bool:
        """队列是否已满（仅当设置了 maxlen 时有意义）。"""
        with self._lock:
            if self._deque.maxlen is None:
                return False
            return len(self._deque) >= self._deque.maxlen

    def to_list(self) -> List[_T]:
        """转为列表。"""
        with self._lock:
            return list(self._deque)

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------
    def __enter__(self) -> "VDeque[_T]":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.clear()
        return False

    def __repr__(self) -> str:
        with self._lock:
            return f"<VDeque size={len(self._deque)} maxlen={self._deque.maxlen}>"


# ============================================================================
# BoundedChannel - 有界通道
# ============================================================================


class ChannelClosedError(Exception):
    """通道已关闭异常。"""


class BoundedChannel:
    """有界通道，支持生产者消费者模式，带关闭语义。

    与普通队列的区别：
        - 通道可以 ``close()``，关闭后无法再发送
        - 接收方在通道关闭且数据读完后会收到 ``None``（或抛出异常）
        - 支持 ``for item in channel:`` 迭代

    示例::

        ch = BoundedChannel(maxsize=10)

        def producer():
            for i in range(5):
                ch.send(i)
            ch.close()

        def consumer():
            for item in ch:
                print(item)
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: "queue.Queue[_T]" = queue.Queue(maxsize=maxsize)
        self._closed = False
        self._lock = threading.Lock()
        self._close_event = threading.Event()

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------
    def send(self, item: _T, timeout: Optional[float] = None) -> None:
        """发送数据到通道。

        Args:
            item: 要发送的数据。
            timeout: 发送超时（秒），``None`` 表示无限等待。

        Raises:
            ChannelClosedError: 通道已关闭时。
            queue.Full: 超时队列仍满时。
        """
        if self._closed:
            raise ChannelClosedError("Cannot send on closed channel")
        self._queue.put(item, timeout=timeout)

    def send_timeout(self, item: _T, timeout: float) -> bool:
        """尝试在指定时间内发送数据。

        Args:
            item: 要发送的数据。
            timeout: 超时时间（秒）。

        Returns:
            bool: 是否成功发送。

        Raises:
            ChannelClosedError: 通道已关闭时。
        """
        if self._closed:
            raise ChannelClosedError("Cannot send on closed channel")
        try:
            self._queue.put(item, timeout=timeout)
            return True
        except queue.Full:
            return False

    # ------------------------------------------------------------------
    # 接收
    # ------------------------------------------------------------------
    def recv(self, timeout: Optional[float] = None) -> Optional[_T]:
        """从通道接收数据。

        Args:
            timeout: 接收超时（秒），``None`` 表示无限等待。

        Returns:
            接收到的数据；通道关闭且已空时返回 ``None``。

        Raises:
            queue.Empty: 超时时。
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            if self._closed and self._queue.empty():
                return None
            raise

    def recv_timeout(self, timeout: float) -> Optional[_T]:
        """尝试在指定时间内接收数据。

        Args:
            timeout: 超时时间（秒）。

        Returns:
            接收到的数据；超时或通道关闭时返回 ``None``。
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------
    def close(self) -> None:
        """关闭通道。关闭后不能再发送，但可以继续接收剩余数据。"""
        with self._lock:
            if not self._closed:
                self._closed = True
                self._close_event.set()

    @property
    def is_closed(self) -> bool:
        """通道是否已关闭。"""
        return self._closed

    def wait_closed(self, timeout: Optional[float] = None) -> bool:
        """等待通道被关闭。

        Args:
            timeout: 等待超时（秒）。

        Returns:
            bool: 是否已关闭。
        """
        return self._close_event.wait(timeout=timeout)

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def qsize(self) -> int:
        """返回通道当前大小。"""
        return self._queue.qsize()

    def is_empty(self) -> bool:
        """通道是否为空。"""
        return self._queue.empty()

    def is_full(self) -> bool:
        """通道是否已满。"""
        return self._queue.full()

    @property
    def maxsize(self) -> int:
        """通道最大容量。"""
        return self._queue.maxsize

    # ------------------------------------------------------------------
    # 迭代
    # ------------------------------------------------------------------
    def __iter__(self) -> Generator[_T, None, None]:
        while True:
            try:
                item = self._queue.get(timeout=0.1)
                yield item
            except queue.Empty:
                if self._closed and self._queue.empty():
                    return
                if not self._closed:
                    continue
                return

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------
    def __enter__(self) -> "BoundedChannel[_T]":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.close()
        return False

    def __len__(self) -> int:
        return self.qsize()

    def __bool__(self) -> bool:
        return not self.is_empty() or not self._closed

    def __repr__(self) -> str:
        state = "closed" if self._closed else "open"
        return f"<BoundedChannel {state} size={self.qsize()} maxsize={self.maxsize}>"


# ============================================================================
# 工具函数
# ============================================================================


def merge_queues(
    queues: Iterable[Any],
    timeout: Optional[float] = None,
    round_robin: bool = True,
) -> Generator[Any, None, None]:
    """合并多个队列，轮询读取。

    Args:
        queues: 队列列表，每个队列需支持 ``get(block, timeout)`` 方法。
        timeout: 每个队列的读取超时（秒），``None`` 表示非阻塞轮询。
        round_robin: 是否轮询（True）或按顺序优先读取前面的队列（False）。

    Yields:
        从队列中读取到的元素。

    示例::

        q1, q2 = VQueue(), VQueue()
        for item in merge_queues([q1, q2], timeout=0.1):
            print(item)
    """
    queue_list = list(queues)
    if not queue_list:
        return

    idx = 0
    while True:
        got_item = False
        start_idx = idx

        for _ in range(len(queue_list)):
            q = queue_list[idx]
            try:
                if timeout is None:
                    item = q.get(block=False)
                else:
                    item = q.get(timeout=timeout)
                yield item
                got_item = True
            except (queue.Empty, IndexError):
                pass

            if round_robin:
                idx = (idx + 1) % len(queue_list)
            else:
                idx = 0

            if got_item and not round_robin:
                break

        if not got_item and timeout is None:
            return

        if not round_robin and idx == start_idx and not got_item:
            if timeout is None:
                return


def queue_to_generator(
    q: Any,
    timeout: Optional[float] = None,
    sentinel: Any = None,
) -> Generator[Any, None, None]:
    """将队列转为生成器。

    持续从队列中取出元素，直到遇到哨兵值或超时。

    Args:
        q: 队列对象，需支持 ``get(block, timeout)`` 方法。
        timeout: 每次读取的超时（秒），``None`` 表示阻塞等待。
        sentinel: 哨兵值，遇到此值则停止迭代。

    Yields:
        从队列中读取到的元素。

    示例::

        q = VQueue()
        for item in queue_to_generator(q, timeout=0.5):
            print(item)
    """
    while True:
        try:
            if timeout is None:
                item = q.get()
            else:
                item = q.get(timeout=timeout)
            if item is sentinel:
                return
            yield item
        except (queue.Empty, IndexError):
            if timeout is not None:
                return
