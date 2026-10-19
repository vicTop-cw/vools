# -*- coding: utf-8 -*-
"""回归测试：add_custom_sig 缓存命中必须校验 id 复用（BUG-211）。

原 `add_custom_sig` 只查 `key in _SIG_CACHE`（key=id(func)），不走
BUG-113 的 `_key_is_valid` 弱引用校验——id 被 GC 后的新对象复用时，
"死条目"命中导致新函数的注册被静默丢弃（force=False 默认路径）。
修复后读写校验对称：失效条目删除并照常写入；活条目保持原
force=False 不覆盖 / force=True 覆盖语义。
"""

import gc
from inspect import Parameter, Signature

import pytest

from vools.cache import sigcache as sc
from vools.cache.sigcache import add_custom_sig, clear_cache, get_signature


def _sig_of(name: str) -> Signature:
    return Signature([Parameter(name, Parameter.POSITIONAL_OR_KEYWORD)])


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


class TestStaleEntryNotSwallowed:
    """BUG-211 核心：id 复用（死弱引用）时注册不得被静默吞掉。"""

    def test_stale_dead_ref_registers(self):
        def f():
            pass

        # 构造与真 GC 复用等价的状态：缓存条目存在但弱引用已失效
        sc._SIG_CACHE[id(f)] = _sig_of("stale_a")
        sc._SIG_REFS[id(f)] = lambda: None

        target = _sig_of("z")
        add_custom_sig(f, target)
        assert list(get_signature(f).parameters.keys()) == ["z"]

    def test_stale_entry_evicted_from_refs(self):
        def f():
            pass

        sc._SIG_CACHE[id(f)] = _sig_of("stale")
        sc._SIG_REFS[id(f)] = lambda: None
        add_custom_sig(f, _sig_of("new"))
        # 写入后 ref 应指向活对象本身（_remember_ref 已更新）
        assert sc._SIG_REFS[id(f)]() is f


class TestLiveEntrySemanticsUnchanged:
    """活条目（同对象真缓存）保持原语义，防修复过度。"""

    def test_force_false_keeps_first(self):
        def g():
            pass

        first = _sig_of("keep")
        add_custom_sig(g, first)
        add_custom_sig(g, _sig_of("override"))
        assert get_signature(g) is first

    def test_force_true_overwrites(self):
        def g():
            pass

        add_custom_sig(g, _sig_of("first"))
        forced = _sig_of("forced")
        add_custom_sig(g, forced, force=True)
        assert get_signature(g) is forced


class TestRealGcReusePath:
    """真 GC 后 id 复用尽力触发路径：注册与读取全链自洽。"""

    def test_after_garbage_collection_redefine(self):
        def old():
            pass

        get_signature(old)          # 缓存 old 的自动签名
        old_id = id(old)
        del old
        gc.collect()

        def new():
            pass

        # 无论本轮 id 是否复用，语义都必须成立：
        # - 复用了：add_custom_sig 必须注册成功（修复前会被吞）
        # - 没复用：新对象正常注册
        target = _sig_of("z")
        add_custom_sig(new, target)
        params = list(get_signature(new).parameters.keys())
        if id(new) == old_id:
            assert params == ["z"]
        else:
            assert params == ["z"]  # 未复用也照常注册生效