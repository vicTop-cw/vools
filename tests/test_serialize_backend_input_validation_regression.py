# -*- coding: utf-8 -*-
"""回归测试：serialize 后端对象直用时缺少入参校验（BUG-351）。

顶层便捷函数（``vools.serialize.loads`` / ``loads_hex``）早已校验入参，
但**后端对象直接用**时没有：

    JsonBackend().loads(None)        # AttributeError: 'NoneType' object has no attribute 'decode'
    JsonBackend().loads("str")       # AttributeError: 'str' object has no attribute 'decode'
    MsgpackBackend().loads(None)     # TypeError: a bytes-like object is required, not 'NoneType'
    JsonBackend().loads_hex(None)    # TypeError: fromhex() argument must be str, not None

修复：BaseBackend 增加 _require_bytes() 与 loads_hex 校验（hex_str 必须 str/bytes）；
四个后端 loads() 开头统一调用 _require_bytes，错误信息带"类名.loads"。
"""

import pytest

from vools.serialize.backends.json_backend import JsonBackend
from vools.serialize.backends.msgpack_backend import MsgpackBackend
from vools.serialize.backends.pickle_backend import PickleBackend
from vools.serialize.backends.vb_json_backend import VBJsonBackend

BACKENDS = [JsonBackend, MsgpackBackend, VBJsonBackend, PickleBackend]
IDS = [cls.__name__ for cls in BACKENDS]


@pytest.fixture(params=BACKENDS, ids=IDS)
def backend(request):
    return request.param()


class TestLoadsValidation:
    @pytest.mark.parametrize("bad", [None, "str", 123, [1]])
    def test_non_bytes_rejected(self, backend, bad):
        with pytest.raises(TypeError) as ei:
            backend.loads(bad)
        assert "data" in str(ei.value)
        assert type(backend).__name__ in str(ei.value)

    def test_bytearray_accepted(self, backend):
        payload = backend.dumps({"a": 1})
        assert backend.loads(bytearray(payload)) == {"a": 1}

    def test_memoryview_accepted(self, backend):
        payload = backend.dumps({"a": 1})
        assert backend.loads(memoryview(payload)) == {"a": 1}


class TestLoadsHexValidation:
    @pytest.mark.parametrize("bad", [None, 123, 1.5])
    def test_non_str_bytes_rejected(self, backend, bad):
        with pytest.raises(TypeError) as ei:
            backend.loads_hex(bad)
        assert "hex_str" in str(ei.value)

    def test_bad_hex_value_still_loud(self, backend):
        with pytest.raises(ValueError):
            backend.loads_hex("zz")

    def test_hex_roundtrip(self, backend):
        assert backend.loads_hex(backend.dumps_hex({"k": [1, 2]})) == {"k": [1, 2]}

    def test_bytes_hex_accepted(self, backend):
        hex_bytes = backend.dumps_hex({"k": 1}).encode("ascii")
        assert backend.loads_hex(hex_bytes) == {"k": 1}


class TestTopLevelUnchanged:
    def test_dumps_loads_roundtrip(self):
        import vools.serialize as sr

        for fmt in ("json", "vb_json", "msgpack", "pickle"):
            assert sr.loads(sr.dumps({"a": [1, 2]}, fmt), fmt) == {"a": [1, 2]}

    def test_dumps_hex_loads_hex(self):
        import vools.serialize as sr

        for fmt in ("json", "vb_json", "msgpack", "pickle"):
            assert sr.loads_hex(sr.dumps_hex({"a": 1}, fmt), fmt) == {"a": 1}

    def test_top_level_loads_validation(self):
        import vools.serialize as sr

        with pytest.raises(TypeError):
            sr.loads(None, "json")
        with pytest.raises(TypeError):
            sr.loads_hex(None, "json")
