# -*- coding: utf-8 -*-
"""回归测试：Nim 版 Itor（NimItor）补齐 VoolsBase 统一 API（BUG-418）。

``get_itor(iterable)`` 在 Nim 扩展可用时返回 ``NimItor``，而 NimItor 原本
**没有继承 VoolsBase**，于是与 Python 版 ``Itor`` 的统一 API 不一致：

    n.do(...)     # NimItor -> AttributeError（Itor 可用）
    n.copy()      # 同上
    n.to_dict()   # 同上
    n.from_dict() # 同上
    n.update(...) # 同上

a676de6（do 方法统一到 VoolsBase）只覆盖了 Python 侧，Nim 侧漏了。
修复：``class NimItor(VoolsBase)``。

本测试在 Nim 扩展不可用的环境会**跳过** Nim 专属断言（``use_nim(True)`` 会
回退），Python 侧契约始终校验。
"""

import importlib

import pytest

_MOD = "vools.data." + "itor"
_MOD_NIM = _MOD + "_nim"


def _nim_module():
    try:
        return importlib.import_module(_MOD_NIM)
    except Exception:
        return None


def _use_nim_fn():
    m = importlib.import_module(_MOD)
    return m.use_nim, m.get_itor


@pytest.fixture()
def nim_state():
    use_nim, _ = _use_nim_fn()
    try:
        yield use_nim
    finally:
        use_nim(False)


def _nim_available():
    mod = _nim_module()
    if mod is None:
        return False
    try:
        return bool(mod.NimItor._load_dll())
    except Exception:
        return False


REQUIRED_ATTRS = ("do", "copy", "to_dict", "from_dict", "update")


@pytest.mark.skipif(not _nim_available(), reason="Nim 扩展不可用")
def test_nim_itor_has_unified_api(nim_state):
    use_nim, get_itor = _use_nim_fn()
    nim_mod = _nim_module()
    use_nim(True)
    obj = get_itor([1, 2, 3])
    assert isinstance(obj, nim_mod.NimItor)
    for attr in REQUIRED_ATTRS:
        assert hasattr(obj, attr), f"NimItor 缺少 {attr}"

    # 行为与 Python 版一致
    assert obj.do(lambda x: None) is obj
    assert isinstance(obj.copy(), nim_mod.NimItor)
    assert isinstance(obj.to_dict(), dict)
    assert (obj == obj) is True


@pytest.mark.skipif(not _nim_available(), reason="Nim 扩展不可用")
def test_nim_itor_hash_rejected_clearly(nim_state):
    use_nim, get_itor = _use_nim_fn()
    use_nim(True)
    obj = get_itor([1, 2, 3])
    with pytest.raises(TypeError) as ei:
        hash(obj)
    assert "NimItor" in str(ei.value)


def test_python_itor_contract(nim_state):
    use_nim, get_itor = _use_nim_fn()
    use_nim(False)
    obj = get_itor([1, 2, 3])
    assert type(obj).__name__ == "Itor"
    for attr in REQUIRED_ATTRS:
        assert hasattr(obj, attr)
    assert (obj == obj) is True
    assert isinstance(obj.copy(), type(obj))


def test_get_itor_returns_itor_when_nim_off():
    use_nim, get_itor = _use_nim_fn()
    use_nim(False)
    assert type(get_itor([1, 2, 3])).__name__ == "Itor"
