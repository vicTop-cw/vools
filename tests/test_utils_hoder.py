# -*- coding: utf-8 -*-
"""测试 vools.utils.hoder.Hoder。"""

__all__ = ["TestHoder"]


class Dummy:
    """测试用对象。"""

    value = 42


class TestHoder:
    """Hoder 核心行为测试。"""

    def test_initial_obj(self):
        from vools.utils.hoder import Hoder
        h = Hoder(Dummy())
        assert h.get().value == 42
        assert h.is_created() is True
        assert h() is not None

    def test_lazy_creator_called_once(self):
        from vools.utils.hoder import Hoder
        calls = []
        h = Hoder(lazy=True, creator=lambda: calls.append(1) or Dummy())
        assert calls == []
        assert h.is_created() is False
        h.get()
        assert calls == [1]
        assert h.is_created() is True
        # Second call should not re-invoke creator
        h.get()
        assert calls == [1]

    def test_lazy_without_creator(self):
        from vools.utils.hoder import Hoder
        h = Hoder(lazy=True)
        assert h.is_created() is False
        assert h.get() is None

    def test_set_reset(self):
        from vools.utils.hoder import Hoder
        h = Hoder(lazy=True, creator=lambda: Dummy())
        h.set(1)
        assert h.get() == 1
        h.reset()
        assert h.is_created() is False
        assert h.get().value == 42

    def test_call_proxy(self):
        from vools.utils.hoder import Hoder
        h = Hoder(Dummy())
        assert h.value == 42
        h.value = 99
        assert h.get().value == 99

    def test_do_chain(self):
        from vools.utils.hoder import Hoder
        h = Hoder(1)
        r = h.do()
        assert r is h

    def test_do_with_pre_sub(self):
        from vools.utils.hoder import Hoder
        seen = []
        h = Hoder(5)
        h.do(
            pre_f=lambda x: (seen.append(("pre", x)), x)[1],
            f=lambda x: (seen.append(("f", x)), x)[1],
            sub_f=lambda x: seen.append(("sub", x)),
        )
        assert seen == [("pre", h), ("f", h), ("sub", h)]

    def test_private_attr_setattr(self):
        from vools.utils.hoder import Hoder
        h = Hoder(Dummy())
        h._private = "secret"
        assert h._private == "secret"
        assert h.get().value == 42  # unaffected

    def test_is_created_init_non_lazy(self):
        from vools.utils.hoder import Hoder
        h = Hoder(1, lazy=False)
        assert h.is_created() is True

    def test_import_all(self):
        from vools.utils.hoder import __all__
        assert "Hoder" in __all__
