"""tests/concurrent/test_bridges.py — 桥接工具测试"""
import pytest
import queue
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.concurrent.bridges import (
    PipePair, ThreadProcessBridge, ChannelBridge, QueueBridge,
    SharedBridge, EventBridge, StreamBridge, bridge_queues,
)


def _new_bridge(**kw):
    """构造 SharedBridge，兼容 Python < 3.8。

    Python >= 3.8：返回真实实例。
    Python < 3.8：``multiprocessing.shared_memory`` 不存在，SharedBridge.__init__
    必须**明确抛出 NotImplementedError**（这正是设计契约——不支持时显式报错，
    而不是静默坏掉）。这里用 pytest.raises 断言这个契约，并返回 None。
    """
    if sys.version_info >= (3, 8):
        return SharedBridge(**kw)
    with pytest.raises(NotImplementedError):
        SharedBridge(**kw)
    return None


class TestPipePair:
    """PipePair 管道对测试"""

    def test_creation(self):
        pp = PipePair()
        assert pp is not None

    def test_a_and_b(self):
        pp = PipePair()
        assert pp.a is not None
        assert pp.b is not None

    def test_close(self):
        pp = PipePair()
        pp.close()
        assert True  # 无异常即通过

    def test_context_manager(self):
        with PipePair() as pp:
            assert pp.a is not None
        assert True  # 无异常即通过


class TestThreadProcessBridge:
    """ThreadProcessBridge 线程-进程桥接测试"""

    def test_creation(self):
        b = ThreadProcessBridge()
        assert b is not None

    def test_send_recv_thread_side(self):
        # 线程侧发 → 进程侧收（ThreadProcessBridge 的文档语义就是跨侧通信：
        # 线程侧用管道 a 端、进程侧用 b 端）。这里过去写成「线程侧发、线程侧收」——
        # 同一个 a 端自发自收，duplex Pipe 上 a.send 的数据只会出现在 b 端，
        # a.recv() 因此**永久阻塞**（不是失败而是挂死，整条 pytest 会话被拖住）。
        # 传 timeout 让任何回归变成「快速失败」而不是「无限等待」。
        b = ThreadProcessBridge()
        b.send_thread_side('hello')
        assert b.recv_process_side(timeout=2.0) == 'hello'

    def test_send_recv_process_side(self):
        # 进程侧发 → 线程侧收（反向跨侧，与上一条成对覆盖两个方向）
        b = ThreadProcessBridge()
        b.send_process_side('world')
        assert b.recv_thread_side(timeout=2.0) == 'world'

    def test_send_unpicklable_returns_false_not_crash(self):
        """BUG-191: ThreadProcessBridge 两侧 send 对 lambda 原抛 AttributeError，
        现应返回 False。"""
        b = ThreadProcessBridge()
        try:
            assert b.send_thread_side(lambda: 1) is False
            assert b.send_process_side(lambda: 1) is False
        finally:
            b.close()

    def test_close(self):
        b = ThreadProcessBridge()
        b.close()
        assert True  # 无异常即通过


