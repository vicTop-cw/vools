# -*- coding: utf-8 -*-
"""回归测试：task 模块不得 pickle 反序列化不可信数据（BUG-207）。

原 `TaskQueue._deserialize_func`（queue.py L201）与 `Task._restore_pickle`
（models.py L49）均 `pickle.loads` 未验证来源的持久化数据，`__reduce__`
gadget 可任意代码执行。修复：
- queue.py：函数序列化不再走 pickle，`__main__`/lambda 统一走 `__registry__:<id>`
  （同进程），`_deserialize_func` 对非 `__registry__`/`<module>:<func>` 格式抛
  ValueError（不执行任何 pickle）；
- models.py：`_restore_pickle` 改用 `_SafeUnpickler`（find_class 白名单：
  builtins 函数/异常 + datetime/decimal/uuid/collections），非白名单全局抛
  UnpicklingError，捕获后按纯字符串回退，不执行 payload。
"""

import pickle
import base64
import json

import pytest

from vools.task.core.queue import TaskQueue
from vools.task.core.models import (
    _restore_pickle,
    _load_json,
    _PICKLE_MARKER,
)


def _pwned():
    """模块顶层 gadget：pickle 序列化需引用模块级全局。"""
    return "PWNED"


class Evil:
    """恶意 __reduce__：返回 (模块顶层函数, 参数)，反序列化时会被调用。"""

    def __reduce__(self):
        return (_pwned, ())


def top_func():
    """模块顶层函数，用于 __main__ 场景的 registry 序列化测试。"""
    return 42


def _make_evil_payload() -> bytes:
    """构造带 __reduce__ gadget 的恶意 pickle payload。"""
    return pickle.dumps(Evil())


class TestQueueNoPickleRce:
    """TaskQueue._deserialize_func 不得执行恶意 pickle（BUG-207）。"""

    def test_deserialize_func_blocks_evil_payload(self):
        q = TaskQueue()
        payload = base64.b64encode(_make_evil_payload()).decode("utf-8")
        with pytest.raises(ValueError):
            q._deserialize_func(payload)

    def test_deserialize_func_blocks_base64_without_colon(self):
        # 不含 ':' 且非 registry/路径格式 → 直接拒绝
        q = TaskQueue()
        payload = base64.b64encode(b"hello").decode("utf-8")
        with pytest.raises(ValueError):
            q._deserialize_func(payload)

    def test_deserialize_func_registry_main_function(self, monkeypatch):
        q = TaskQueue()
        # BUG-207: __main__ 函数走 __registry__:<id>，不走 pickle
        monkeypatch.setattr(top_func, "__module__", "__main__")
        fd = q._serialize_func(top_func)
        assert fd.startswith("__registry__:")
        assert q._deserialize_func(fd)() == 42

    def test_deserialize_func_module_path(self):
        q = TaskQueue()
        fd = q._serialize_func(TaskQueue)
        assert fd == "vools.task.core.queue:TaskQueue"
        assert q._deserialize_func(fd) is TaskQueue


class TestModelsNoPickleRce:
    """Task._restore_pickle 不得执行恶意 pickle（BUG-207）。"""

    def test_restore_pickle_blocks_evil(self):
        marker = _PICKLE_MARKER + base64.b64encode(
            _make_evil_payload()
        ).decode("ascii")
        # 应回退为原字符串，不执行 gadget
        assert _restore_pickle(marker) == marker

    def test_load_json_blocks_evil(self):
        marker = _PICKLE_MARKER + base64.b64encode(
            _make_evil_payload()
        ).decode("ascii")
        obj = _load_json(json.dumps({"__x": marker}))
        assert obj["__x"] == marker

    def test_restore_pickle_allows_std_lib_types(self):
        from datetime import datetime, timedelta
        from decimal import Decimal
        from uuid import UUID

        marker = _PICKLE_MARKER + base64.b64encode(
            pickle.dumps(
                {
                    "dt": datetime(2020, 1, 1),
                    "td": timedelta(days=1),
                    "dec": Decimal("3.14"),
                    "u": UUID("00000000-0000-0000-0000-000000000001"),
                }
            )
        ).decode("ascii")
        obj = _load_json(json.dumps({"__x": marker}))
        restored = obj["__x"]
        assert restored["dt"] == datetime(2020, 1, 1)
        assert restored["td"] == timedelta(days=1)
        assert restored["dec"] == Decimal("3.14")
        assert str(restored["u"]) == "00000000-0000-0000-0000-000000000001"