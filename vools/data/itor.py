"""
``vools.data.itor`` - 可控迭代器

提供 ``Itor`` 类，将普通可迭代对象包装成一个**线程安全、可控制**的迭代器。

- ``iter(itor)`` / ``next(itor)`` 使用实例本身的状态。
- ``itor()`` 返回一个全新状态的独立副本，可在副本上调用 ``restart()`` 等控制方法而不影响原实例。

支持特性
--------
- **异步线程控制**：``send`` / ``set_pause`` / ``resume`` / ``restart`` / ``stop`` 都可在任意线程中安全调用。
- **断点暂停**：可随时暂停产出，稍后恢复。
- **插队**：
  - 紧急插队：立即插入到下一个产出位置。
  - 条件插队：注册 ``jump_when`` 回调，当条件满足时自动插入。
- **基于历史流的重启**：调用 ``restart()`` 后，会按历史记录重新产出，再续接源迭代器剩余部分。
- **可定制历史策略**：通过 ``history_strategy()`` 或便捷类方法 ``set_history_max()`` 控制历史保留长度。

基本用法
--------
>>> from vools.data import Itor, Node
>>> itor = Itor([1, 2, 3, 4, 5])
>>> list(itor())          # 返回独立副本并迭代，不影响原实例
[1, 2, 3, 4, 5]
>>> list(itor)            # 直接迭代原实例
[1, 2, 3, 4, 5]
>>> itor2 = Itor([7, 8, 9])
>>> next(itor2), next(itor2)
(7, 8)

>>> chain = Node.from_iter([1, 2, 3])
>>> [n.val for n in chain]
[1, 2, 3]
>>> list(chain.to_iter())
[1, 2, 3]
>>> itor = chain.to_itor()
>>> list(itor())
[1, 2, 3]

线程控制示例
------------
>>> import threading, time
>>> itor = Itor(range(100))
>>> results = []
>>> def consumer():
...     for v in itor:          # 直接迭代原实例，控制线程才能影响它
...         results.append(v)
...         time.sleep(0.02)
>>> def controller():
...     time.sleep(0.05)
...     itor.set_pause()
...     itor.send(Node(99))   # 插队 99
...     itor.resume()
...     time.sleep(0.1)
...     itor.stop()
>>> threading.Thread(target=consumer).start()
>>> threading.Thread(target=controller).start()

限制
----
- 一个 ``Itor`` 实例在同一时刻只应存在一个活动迭代。``iter(itor)`` 和 ``next(itor)`` 共享同一状态；``itor()`` 每次返回独立副本，副本与原实例之间状态互不影响（除手动共享 ``Node`` 对象外）。
- 多个副本可同时存在，但源可迭代对象若为一次性生成器/迭代器，则副本之间会共享该源。
- 源迭代器在 ``next()`` 调用期间会阻塞当前消费线程；控制线程仍能立即响应，因为控制方法不依赖该阻塞。
"""

import copy
import threading
from enum import Enum, auto
from typing import Any, Callable, Optional, Iterable, Iterator, List, Tuple, Type

__all__ = ['Node', 'ItorState', 'Itor']