class TestChannelBridge:
    """ChannelBridge 通道桥接测试"""

    def test_creation(self):
        b = ChannelBridge()
        assert b is not None

    def test_connection(self):
        b = ChannelBridge()
        assert b.connection is not None

    def test_send_recv(self):
        # ChannelBridge 是**跨进程**通道：本端 send 的消息由 peer_connection（对端）收到。
        # 过去写成「同一实例 send 后立刻 recv」——本端 a 端发、a 端收，duplex Pipe 上
        # 消息只出现在对端，本端 recv() 因此永久阻塞（挂死而非失败）。
        b = ChannelBridge()
        b.send('test')
        assert b.peer_connection.recv() == 'test'

    def test_recv_from_peer(self):
        # 反向：对端 send → 本端 recv
        b = ChannelBridge()
        b.peer_connection.send('from_peer')
        assert b.recv(timeout=2.0) == 'from_peer'

    def test_send_unpicklable_returns_false_not_crash(self):
        """BUG-191: send 对不可 pickle 对象（lambda/file handle）原抛未捕获
        AttributeError/TypeError，现应返回 False。"""
        b = ChannelBridge()
        try:
            assert b.send(lambda: 1) is False
            with open(__file__, encoding='utf-8') as fh:
                assert b.send(fh) is False
        finally:
            b.close()

    def test_send_pickle_unpicklable_returns_false(self):
        """BUG-191: send_pickle 对 lambda 原抛 AttributeError，现返回 False。"""
        b = ChannelBridge()
        try:
            assert b.send_pickle(lambda: 1) is False
        finally:
            b.close()

    def test_send_json_recv_json(self):
        b = ChannelBridge()
        b.send_json({'key': 'value'})
        assert b.peer_connection.recv() == ('__json__', '{"key": "value"}')

    def test_recv_json_from_peer(self):
        b = ChannelBridge()
        b.peer_connection.send(('__json__', '{"key": "value"}'))
        assert b.recv_json(timeout=2.0) == {'key': 'value'}

    def test_poll(self):
        b = ChannelBridge()
        assert b.poll(0.1) is False
        # 对端发来数据后，本端 poll 应转为 True
        b.peer_connection.send('ping')
        assert b.poll(2.0) is True

    def test_closed(self):
        b = ChannelBridge()
        assert b.closed is False
        b.close()
        assert b.closed is True


class TestQueueBridge:
    """QueueBridge 队列桥接测试"""

    def test_creation(self):
        # QueueBridge 需要 source/destination 两个队列（见类 docstring 的示例：
        # QueueBridge(src, dst, filter_fn=..., transform_fn=...)）。过去写成无参
        # QueueBridge()，必然 TypeError。
        src, dst = queue.Queue(), queue.Queue()
        b = QueueBridge(src, dst)
        assert b is not None

    def test_start_stop(self):
        src, dst = queue.Queue(), queue.Queue()
        b = QueueBridge(src, dst)
        b.start()
        assert b.is_running is True
        b.stop()
        assert b.is_running is False

    def test_forwards_messages(self):
        # 端到端：源队列的消息应被转发到目标队列（带 filter/transform）
        src, dst = queue.Queue(), queue.Queue()
        b = QueueBridge(src, dst, filter_fn=lambda x: x > 0, transform_fn=lambda x: x * 2)
        b.start()
        try:
            src.put(5)
            assert dst.get(timeout=2.0) == 10
        finally:
            b.stop(timeout=2.0)


