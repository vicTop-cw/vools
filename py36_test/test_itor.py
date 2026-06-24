import threading
import time
import pytest
from vools.data.itor import Itor, Node, ItorState


class TestNode:
    """Node 节点功能测试"""

    def test_node_val_and_next(self):
        node = Node(42)
        assert node.val == 42
        assert node.next is None
        node.next = Node(99)
        assert node.next.val == 99

    def test_next_property_setter(self):
        a = Node(1)
        b = Node(2)
        a.next = b
        assert a.next is b
        a.next = None
        assert a.next is None

    def test_node_iteration(self):
        head = Node.from_iter([1, 2, 3])
        assert [n.val for n in head] == [1, 2, 3]

    def test_from_iter_basic(self):
        head = Node.from_iter([10, 20, 30])
        assert head.val == 10
        assert head.next.val == 20
        assert head.next.next.val == 30
        assert head.next.next.next is None

    def test_from_iter_empty(self):
        assert Node.from_iter([]) is None

    def test_from_iter_generator(self):
        def gen():
            yield 'a'
            yield 'b'

        head = Node.from_iter(gen())
        assert [n.val for n in head] == ['a', 'b']

    def test_from_iter_infinite(self):
        def infinite():
            i = 0
            while True:
                yield i
                i += 1

        head = Node.from_iter(infinite())
        assert head.val == 0
        assert head.next.val == 1
        assert head.next.next.val == 2
        assert head.next.next.next.val == 3

    def test_to_iter_infinite_with_limit(self):
        def infinite():
            i = 0
            while True:
                yield i
                i += 1

        head = Node.from_iter(infinite())
        vals = []
        for v in head.to_iter():
            vals.append(v)
            if len(vals) == 5:
                break
        assert vals == [0, 1, 2, 3, 4]

    def test_to_itor_infinite(self):
        def infinite():
            i = 0
            while True:
                yield i
                i += 1

        head = Node.from_iter(infinite())
        itor = head.to_itor()
        gen = itor()
        assert next(gen) == 0
        assert next(gen) == 1
        assert next(gen) == 2
        gen.stop()
        with pytest.raises(StopIteration):
            next(gen)

    def test_to_iter(self):
        head = Node.from_iter([1, 2, 3])
        assert list(head.to_iter()) == [1, 2, 3]

    def test_to_iter_single_node(self):
        node = Node(42)
        assert list(node.to_iter()) == [42]

    def test_to_itor(self):
        head = Node.from_iter([1, 2, 3])
        itor = head.to_itor()
        gen = itor()
        assert list(gen) == [1, 2, 3]
        assert gen.state is ItorState.STOPPED

    def test_to_itor_history_and_restart(self):
        head = Node.from_iter([1, 2, 3])
        itor = head.to_itor()
        gen = itor()
        assert next(gen) == 1
        assert next(gen) == 2
        gen.restart()
        assert list(gen) == [1, 2, 3]