class Node:
    """
    链表节点，用于存储插队值和历史记录值。

    支持**懒加载**：通过 ``from_iter`` 从生成器或无限迭代器创建时，
    不会立即展开整条链表，而是在访问 ``next`` 时按需生成后续节点。

    Attributes:
        val: 节点保存的值。
        next: 下一个节点。对懒加载节点，首次访问时会从底层迭代器取数。

    Example:
        >>> node = Node(42)
        >>> node.val
        42
        >>> node.next = Node(99)
        >>> node.next.val
        99
        >>> chain = Node.from_iter([1, 2, 3])
        >>> [n.val for n in chain]
        [1, 2, 3]
        >>> list(chain.to_iter())
        [1, 2, 3]
        >>> itor = chain.to_itor()
        >>> list(itor())
        [1, 2, 3]

    Lazy example:
        >>> def gen():
        ...     i = 0
        ...     while True:
        ...         yield i
        ...         i += 1
        >>> head = Node.from_iter(gen())
        >>> head.val, head.next.val, head.next.next.val
        (0, 1, 2)
    """

    __slots__ = ('_val', '_next', '_is_replay', '_iterator', '_fallback')

    def __init__(
        self,
        val: Any = None,
        next: Optional['Node'] = None,
        iterator: Optional[Iterator] = None,
        fallback: Optional['Node'] = None,
    ) -> None:
        self._val = val
        self._next: Optional['Node'] = next
        # 标记是否来自历史重放，重放节点不应再次写入历史链表
        self._is_replay = False
        # 懒加载迭代器：next 为 None 时，从此迭代器生成下一个节点
        self._iterator: Optional[Iterator] = iterator
        # 懒加载链表的尾后节点：当 _iterator 耗尽时，自动接上 fallback
        self._fallback: Optional['Node'] = fallback

    @property
    def val(self) -> Any:
        """当前节点保存的值。"""
        return self._val

    @val.setter
    def val(self, value: Any) -> None:
        self._val = value

    @property
    def next(self) -> Optional['Node']:
        """
        下一个节点。

        对懒加载节点，首次访问时会从底层迭代器取数生成下一个节点；
        若迭代器耗尽，则返回 ``fallback``（如果有）。
        """
        if self._next is None:
            if self._iterator is not None:
                try:
                    self._next = Node(
                        next(self._iterator),
                        iterator=self._iterator,
                        fallback=self._fallback,
                    )
                except StopIteration:
                    self._next = self._fallback
                    self._iterator = None
                    self._fallback = None
        return self._next

    @next.setter
    def next(self, node: Optional['Node']) -> None:
        """设置下一个节点。手动设置后会清除懒加载源。"""
        self._next = node
        self._iterator = None
        self._fallback = None

    def __iter__(self):
        """按链表顺序迭代当前节点及其后续节点。"""
        cur: Optional['Node'] = self
        while cur is not None:
            yield cur
            cur = cur.next

    def to_iter(self) -> Iterator[Any]:
        """
        按链表顺序产出节点保存的值。

        Returns:
            一个迭代器，依次产出 ``self`` 及其后续节点的 ``val``。
            对懒加载链表，此迭代器也是懒加载的。

        Example:
            >>> head = Node.from_iter([1, 2, 3])
            >>> list(head.to_iter())
            [1, 2, 3]
        """
        for node in self:
            yield node.val

    def to_itor(self) -> 'Itor':
        """
        将当前 ``Node`` 链表转换为 ``Itor`` 实例。

        Returns:
            一个基于当前链表值的 ``Itor`` 实例，可继续使用暂停、插队、重启等控制。

        Example:
            >>> head = Node.from_iter([1, 2, 3])
            >>> itor = head.to_itor()
            >>> list(itor())
            [1, 2, 3]
        """
        return Itor(self.to_iter())

    @classmethod
    def from_iter(cls, iterable: Iterable) -> Optional['Node']:
        """
        将可迭代对象转换为 ``Node`` 链表。

        对生成器或无限迭代器采用**懒加载**：不会立即展开整条链表，
        而是在访问 ``next`` 时按需生成后续节点。

        Args:
            iterable: 任意可迭代对象，包括生成器和无限迭代器。

        Returns:
            链表头节点。若可迭代对象为空，则返回 ``None``。

        Example:
            >>> head = Node.from_iter([1, 2, 3])
            >>> [n.val for n in head]
            [1, 2, 3]

            >>> def gen():
            ...     i = 0
            ...     while True:
            ...         yield i
            ...         i += 1
            >>> head = Node.from_iter(gen())
            >>> head.next.next.val
            2
        """
        it = iter(iterable)
        try:
            head = cls(next(it))
        except StopIteration:
            return None

        head._iterator = it
        return head


class ItorState(Enum):
    """
    Itor 内部状态。

    - ``PENDING``: 未开始或已重置，等待首次产出。
    - ``ITERRING``: 正在迭代中。
    - ``PAUSED``: 已暂停。
    - ``STOPPED``: 已终止。
    """
    PENDING = auto()
    ITERRING = auto()
    PAUSED = auto()
    STOPPED = auto()