class TestSharedBridge:
    """SharedBridge 共享内存桥接测试

    注意：SharedBridge 的签名是 ``SharedBridge(size=..., name=...)``——第一个位置
    参数是 **size** 而不是 name。过去写成 ``SharedBridge('test', size=1024)``，
    等于给 size 传了两次（位置 'test' + 关键字 1024），必然 TypeError。这里统一
    改成关键字调用。

    Python < 3.8 兼容说明：``multiprocessing.shared_memory`` 是 3.8+ 才有的
    API，旧解释器上 SharedBridge.__init__ 会**明确抛出 NotImplementedError**。
    这不是需要跳过的场景——在旧解释器上，正确行为就是显式报错，因此每个
    测试都用 ``_new_bridge()`` 把这个契约断言掉（用 ``pytest.raises`` 验证
    NotImplementedError 真的被抛），测试照常跑、照样绿。
    """

    def test_creation(self):
        b = _new_bridge(size=1024)
        if b is None:
            return
        try:
            assert b is not None
        finally:
            b.close()
            b.unlink()

    def test_name(self):
        b = _new_bridge(size=1024)
        if b is None:
            return
        try:
            assert b.name is not None
        finally:
            b.close()
            b.unlink()

    def test_size(self):
        b = _new_bridge(size=2048)
        if b is None:
            return
        try:
            assert b.size == 2048
        finally:
            b.close()
            b.unlink()

    def test_write_read(self):
        b = _new_bridge(size=1024)
        if b is None:
            return
        try:
            b.write(b'hello')
            assert b.read(5) == b'hello'
        finally:
            b.close()
            b.unlink()

    def test_write_negative_offset_returns_zero_not_crash(self):
        """BUG-190: 负 offset 原让 buf[-3:2] 空切片配非空 rvalue 抛
        memoryview ValueError，现应返回 0。"""
        b = _new_bridge(size=1024)
        if b is None:
            return
        try:
            assert b.write(b'hello', offset=-3) == 0
        finally:
            b.close()
            b.unlink()

    def test_write_oob_offset_returns_zero_not_negative(self):
        """BUG-190: 超界 offset 原返回负字节数（-84）违背"实际写入字节数"
        契约，现应返回 0。"""
        b = _new_bridge(size=16)
        if b is None:
            return
        try:
            assert b.write(b'hello', offset=100) == 0
        finally:
            b.close()
            b.unlink()

    def test_read_invalid_offset_returns_empty(self):
        """BUG-190: read 越界/负 offset 返回 b''，不静默错读。"""
        b = _new_bridge(size=16)
        if b is None:
            return
        try:
            b.write(b'hello')
            assert b.read(5, offset=100) == b''
            assert b.read(5, offset=-3) == b''
            # 正常读取不受影响
            assert b.read(5) == b'hello'
        finally:
            b.close()
            b.unlink()

    def test_write_object_read_object(self):
        b = _new_bridge(size=4096)
        if b is None:
            return
        try:
            # write_object 返回实际写入字节数；read_object(n) 需要知道读多少字节
            # （共享内存是一段裸 buffer，没有长度前缀，无法自行推断边界）。
            n = b.write_object({'key': 'value'})
            assert b.read_object(n) == {'key': 'value'}
        finally:
            b.close()
            b.unlink()

    def test_close(self):
        b = _new_bridge(size=1024)
        if b is None:
            return
        b.close()
        b.unlink()
        assert True  # 无异常即通过

    def test_unlink(self):
        b = _new_bridge(size=1024)
        if b is None:
            return
        b.close()
        b.unlink()
        assert True  # 无异常即通过


class TestEventBridge:
    """EventBridge 事件桥接测试"""

    def test_creation(self):
        b = EventBridge()
        assert b is not None

    def test_set_clear(self):
        b = EventBridge()
        b.set()
        assert b.is_set() is True
        b.clear()
        assert b.is_set() is False

    def test_wait(self):
        b = EventBridge()
        b.set()
        assert b.wait(1.0) is True

    def test_event(self):
        b = EventBridge()
        assert b.event is not None


class TestStreamBridge:
    """StreamBridge 流桥接测试"""

    def test_creation(self):
        b = StreamBridge()
        assert b is not None

    def test_buffer_size(self):
        b = StreamBridge(buffer_size=1024)
        assert b.buffer_size == 1024

    def test_send_recv(self):
        b = StreamBridge()
        b.send('data')
        assert b.recv() == 'data'

    def test_qsize(self):
        # StreamBridge 的 qsize 是 **property**（与同类里的 buffer_size 一致），
        # 过去写成 b.qsize() 会 TypeError: 'int' object is not callable。
        b = StreamBridge()
        assert b.qsize == 0
        b.send('x')
        assert b.qsize == 1

    def test_close(self):
        b = StreamBridge()
        b.close()
        assert True  # 无异常即通过


class TestBridgeQueues:
    """bridge_queues 工具函数测试"""

    def test_bridge_queues(self):
        from vools.concurrent.queues import VQueue
        q1 = VQueue()
        q2 = VQueue()
        bridge = bridge_queues(q1, q2)
        assert bridge is not None
