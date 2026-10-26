# -*- coding: utf-8 -*-
"""回归测试：serialize.loads / loads_hex 的输入类型校验（BUG-497）。

修复前把类型错误留给底层：

    loads("str")        # TypeError: a bytes-like object is required, not 'str'
    loads(None)         # TypeError: a bytes-like object is required, not 'NoneType'
    loads_hex(None)     # TypeError: fromhex() argument must be str

错误信息看不出是**哪个参数**、也不提示期望类型。修复后入口即校验并带参数名；
同时 ``loads_hex`` 现在也接受 bytes 形式的十六进制串（``bytes.fromhex`` 本就支持）。

另：本轮把 pickle 后端的**不安全反序列化**声明写进 docstring
（``loads``/``loads_hex`` 的 Raises/安全提示），处理不可信输入应显式用 json。
"""

import pytest

import vools.serialize as se


@se.serializable(backend="pickle")
class Payload:
    """模块级类：pickle 后端要求类可被导入（不能定义在测试函数内）。"""

    def __init__(self, name):
        self.name = name


class Vec:
    """模块级类：用于 register_type 往返。"""

    def __init__(self, x, y):
        self.x, self.y = x, y

    def __eq__(self, other):
        return isinstance(other, Vec) and (self.x, self.y) == (other.x, other.y)


@pytest.fixture(autouse=True)
def _pickle_backend():
    previous = se.get_default_backend()
    se.set_default_backend("pickle")
    yield
    if previous:
        se.set_default_backend(previous)


class TestLoadsInputType:
    @pytest.mark.parametrize("bad", ["str", None, 123, 1.5, [1]])
    def test_rejected_with_param_name(self, bad):
        with pytest.raises(TypeError) as ei:
            se.loads(bad)
        assert "data" in str(ei.value)

    @pytest.mark.parametrize("good", [b"", bytearray(), memoryview(b"")])
    def test_byte_like_accepted(self, good):
        # 空字节串仍然走底层 EOFError，而不是被类型校验拦下
        with pytest.raises(Exception) as ei:
            se.loads(good)
        assert not isinstance(ei.value, TypeError) or "data" not in str(ei.value)

    def test_roundtrip_bytes(self):
        assert se.loads(se.dumps({"a": 1})) == {"a": 1}

    def test_roundtrip_bytearray(self):
        assert se.loads(bytearray(se.dumps({"a": 1}))) == {"a": 1}

    def test_roundtrip_memoryview(self):
        assert se.loads(memoryview(se.dumps({"a": 1}))) == {"a": 1}


class TestLoadsHexInputType:
    @pytest.mark.parametrize("bad", [None, 123, [1]])
    def test_rejected_with_param_name(self, bad):
        with pytest.raises(TypeError) as ei:
            se.loads_hex(bad)
        assert "hex_str" in str(ei.value)

    def test_roundtrip_str(self):
        assert se.loads_hex(se.dumps_hex({"a": 1})) == {"a": 1}

    def test_roundtrip_bytes(self):
        assert se.loads_hex(se.dumps_hex({"a": 1}).encode()) == {"a": 1}

    def test_invalid_hex_still_loud(self):
        with pytest.raises(ValueError):
            se.loads_hex("zz")


class TestBackendSemanticsUnchanged:
    def test_unknown_backend_message(self):
        with pytest.raises(ValueError) as ei:
            se.loads(b"{}", backend="bogus")
        assert "Unknown backend" in str(ei.value)

    def test_json_backend_roundtrip(self):
        data = se.dumps({"a": [1, 2]}, backend="json")
        assert se.loads(data, backend="json") == {"a": [1, 2]}

    def test_default_backend_set(self):
        before = se.get_default_backend()
        try:
            se.set_default_backend("json")
            assert se.get_default_backend() == "json"
        finally:
            if before:
                se.set_default_backend(before)


class TestSerializableDecoratorContract:
    def test_adds_classmethods(self):
        data = Payload.serialize(Payload("abc"))
        assert isinstance(data, bytes)
        assert Payload.deserialize(data).name == "abc"

    def test_bare_decorator(self):
        @se.serializable
        class Bare:
            pass

        assert hasattr(Bare, "serialize")
        assert hasattr(Bare, "deserialize")


class TestRegisterTypeContract:
    def test_roundtrip_registered_type(self):
        se.register_type(
            Vec, "Vec",
            serialize=lambda v: [v.x, v.y],
            deserialize=lambda pair: Vec(*pair),
        )
        assert se.loads(se.dumps(Vec(1, 2))) == Vec(1, 2)
        assert se.get_type_handler(Vec(1, 2))[0] == "Vec"

    def test_non_type_rejected(self):
        with pytest.raises(TypeError):
            se.register_type(123)