class TestItorBasic:
    """基础迭代功能测试"""

    def test_iterates_all_values(self):
        itor = Itor([1, 2, 3])
        assert list(itor()) == [1, 2, 3]

    def test_state_after_exhaustion(self):
        itor = Itor([1])
        gen = itor()
        assert next(gen) == 1
        with pytest.raises(StopIteration):
            next(gen)
        assert gen.state is ItorState.STOPPED

    def test_generator_finishes_cleanly(self):
        itor = Itor(range(5))
        gen = itor()
        vals = list(gen)
        assert vals == list(range(5))
        assert gen.state is ItorState.STOPPED

    def test_iter_directly(self):
        itor = Itor([1, 2, 3])
        assert list(itor) == [1, 2, 3]
        assert itor.state is ItorState.STOPPED

    def test_next_directly(self):
        itor = Itor([1, 2, 3])
        assert next(itor) == 1
        assert next(itor) == 2
        assert next(itor) == 3
        with pytest.raises(StopIteration):
            next(itor)
        assert itor.state is ItorState.STOPPED

    def test_call_returns_fresh_copy(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert gen is not itor
        assert gen.state is ItorState.PENDING
        assert itor.state is ItorState.PENDING
        assert list(gen) == [1, 2, 3]
        assert gen.state is ItorState.STOPPED
        assert itor.state is ItorState.PENDING

    def test_call_does_not_share_state(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert list(gen) == [1, 2, 3]
        assert gen.state is ItorState.STOPPED
        assert itor.state is ItorState.PENDING
        # 原实例仍可继续独立迭代
        assert list(itor) == [1, 2, 3]
        assert itor.state is ItorState.STOPPED


class TestItorPauseResume:
    """断点暂停/恢复测试"""

    def test_pause_resume(self):
        itor = Itor([1, 2, 3, 4, 5])
        results = []

        def consumer():
            for v in itor:          # 直接迭代原实例，控制线程才能影响它
                results.append(v)

        t = threading.Thread(target=consumer)
        t.start()
        while len(results) < 2:
            time.sleep(0.005)

        itor.set_pause()
        time.sleep(0.05)
        count = len(results)
        time.sleep(0.05)
        assert len(results) == count, "暂停期间不应继续产出"

        itor.resume()
        t.join(timeout=1)
        assert not t.is_alive()
        assert results == [1, 2, 3, 4, 5]

    def test_pause_from_other_thread(self):
        itor = Itor(range(10))
        results = []

        def consumer():
            for v in itor:          # 直接迭代原实例，控制线程才能影响它
                results.append(v)

        def controller():
            time.sleep(0.05)
            itor.set_pause()
            time.sleep(0.05)
            itor.resume()

        t = threading.Thread(target=consumer)
        t.start()
        threading.Thread(target=controller).start()
        t.join(timeout=1)
        assert not t.is_alive()
        assert results == list(range(10))


class TestItorJump:
    """插队（send）测试"""

    def test_immediate_jump(self):
        itor = Itor([1, 2, 3, 4, 5])
        gen = itor()
        assert next(gen) == 1
        gen.send(Node(99))
        assert next(gen) == 99
        assert next(gen) == 2
        assert list(gen) == [3, 4, 5]

    def test_immediate_jump_chain(self):
        itor = Itor([1, 2, 3, 4, 5])
        gen = itor()
        assert next(gen) == 1
        gen.send(Node.from_iter([98, 99]))
        assert next(gen) == 98
        assert next(gen) == 99
        assert next(gen) == 2
        assert list(gen) == [3, 4, 5]

    def test_send_lazy_chain(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert next(gen) == 1
        gen.send(Node.from_iter([88, 89]))  # 懒加载链表
        assert next(gen) == 88
        assert next(gen) == 89
        assert next(gen) == 2
        assert list(gen) == [3]

    def test_conditional_jump_chain(self):
        itor = Itor([1, 2, 3, 4, 5])
        gen = itor()
        # 当历史记录中已有 3 条时插入整条链表 [88, 89]
        gen.send(Node.from_iter([88, 89]), jump_when=lambda it: _history_len(it) == 3)
        vals = list(gen)
        assert vals == [1, 2, 3, 88, 89, 4, 5]

    def test_immediate_jump_in_thread(self):
        itor = Itor(range(100))
        results = []

        def consumer():
            for v in itor:          # 直接迭代原实例，控制线程才能影响它
                results.append(v)
                time.sleep(0.02)  # 让生成器停在 yield 点，方便控制线程插队

        def controller():
            while len(results) < 2:
                time.sleep(0.005)
            itor.set_pause()
            time.sleep(0.02)
            itor.send(Node(99))
            itor.resume()
            time.sleep(0.05)
            itor.stop()

        t = threading.Thread(target=consumer)
        t.start()
        threading.Thread(target=controller).start()
        t.join(timeout=2)
        assert not t.is_alive()
        assert 99 in results
        assert results.index(99) == 2

    def test_conditional_jump(self):
        itor = Itor([1, 2, 3, 4, 5])
        gen = itor()
        # 当历史记录中已有 3 条时插入
        gen.send(Node(88), jump_when=lambda it: _history_len(it) == 3)
        vals = list(gen)
        assert vals == [1, 2, 3, 88, 4, 5]

    def test_conditional_jump_in_thread(self):
        itor = Itor([1, 2, 3, 4, 5])
        results = []
        itor.send(Node(88), jump_when=lambda it: _history_len(it) == 3)

        def consumer():
            for v in itor:          # 直接迭代原实例，控制线程才能影响它
                results.append(v)

        t = threading.Thread(target=consumer)
        t.start()
        t.join(timeout=1)
        assert not t.is_alive()
        assert results == [1, 2, 3, 88, 4, 5]

    def test_send_after_stop_raises(self):
        itor = Itor([1])
        gen = itor()
        next(gen)
        with pytest.raises(StopIteration):
            next(gen)
        with pytest.raises(RuntimeError, match="迭代器已终止"):
            gen.send(Node(99))

    def test_send_returns_self(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert gen.send(Node(99)) is gen

    def test_send_accepts_non_node_single_value(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert next(gen) == 1
        gen.send(99)
        assert next(gen) == 99
        assert next(gen) == 2

    def test_send_accepts_list(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert next(gen) == 1
        gen.send([88, 89])
        assert next(gen) == 88
        assert next(gen) == 89
        assert next(gen) == 2

    def test_send_accepts_string_as_single_value(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert next(gen) == 1
        gen.send("hello")
        assert next(gen) == "hello"
        assert next(gen) == 2

    def test_send_accepts_empty_list(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert next(gen) == 1
        gen.send([])
        assert next(gen) == 2

    def test_send_accepts_generator(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert next(gen) == 1
        gen.send((x for x in [88, 89]))
        assert next(gen) == 88
        assert next(gen) == 89
        assert next(gen) == 2


class TestItorChaining:
    """链式调用（公开方法返回 self）测试"""

    def test_set_pause_returns_self(self):
        itor = Itor([1, 2, 3])
        assert itor.set_pause() is itor

    def test_resume_returns_self(self):
        itor = Itor([1, 2, 3])
        itor.set_pause()
        assert itor.resume() is itor

    def test_restart_returns_self(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        next(gen)
        assert gen.restart() is gen

    def test_history_strategy_returns_self(self):
        itor = Itor([1, 2, 3])
        assert itor.history_strategy(None) is itor

    def test_stop_returns_self(self):
        itor = Itor([1, 2, 3])
        assert itor.stop() is itor

    def test_set_history_max_returns_cls(self):
        itor = Itor([1, 2, 3])
        assert Itor.set_history_max(itor, 3) is Itor

    def test_chain_send_pause_resume(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert next(gen) == 1
        assert gen.send(99).set_pause().resume() is gen
        assert next(gen) == 99
        assert next(gen) == 2


class TestItorRestart:
    """重启 / 重放测试"""

    def test_restart_replays_history(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert next(gen) == 1
        assert next(gen) == 2
        gen.restart()
        assert list(gen) == [1, 2, 3]

    def test_restart_after_exhaustion(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        vals = list(gen)
        assert vals == [1, 2, 3]
        gen.restart()
        gen2 = gen()
        assert list(gen2) == [1, 2, 3]

    def test_restart_from_other_thread(self):
        itor = Itor([1, 2, 3])
        results = []

        def consumer():
            for v in itor:          # 直接迭代原实例，控制线程才能影响它
                results.append(v)
                time.sleep(0.02)  # 让生成器停在 yield 点，便于外部重启

        def controller():
            while len(results) < 2:
                time.sleep(0.005)
            itor.restart()
            while len(results) < 5:
                time.sleep(0.005)
            itor.stop()

        t = threading.Thread(target=consumer)
        t.start()
        threading.Thread(target=controller).start()
        t.join(timeout=2)
        assert not t.is_alive()
        # 先拿到 1,2，然后重放 1,2,3
        assert results[:5] == [1, 2, 1, 2, 3]


class TestItorHistoryStrategy:
    """历史保留策略 / 可定制性测试"""

    def test_custom_history_strategy(self):
        itor = Itor([1, 2, 3, 4, 5])

        def keep_last_3(it):
            while True:
                count = 0
                cur = it._history_head
                while cur:
                    count += 1
                    cur = cur.next
                if count > 3:
                    it._history_head = it._history_head.next
                else:
                    break
            if it._history_head is None:
                it._history_tail = None

        itor.history_strategy(keep_last_3)
        gen = itor()
        vals = list(gen)
        assert vals == [1, 2, 3, 4, 5]
        # 重启后只保留最近 3 条
        gen.restart()
        assert list(gen) == [3, 4, 5]

    def test_restart_preserves_history_by_default(self):
        itor = Itor([1, 2, 3])
        gen = itor()
        assert list(gen) == [1, 2, 3]
        gen.restart()
        assert list(gen) == [1, 2, 3]


class TestItorStop:
    """终止控制测试"""

    def test_stop_while_running(self):
        itor = Itor(range(100))
        results = []

        def consumer():
            for v in itor:          # 直接迭代原实例，控制线程才能影响它
                results.append(v)
                time.sleep(0.001)

        t = threading.Thread(target=consumer)
        t.start()
        while len(results) < 5:
            time.sleep(0.005)
        itor.stop()
        t.join(timeout=2)
        assert not t.is_alive()
        assert len(results) >= 5
        assert len(results) < 100


class TestItorAsyncThread:
    """异步线程综合控制测试"""

    def test_async_thread_control(self):
        itor = Itor(range(100))
        results = []
        control_log = []

        def consumer():
            for v in itor:          # 直接迭代原实例，控制线程才能影响它
                results.append(v)
                time.sleep(0.02)  # 让生成器停在 yield 点，便于外部综合控制

        def controller():
            time.sleep(0.05)
            itor.set_pause()
            control_log.append("pause")
            time.sleep(0.02)
            itor.send(Node(77))
            control_log.append("jump")
            itor.resume()
            control_log.append("resume")
            while 77 not in results:
                time.sleep(0.005)
            itor.restart()
            control_log.append("restart")
            time.sleep(0.1)
            itor.stop()

        t = threading.Thread(target=consumer)
        t.start()
        threading.Thread(target=controller).start()
        t.join(timeout=3)
        assert not t.is_alive()
        assert 77 in results
        assert control_log == ["pause", "jump", "resume", "restart"]


class TestItorNoDeadlock:
    """死锁修复验证"""

    def test_stop_with_blocking_source(self):
        source = _BlockingSource(10)
        itor = Itor(source)
        results = []

        def consumer():
            for v in itor:          # 直接迭代原实例，控制线程才能影响它
                results.append(v)

        t = threading.Thread(target=consumer)
        t.start()
        time.sleep(0.05)
        # 源迭代器阻塞在 next() 时，stop 不应死锁
        itor.stop()
        source.release()
        t.join(timeout=1)
        assert not t.is_alive()
        assert len(results) <= 1

    def test_send_with_blocking_source(self):
        source = _BlockingSource(10)
        itor = Itor(source)
        results = []

        def consumer():
            for v in itor:          # 直接迭代原实例，控制线程才能影响它
                results.append(v)

        def controller():
            time.sleep(0.05)
            itor.send(Node(99))
            source.release()

        t = threading.Thread(target=consumer)
        t.start()
        threading.Thread(target=controller).start()
        t.join(timeout=1)
        assert not t.is_alive()
        assert 99 in results


class TestItorSetHistoryMax:
    """类方法 set_history_max 验证"""

    def test_keep_last(self):
        itor = Itor([1, 2, 3, 4, 5])
        Itor.set_history_max(itor, 3)
        gen = itor()
        assert list(gen) == [1, 2, 3, 4, 5]
        gen.restart()
        assert list(gen) == [3, 4, 5]

    def test_minus_one_keep_all(self):
        itor = Itor([1, 2, 3, 4, 5])
        Itor.set_history_max(itor, 3)
        Itor.set_history_max(itor, -1)
        gen = itor()
        assert list(gen) == [1, 2, 3, 4, 5]
        gen.restart()
        assert list(gen) == [1, 2, 3, 4, 5]

    def test_zero(self):
        itor = Itor([1, 2, 3])
        Itor.set_history_max(itor, 0)
        gen = itor()
        assert list(gen) == [1, 2, 3]
        gen.restart()
        assert list(gen) == []

    def test_invalid(self):
        itor = Itor([1])
        with pytest.raises(ValueError):
            Itor.set_history_max(itor, -2)
        with pytest.raises(TypeError):
            Itor.set_history_max(itor, "3")


# ---------- helpers ----------

def _history_len(itor: Itor) -> int:
    """不持锁地数历史长度；供条件插队函数使用（调用方已持有锁）。"""
    count = 0
    cur = itor._history_head
    while cur:
        count += 1
        cur = cur.next
    return count


class _BlockingSource:
    """用于模拟阻塞型源迭代器的辅助类"""
    def __init__(self, n: int) -> None:
        self.n = n
        self.i = 0
        self._event = threading.Event()

    def __iter__(self):
        return self

    def __next__(self):
        if self.i >= self.n:
            raise StopIteration
        self._event.wait()
        v = self.i
        self.i += 1
        return v

    def release(self):
        self._event.set()
