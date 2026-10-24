# -*- coding: utf-8 -*-
"""回归测试：Result.unwrap() 对非异常错误值的报错（BUG-436）。

``Result[T, E]`` 的 E 可以是任意类型，但原实现无条件 ``raise self._value``：

    Result.failure("e").unwrap()
    # TypeError: exceptions must derive from BaseException

看起来像 Result 自身的 bug，实际是"错误值不是异常"。修复后：错误值是
``BaseException`` 时照常抛出；否则抛带值与替代方案提示的 TypeError。
成功路径、``unwrap_or``/``unwrap_or_else``/``get_or_raise`` 语义不变。
"""

import pytest

from vools.functional.result import Result


class TestUnwrapSuccess:
    def test_success_returns_value(self):
        assert Result.success(1).unwrap() == 1
        assert Result.success(None).unwrap() is None


class TestUnwrapFailureWithException:
    def test_raises_original_exception(self):
        with pytest.raises(ValueError, match="boom"):
            Result.failure(ValueError("boom")).unwrap()

    def test_raises_custom_exception_subclass(self):
        class MyErr(Exception):
            pass

        with pytest.raises(MyErr):
            Result.failure(MyErr("custom")).unwrap()


class TestUnwrapFailureWithNonException:
    @pytest.mark.parametrize("bad", ["e", 123, None, 1.5, ["x"]])
    def test_clear_type_error(self, bad):
        with pytest.raises(TypeError) as ei:
            Result.failure(bad).unwrap()
        msg = str(ei.value)
        assert "unwrap" in msg
        assert repr(bad) in msg
        assert "BaseException" not in msg


class TestAlternativesUnchanged:
    def test_unwrap_or(self):
        assert Result.failure("e").unwrap_or(0) == 0
        assert Result.success(1).unwrap_or(0) == 1

    def test_unwrap_or_else(self):
        assert Result.failure("e").unwrap_or_else(lambda e: -1) == -1

    def test_get_or_raise(self):
        with pytest.raises(RuntimeError, match="boom"):
            Result.failure("e").get_or_raise(RuntimeError("boom"))
        assert Result.success(1).get_or_raise(RuntimeError("boom")) == 1
