# -*- coding: utf-8 -*-
"""回归测试：Nim/Python 两侧 Itor 历史策略的**功能对齐**（BUG-419）。

Python 版 ``Itor`` 的 ``set_history_max`` / ``history_strategy`` 是功能实现，
而 Nim 版 ``NimItor`` 原实现是**忽略参数的 no-op**：

    N.NimItor.set_history_max(n, 2)   # 返回 cls，什么都不做
    n.history_strategy(cb)            # 返回 self，策略从不被调用

且校验口径不一致（``True`` 是 int 的子类，Python 侧接受、Nim 侧拒绝）。

修复：
* Nim 侧实现真实历史记录（``_history`` 列表 + ``_record`` 在产出点调用策略）
  并补齐 ``set_history_max`` / ``history_strategy``；
* 两侧统一拒绝 bool，``max_len`` 校验口径一致。

已知差异（文档化，不视为缺陷）：Nim 侧 ``restart`` 由 C DLL 提供，不重放
Python 包装层维护的历史（Python 版会重放裁剪后的历史）。
"""

import importlib

import pytest

_MOD = "vools.data." + "itor"
_MOD_NIM = _MOD + "_nim"


def _load(name):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


_I = _load(_MOD)
_N = _load(_MOD_NIM)


def _nim_available():
    if _N is None:
        return False
    try:
        return bool(_N.NimItor._load_dll())
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _reset_nim():
    _I.use_nim(False)
    yield
    _I.use_nim(False)


class TestValidationParity:
    @pytest.mark.parametrize("bad, exc", [(1.5, TypeError), (-2, ValueError), (True, TypeError)])
    def test_both_backends_same_rules(self, bad, exc):
        backends = [_I.Itor]
        if _nim_available():
            backends.append(_N.NimItor)
        for cls in backends:
            obj = cls(range(3))
            with pytest.raises(exc):
                cls.set_history_max(obj, bad)


class TestNimHistoryFunctionality:
    @pytest.mark.skipif(not _nim_available(), reason="Nim 扩展不可用")
    def test_trims_to_max_len(self):
        _I.use_nim(True)
        obj = _I.get_itor(range(5))
        _N.NimItor.set_history_max(obj, 2)
        assert list(obj) == [0, 1, 2, 3, 4]
        assert obj._history == [3, 4]   # 旧实现为 []（策略被忽略）

    @pytest.mark.skipif(not _nim_available(), reason="Nim 扩展不可用")
    def test_minus_one_clears_strategy(self):
        _I.use_nim(True)
        obj = _I.get_itor(range(5))
        _N.NimItor.set_history_max(obj, -1)
        assert list(obj) == [0, 1, 2, 3, 4]
        assert obj._history == [0, 1, 2, 3, 4]

    @pytest.mark.skipif(not _nim_available(), reason="Nim 扩展不可用")
    def test_custom_strategy_called(self):
        _I.use_nim(True)
        obj = _I.get_itor(range(4))
        calls = {"n": 0}

        def cb(itor):
            calls["n"] += 1
            itor._history.clear()

        assert obj.history_strategy(cb) is obj
        assert list(obj) == [0, 1, 2, 3]
        assert calls["n"] == 4
        assert obj._history == []


class TestPythonBackendBehaviour:
    def test_trims_to_max_len(self):
        _I.use_nim(False)
        obj = _I.get_itor(range(5))
        _I.Itor.set_history_max(obj, 2)
        assert list(obj) == [0, 1, 2, 3, 4]
        assert obj._history_head is not None

    def test_restart_replays_trimmed_history(self):
        _I.use_nim(False)
        obj = _I.get_itor(range(5))
        _I.Itor.set_history_max(obj, 2)
        assert list(obj) == [0, 1, 2, 3, 4]
        obj.restart()
        assert list(obj) == [3, 4]

    def test_custom_strategy_called(self):
        _I.use_nim(False)
        obj = _I.get_itor(range(3))
        calls = {"n": 0}

        def cb(itor):
            calls["n"] += 1

        assert obj.history_strategy(cb) is obj
        assert list(obj) == [0, 1, 2]
        assert calls["n"] == 3


class TestNimRestartLimitationDocumented:
    @pytest.mark.skipif(not _nim_available(), reason="Nim 扩展不可用")
    def test_restart_is_dll_driven(self):
        """Nim 侧 restart 由 C DLL 提供：不重放 Python 包装层的历史（已知差异）。"""
        _I.use_nim(True)
        obj = _I.get_itor(range(3))
        _N.NimItor.set_history_max(obj, 2)
        assert list(obj) == [0, 1, 2]
        assert obj._history == [1, 2]
        obj.restart()
        # 源迭代器被 DLL 重启（而非重放历史），随后历史继续按策略裁剪
        assert list(obj) == [0, 1, 2]
        assert obj._history == [1, 2]
