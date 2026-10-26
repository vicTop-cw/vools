# -*- coding: utf-8 -*-
"""回归测试：Itor/get_itor 构造期不校验 iterable（BUG-507）。

修复前：

    it = get_itor(123)      # 构造**成功**，state 还是 PENDING
    list(it)                # 直到真正迭代才抛裸
                            # "TypeError: 'int' object is not iterable"

修复后在**统一入口** ``get_itor`` 用 ``iter()`` 做准入探测（不消费元素），
同时 ``Itor.__init__`` 也校验——**关键**：``use_nim(True)`` 是全局开关，
原实现只校验 Python 版，启用 Nim 版后同一函数行为会漂移。

测试卫生：本文件用 autouse fixture 固定 Python 实现并在结束时恢复，
避免被其他测试模块遗留的 ``use_nim(True)`` 全局状态污染（实测会发生）。
"""

import pytest

from vools.data.itor import Itor, get_itor, use_nim


@pytest.fixture(autouse=True)
def _pin_python_impl():
    use_nim(False)
    yield
    use_nim(False)


class TestIterableValidation:
    @pytest.mark.parametrize("bad", [123, None, 1.5, object()])
    def test_non_iterable_rejected_at_construction(self, bad):
        with pytest.raises(TypeError) as ei:
            get_itor(bad)
        assert "iterable" in str(ei.value)

    def test_direct_Itor_construction_also_validates(self):
        with pytest.raises(TypeError):
            Itor(42)

    def test_validation_holds_in_nim_mode_too(self):
        """全局开关切换实现时，准入校验不能消失（BUG-507 的核心）。"""
        if not use_nim(True):
            pytest.skip("Nim 扩展不可用")
        try:
            with pytest.raises(TypeError):
                get_itor(123)
        finally:
            use_nim(False)


class TestValidIterablesAccepted:
    def test_list(self):
        assert list(get_itor([1, 2, 3])) == [1, 2, 3]

    def test_str(self):
        assert list(get_itor("ab")) == ["a", "b"]

    def test_generator(self):
        assert list(get_itor(x for x in range(3))) == [0, 1, 2]

    def test_dict(self):
        assert list(get_itor({"a": 1})) == ["a"]

    def test_range(self):
        assert list(get_itor(range(3))) == [0, 1, 2]

    def test_old_style_getitem_only(self):
        class OldStyle:
            def __getitem__(self, i):
                if i >= 2:
                    raise IndexError
                return i * 10

        assert list(get_itor(OldStyle())) == [0, 10]


class TestItorSemanticsUnchanged:
    def test_state_is_property(self):
        it = Itor([1])
        assert not callable(it.state)
        list(it)
        assert it.state.name == "STOPPED"

    def test_restart_replays(self):
        it = Itor([1, 2])
        assert list(it) == [1, 2]
        it.restart()
        assert list(it) == [1, 2]

    def test_resume_returns_self(self):
        it = Itor([1, 2])
        assert it.resume() is it

    def test_send_without_args_is_documented_error(self):
        """send(jump, jump_when) 是**插队** API；两者都不给是文档化的 ValueError。"""
        it = Itor([1, 2])
        with pytest.raises(ValueError) as ei:
            it.send()
        assert "jump" in str(ei.value)

    def test_set_history_max_is_classmethod_with_explicit_itor(self):
        it = Itor([1, 2])
        assert Itor.set_history_max(it, 2) is not None