class Itor:
    """
    可控制迭代器（Iterator Controller）。

    将任意可迭代对象包装成支持多线程控制、断点、插队、重启和历史策略的迭代器。
    ``Itor`` 实例本身即是迭代器，支持 ``iter(itor)``、``next(itor)`` 以及
    ``itor()`` 三种用法。其中 ``iter(itor)`` / ``next(itor)`` 直接使用实例
    本身状态；``itor()`` 返回一个独立副本，可在副本上自由控制而不影响原实例。

    Args:
        iterable: 原始可迭代对象。

    Example:
        >>> itor = Itor([1, 2, 3])
        >>> itor.state.name
        'PENDING'
        >>> list(itor)
        [1, 2, 3]
        >>> itor.state.name
        'STOPPED'
        >>> itor2 = Itor([4, 5, 6])
        >>> list(itor2())
        [4, 5, 6]
        >>> itor2.state.name
        'PENDING'
        >>> itor3 = Itor([7, 8])
        >>> next(itor3), next(itor3)
        (7, 8)
    """

    def __init__(self, iterable: Iterable) -> None:
        self._iterable = iterable          # 原始可迭代对象
        self._iterator: Optional[Iterator] = None
        self._state = ItorState.PENDING
        self._lock = threading.Lock()      # 保护内部状态与链表的互斥锁
        self._pause_event = threading.Event()
        self._pause_event.set()            # 初始为非暂停状态

        # 哨兵节点，其 next 始终指向下一个待产出的 Node（插队用）
        self._dummy = Node()
        self._dummy.next = None

        # 历史记录链表（按产出顺序）
        self._history_head: Optional[Node] = None
        self._history_tail: Optional[Node] = None

        # 插队相关
        self._conditional_jumps: List[Tuple[Node, Callable[['Itor'], bool]]] = []

        # 重启重放模式
        self._replay_mode = False
        self._replay_node: Optional[Node] = None   # 当前重放位置

        # 若 restart 发生在源迭代器 next() 阻塞期间，已取到的值先暂存此处
        self._pending_source: Optional[Node] = None

        # 历史策略（None 表示完全保留）
        self._history_strategy: Optional[Callable[['Itor'], None]] = None

        # 内部迭代控制
        self._stop_requested = False

    @property
    def state(self) -> ItorState:
        """当前状态（线程安全）。"""
        with self._lock:
            return self._state

    def send(self, jump: Any, jump_when: Optional[Callable[['Itor'], bool]] = None) -> 'Itor':
        """
        插队函数。

        - ``jump_when`` 为 ``None`` 时，将 ``jump`` 插入到下一个产出位置。
        - 否则注册为条件插队，每次产出前检查，条件满足时插入。

        ``jump`` 参数可为任意类型，内部会按以下规则转换为 ``Node``：

        - 已是 ``Node`` 的实例，直接使用。
        - 可迭代对象（字符串/字节除外）通过 ``Node.from_iter`` 转为链表。
        - 其它类型包装为单节点 ``Node``。

        Args:
            jump: 要插入的值，可为 ``Node``、可迭代对象或任意标量。
            jump_when: 条件函数，接收 ``Itor`` 实例并返回 ``bool``。

        Returns:
            返回 ``self``，支持链式调用。

        Raises:
            RuntimeError: 当迭代器已处于 ``STOPPED`` 状态时。

        Example:
            >>> itor = Itor([1, 2, 3])
            >>> gen = itor()
            >>> next(gen)
            1
            >>> gen.send(Node(99))
            >>> next(gen)
            99
            >>> gen.send(Node.from_iter([88, 89]))  # 插入链表
            >>> next(gen), next(gen)
            (88, 89)
            >>> gen.send([77, 78]).send(76)         # 非 Node 类型自动转换
            >>> next(gen), next(gen), next(gen)
            (77, 78, 76)
        """
        # 将任意类型统一转为 Node
        if not isinstance(jump, Node):
            if isinstance(jump, (str, bytes)):
                jump = Node(jump)
            elif isinstance(jump, Iterable):
                converted = Node.from_iter(jump)
                if converted is None:
                    return self
                jump = converted
            else:
                jump = Node(jump)

        with self._lock:
            if self._state == ItorState.STOPPED:
                raise RuntimeError("迭代器已终止，无法插队")

            if jump_when is None:
                # 紧急插队：将 jump 链表整体插入到 dummy 之后
                self._insert_jump_chain(jump)
            else:
                # 条件插队：暂存，等待条件满足时插入
                self._conditional_jumps.append((jump, jump_when))

        return self

    def set_pause(self) -> 'Itor':
        """
        强制暂停。

        可在任意线程中调用。暂停后当前生成器会在下一次 ``yield`` 后的循环中阻塞，
        直到调用 ``resume()``。

        Returns:
            返回 ``self``，支持链式调用。
        """
        with self._lock:
            if self._state in (ItorState.PENDING, ItorState.ITERRING):
                self._state = ItorState.PAUSED
                self._pause_event.clear()
        return self

    def resume(self) -> 'Itor':
        """恢复暂停状态，使生成器继续产出。

        Returns:
            返回 ``self``，支持链式调用。
        """
        with self._lock:
            if self._state == ItorState.PAUSED:
                self._state = ItorState.ITERRING
                self._pause_event.set()
        return self

    def restart(self) -> 'Itor':
        """
        基于历史流重新开始迭代。

        状态回到 ``PENDING``，并从历史记录头部开始重放。重放结束后继续源迭代器
        未消费的部分。任何状态（包括 ``STOPPED``）均可调用。

        Returns:
            返回 ``self``，支持链式调用。

        Example:
            >>> itor = Itor([1, 2, 3])
            >>> gen = itor()
            >>> next(gen), next(gen)
            (1, 2)
            >>> gen.restart()
            >>> list(gen)
            [1, 2, 3]
        """
        with self._lock:
            self._state = ItorState.PENDING
            self._pause_event.set()           # 清除暂停信号
            self._stop_requested = False

            # 启用重放模式，从历史头部开始
            self._replay_mode = True
            self._replay_node = self._history_head
            # 清空 dummy 之后可能残留的插队节点，重新构建产出顺序
            self._dummy.next = None
            # 清空待处理的条件插队（重启视为新生命周期）
            self._conditional_jumps.clear()
        return self

    def history_strategy(self, strategy: Optional[Callable[['Itor'], None]]) -> 'Itor':
        """
        设置历史保留策略。

        ``strategy`` 为 ``None`` 表示完全保留。策略函数接收 ``Itor`` 实例，
        在每次产出值后调用，可实现完全丢弃、长度限制、时间过期等。

        Args:
            strategy: 历史处理回调函数，或 ``None`` 清除策略。

        Returns:
            返回 ``self``，支持链式调用。

        See Also:
            :meth:`set_history_max`：更便捷的类方法，用于设置“最多保留 N 条”。
        """
        with self._lock:
            self._history_strategy = strategy
        return self

    @classmethod
    def set_history_max(cls, itor: 'Itor', max_len: int) -> Type['Itor']:
        """
        类方法：为指定 ``Itor`` 实例设置“最大历史长度”策略。

        Args:
            itor: 目标 ``Itor`` 实例。
            max_len: 最大保留历史条数。
                - ``-1`` 表示完全保留（清除已有策略）。
                - ``>= 0`` 表示最多保留最近 ``max_len`` 条。

        Returns:
            返回 ``Itor`` 类本身，支持链式类方法调用。

        Raises:
            TypeError: ``max_len`` 不是整数。
            ValueError: ``max_len < -1``。

        Example:
            >>> itor = Itor([1, 2, 3, 4, 5])
            >>> Itor.set_history_max(itor, 3)
            >>> gen = itor()
            >>> list(gen)
            [1, 2, 3, 4, 5]
            >>> gen.restart()
            >>> list(gen)
            [3, 4, 5]
        """
        if not isinstance(max_len, int):
            raise TypeError("max_len must be an integer")
        if max_len < -1:
            raise ValueError("max_len must be >= -1")

        if max_len == -1:
            itor.history_strategy(None)
            return cls

        def keep_last(itor: 'Itor') -> None:
            count = 0
            cur = itor._history_head
            while cur:
                count += 1
                cur = cur.next
            while count > max_len and itor._history_head is not None:
                itor._history_head = itor._history_head.next
                count -= 1
            if itor._history_head is None:
                itor._history_tail = None

        itor.history_strategy(keep_last)
        return cls

    def stop(self) -> 'Itor':
        """
        终止迭代器。

        可在任意线程中调用。已阻塞的生成器会被唤醒并终止。

        Returns:
            返回 ``self``，支持链式调用。
        """
        with self._lock:
            self._state = ItorState.STOPPED
            self._pause_event.set()  # 唤醒可能正在等待的生成器
            self._stop_requested = True
        return self

    def __copy__(self) -> 'Itor':
        """
        创建当前 ``Itor`` 的一个浅拷贝副本。

        新实例拥有独立的锁、暂停事件、历史链表、插队队列和迭代状态，
        状态重置为 ``PENDING``；但共享源可迭代对象引用和历史策略函数。
        若手动向原实例和副本发送同一个 ``Node`` 对象，该 ``Node`` 的
        后续链表可能被相互修改，这是唯一可能相互影响的地方。

        Returns:
            一个状态全新的 ``Itor`` 副本。
        """
        new = self.__class__(self._iterable)
        new._history_strategy = self._history_strategy
        return new

    def __call__(self) -> 'Itor':
        """
        返回当前 ``Itor`` 的一个全新状态副本。

        与 ``iter(itor)`` / ``next(itor)`` 不同，``itor()`` 每次调用都会
        返回一个独立副本，在其上调用 ``restart()`` / ``send()`` 等控制
        方法不会影响原实例。

        Returns:
            一个状态全新的 ``Itor`` 副本。
        
        已知限制:
        若源可迭代对象是一次性生成器/迭代器（如 Node.to_itor() 内部使用的 to_iter() 生成器），副本之间会共享该底层迭代器。对于 list、range 等可重复迭代对象，各副本完全独立。
        手动向原实例和副本发送同一个 Node 对象时，该 Node 的链表可能被相互修改。
        """
        return copy.copy(self)

    def __iter__(self):
        """使 ``Itor`` 实例本身成为可迭代对象。``iter(itor)`` 与 ``next(itor)`` 共享实例状态。"""
        return self

    def __next__(self) -> Any:
        """
        获取下一个值。

        迭代结束时抛出 ``StopIteration``，并将状态设为 ``STOPPED``。
        """
        return self._next_value()

    def _next_value(self) -> Any:
        """
        线程安全地获取下一个值。

        首次调用时会自动初始化源迭代器。迭代结束时抛出 ``StopIteration``
        并将状态设为 ``STOPPED``。
        """
        # 初始化源迭代器（若尚未创建），并将状态切为 ITERRING
        with self._lock:
            if self._iterator is None:
                self._iterator = iter(self._iterable)
            if self._state == ItorState.PENDING:
                self._state = ItorState.ITERRING

        try:
            # 等待暂停恢复
            self._pause_event.wait()
            with self._lock:
                if self._state == ItorState.STOPPED or self._stop_requested:
                    raise StopIteration

            # 处理条件插队
            self._process_conditional_jumps()

            # 获取下一个产出节点
            node = self._get_next_node()
            if node is None:
                with self._lock:
                    self._state = ItorState.STOPPED
                raise StopIteration

            # 产出值
            val = node.val

            # 产出后维护历史与链表
            with self._lock:
                # 重放节点不再重复写入历史，避免链表成环
                if not getattr(node, '_is_replay', False):
                    self._add_history(node)
                # 应用历史策略
                if self._history_strategy:
                    self._history_strategy(self)

            return val

        except StopIteration:
            with self._lock:
                if self._state != ItorState.STOPPED:
                    self._state = ItorState.STOPPED
            raise

    # ---------- 内部方法 ----------
    def _insert_jump_chain(self, jump: Node) -> None:
        """
        将 ``jump`` 节点及其后续链表整体插入到 dummy 之后（调用时持有锁）。

        对普通链表会遍历到尾节点再连接；对懒加载/无限链表则直接设置
        ``fallback``，避免无法穷举到尾节点。
        """
        if jump._iterator is not None:
            # 懒加载/无限链表：无法遍历到尾，设置 fallback 后插入头部
            jump._fallback = self._dummy.next
            self._dummy.next = jump
            return

        tail = jump
        while tail.next is not None:
            tail = tail.next
        tail.next = self._dummy.next
        self._dummy.next = jump

    def _process_conditional_jumps(self) -> None:
        """检查并插入所有满足条件的插队节点（调用时持有锁）。"""
        with self._lock:
            i = 0
            while i < len(self._conditional_jumps):
                node, condition = self._conditional_jumps[i]
                try:
                    if condition(self):
                        # 满足条件：插入整条链表
                        self._insert_jump_chain(node)
                        # 移除该条件插队
                        self._conditional_jumps.pop(i)
                        continue
                except Exception:
                    # 条件异常则移除该插队
                    self._conditional_jumps.pop(i)
                    continue
                i += 1

    def _get_next_node(self) -> Optional[Node]:
        """
        获取下一个待产出的节点。

        取值顺序：紧急插队 -> 历史重放 -> 待处理源值 -> 源迭代器。
        返回 ``None`` 表示没有更多数据。

        注意：调用源迭代器 ``next()`` 时**不持有 ``self.__lock``**，
        避免阻塞型源迭代器导致控制线程死锁。
        """
        with self._lock:
            # 1. 紧急插队节点优先
            if self._dummy.next is not None:
                node = self._dummy.next
                self._dummy.next = node.next
                node.next = None
                return node

            # 2. 重放模式：从历史链表逐个重放
            if self._replay_mode:
                if self._replay_node is not None:
                    val = self._replay_node.val
                    self._replay_node = self._replay_node.next
                    node = Node(val)
                    node._is_replay = True
                    return node
                else:
                    # 历史重放结束，切换回正常模式
                    self._replay_mode = False

            # 3. 在源 next() 阻塞期间若发生 restart，已取到的值暂存于此
            if self._pending_source is not None:
                node = self._pending_source
                self._pending_source = None
                return node

            # 4. 需要调用源迭代器
            if self._iterator is None:
                return None
            iterator = self._iterator

        # 5. 在锁外调用源迭代器，防止阻塞型源导致死锁
        try:
            val = next(iterator)
        except StopIteration:
            return None
        except RuntimeError:  # 迭代器被并发修改等异常
            return None

        # 6. 重新加锁，检查取数期间是否发生了 restart
        with self._lock:
            if self._replay_mode:
                # 取数期间被 restart：保存该值，等重放结束后再产出
                self._pending_source = Node(val)
                if self._replay_node is not None:
                    val = self._replay_node.val
                    self._replay_node = self._replay_node.next
                    node = Node(val)
                    node._is_replay = True
                    return node
                else:
                    # 历史为空，直接产出刚才取到的值
                    node = self._pending_source
                    self._pending_source = None
                    self._replay_mode = False
                    return node
            return Node(val)

    # ---- serialization support ----

    def __getstate__(self):
        """return serialization state (exclude non-serializable fields)"""
        exclude = {'_lock', '_pause_event', '_iterator'}
        return {k: v for k, v in self.__dict__.items() if k not in exclude}

    def __setstate__(self, state):
        """restore from serialization state, recreate non-serializable fields"""
        self.__dict__.update(state)
        import threading
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._iterator = None
        self._stop_requested = False


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
    def _add_history(self, node: Node) -> None:
        """将节点加入历史链表尾（必须持有锁）。"""
        node.next = None
        if self._history_tail is None:
            self._history_head = node
            self._history_tail = node
        else:
            self._history_tail.next = node
            self._history_tail = node



# 向后兼容别名：旧代码中直接使用 State 仍可用，但推荐改用 ItorState
State = ItorState
