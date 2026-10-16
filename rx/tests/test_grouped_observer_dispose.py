# -*- coding: utf-8 -*-
"""rx/tests/test_grouped_observer_dispose.py — _GroupedObserver 分发遍历不得被回调内退订改坏

同族先例：f25e417 修 actus eventbus「在锁外直接遍历共享列表，另一线程 unsubscribe
改同一列表 → RuntimeError: list changed size during iteration」。本仓 rx 的 Subject
早已按正确姿势写（subject.py:79/88/303/305 一律 `for observer in list(self._observers)`），
唯独 operators.py 的 _GroupedObserver 三个分发方法（on_next/on_error/on_completed）
直接遍历【活列表】self._observers —— 而它自己的 subscribe() 返回的 unsubscribe 闭包
会执行 `self._observers.remove(observer)`（operators.py:997-999）。

「观察者在自己的 on_next 里退订」是该类 API 自己承诺支持的用法（take(n) 收到第 n 个
就 unsubscribe 是最常见写法），所以这不是理论边角：回调内 unsubscribe → 活列表边遍历
边缩 → RuntimeError。本测试按类契约直接钉这一格（不依赖 group_by 的装配路径）。

修法与 Subject 同口径：分发处取快照 list(self._observers)。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.reactive.core.observable import Observer       # noqa: E402
from vools.reactive.operators.operators import _GroupedObserver  # noqa: E402


def _mk_observer(sink, label, on_next_extra=None):
    class _O(Observer):
        def on_next(self, value):
            sink.append((label, value))
            if on_next_extra:
                on_next_extra()

        def on_error(self, error):
            sink.append((label, 'err'))

        def on_completed(self):
            sink.append((label, 'done'))

    return _O()


def test_observer_disposed_in_earlier_callback_still_gets_current_value():
    """A 在 on_next 里退订自己时，排在其后的 B 不得被静默跳过。

    活列表遍历的真实症状不是抛异常（list 边遍历边删不报错），而是【漏通知】：
    observers=[A,B,C]，迭代到 0=A，A 的回调把 A 删掉 → 列表变 [B,C]，迭代器
    下一步取 index=1 —— 拿到的却是 C，B 被整个跳过。这是分发正确性 bug，
    与 f25e417 同族（回调内退订改活列表），只是形状从"改字典炸"变成"改列表漏"。
    """
    go = _GroupedObserver()
    sink = []
    holder = {}

    def a_unsub():
        holder['a'].unsubscribe()

    holder['a'] = go.subscribe(_mk_observer(sink, 'A', on_next_extra=a_unsub))
    go.subscribe(_mk_observer(sink, 'B'))
    go.subscribe(_mk_observer(sink, 'C'))

    go.on_next(1)
    got = [l for l, v in sink if v == 1]
    assert got == ['A', 'B', 'C'], '退订发生在 A，B 被静默跳过（活列表 index 位移）: %s' % got


def test_all_remaining_observers_completed_after_dispose():
    """on_completed 同理：先订阅者退订不得让后继漏掉完成通知。"""
    go = _GroupedObserver()
    sink = []
    holder = {}

    def a_done():
        holder['a'].unsubscribe()

    class _DoneA(Observer):
        def on_next(self, value):
            pass

        def on_error(self, error):
            pass

        def on_completed(self):
            sink.append(('A', 'done'))
            a_done()

    holder['a'] = go.subscribe(_DoneA())
    go.subscribe(_mk_observer(sink, 'B'))
    go.subscribe(_mk_observer(sink, 'C'))
    go.on_completed()
    done = [l for l, v in sink if v == 'done']
    assert done == ['A', 'B', 'C'], '完成通知漏给: %s' % [x for x in ('A', 'B', 'C') if x not in done]


def test_error_dispatch_not_broken_by_dispose():
    go = _GroupedObserver()
    sink = []
    holder = {}

    class _ErrA(Observer):
        def on_next(self, value):
            pass

        def on_error(self, error):
            sink.append(('A', 'err'))
            holder['a'].unsubscribe()

        def on_completed(self):
            pass

    holder['a'] = go.subscribe(_ErrA())
    go.subscribe(_mk_observer(sink, 'B'))
    go.on_error(RuntimeError('x'))
    got = [l for l, v in sink if v == 'err']
    assert got == ['A', 'B'], 'on_error 分发同样漏给 B: %s' % got


def test_normal_dispatch_still_works_after_fix():
    """正向保底：不退订时，两个观察者都该收到，且后订阅者拿到历史回放。"""
    go = _GroupedObserver()
    sink = []
    go.on_next('x')                          # 先有一条历史
    go.subscribe(_mk_observer(sink, 'A'))    # 订阅时回放历史
    go.on_next('y')
    got = [v for _l, v in sink if v in ('x', 'y')]
    assert 'x' in got and 'y' in got
