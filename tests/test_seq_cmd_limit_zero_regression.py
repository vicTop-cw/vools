# -*- coding: utf-8 -*-
"""回归测试：seq_cmd from_range 的 --limit 0 不被 falsy 吞（BUG-223）。

原 `if limit:` 把显式 `--limit 0`（要 0 条）当"未指定"静默忽略，返回全量；
typer Optional 未指定是 None，须 `is not None` 判定。与 BUG-172 Seq(0)
被判空序列同族。
"""

from vools.api.seq_cmd import from_range


def _collect(**kw):
    return from_range(kw.pop("count"), filter_expr=None, map_expr=None,
                      collect=True, **kw)


class TestLimitZeroHonored:
    """BUG-223 核心：0 是合法截断值。"""

    def test_limit_zero_returns_empty(self):
        assert _collect(count=10, limit=0) == []

    def test_limit_none_full_range(self):
        assert _collect(count=10, limit=None) == list(range(10))

    def test_limit_positive_truncates(self):
        assert _collect(count=10, limit=3) == [0, 1, 2]

    def test_default_unchanged(self):
        # 不传 limit 参数：默认 None → 全量（collect=False 返回 lazy Seq
        # 或 collect=True 全量，此处按默认 collect=False 路径只验证不崩）
        r = from_range(5)
        assert list(r) == [0, 1, 2, 3, 4]