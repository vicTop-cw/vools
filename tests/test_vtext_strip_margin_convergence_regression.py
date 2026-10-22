# -*- coding: utf-8 -*-
"""回归测试：strip_margin 的 $| 格式化循环引用不再挂死（BUG-301）。

`VText.strip_margin` 对 `$|` / `$\d+|` 行反复 `formatEx` 直到文本稳定，原实现
是 `while True` **无迭代上限**：变量互相引用时（a="{b}"、b="{a}"）每轮在两种
文本间振荡、永不相等 → **进程永久挂死**（5 秒子进程超时实测无返回），且无任何
错误提示。

修复：迭代上限 100 轮，超限抛 ValueError（提示变量循环引用）。
"""

import pytest

from vools.data.vtext import VText


class TestOscillatingContextRaises:
    def test_mutual_reference_raises(self):
        # 修复前：死循环挂死（本测试会卡住）
        with pytest.raises(ValueError, match='未收敛'):
            VText('$|{a}').strip_margin(a='{b}', b='{a}')

    def test_indent_rule_also_raises(self):
        with pytest.raises(ValueError, match='循环引用'):
            VText('$2|{a}').strip_margin(a='{b}', b='{a}')

    def test_message_mentions_kwargs(self):
        with pytest.raises(ValueError) as ei:
            VText('$|{a}').strip_margin(a='{b}', b='{a}')
        assert 'kwargs' in str(ei.value)


class TestNormalConvergenceStillWorks:
    def test_single_round(self):
        assert str(VText('$|v={x}').strip_margin(x=42)) == 'v=42'

    def test_multi_round(self):
        # {a} -> {b} -> 'done'：两轮收敛
        assert str(VText('$|{a}').strip_margin(a='{b}', b='done')) == 'done'

    def test_indent(self):
        assert str(VText('$2|v={x}').strip_margin(x=7)) == '  v=7'

    def test_self_reference_is_stable(self):
        # a="{a}" 首轮不变化即视为稳定（不误报循环引用）
        assert str(VText('$|{a}').strip_margin(a='{a}')) == '{a}'

    def test_hash_pipe_dropped(self):
        assert str(VText('|keep\n#|drop\n|keep2').strip_margin()) == 'keep\nkeep2'

    def test_plain_pipe(self):
        assert str(VText('|  abc').strip_margin()) == '  abc'

    def test_no_marker_kept(self):
        assert str(VText('plain').strip_margin()) == 'plain'