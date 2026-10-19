"""
BUG-186 回归：CallableHandler 中悬空的 @abstractmethod 曾错位应用到
具体方法 do，导致继承 CallableHandler 但未 override do 的自定义 handler
实例化抛 TypeError。修复后 do 恢复为普通方法，其余抽象语义不受影响。
"""

from typing import Any, Dict

import pytest

from vools.serialize.callable import CallableHandler


class MinimalHandler(CallableHandler):
    """只实现 can_handle/get_state/restore，未 override do。"""

    def can_handle(self, obj: Any) -> bool:
        return callable(obj)

    def get_state(self, obj: Any) -> Dict[str, Any]:
        return {"name": getattr(obj, "__name__", None)}

    def restore(self, state: Dict[str, Any]) -> Any:
        return None


class MissingRestoreHandler(CallableHandler):
    """故意不实现 restore，验证抽象语义未被破坏。"""

    def can_handle(self, obj: Any) -> bool:
        return False

    def get_state(self, obj: Any) -> Dict[str, Any]:
        return {}


def test_subclass_without_do_can_instantiate():
    """未 override do 的合法子类必须能实例化（BUG-186）。"""
    handler = MinimalHandler()
    assert handler is not None
    assert handler.handler_name == "MinimalHandler"


def test_do_remains_concrete_and_chainable():
    """do 必须是普通方法：调用返回 self，且副作用函数被调用。"""
    handler = MinimalHandler()
    calls = []

    result = handler.do(f=lambda x: calls.append(x))
    assert result is handler
    assert calls == [handler]


class NoRestoreHandler(CallableHandler):
    """未实现 restore（非抽象，但基类体 raise），验证运行期仍失败。"""

    def can_handle(self, obj: Any) -> bool:
        return False

    def get_state(self, obj: Any) -> Dict[str, Any]:
        return {}


def test_restore_abstract_semantics_preserved():
    """修复只移除 do 的抽象；can_handle/get_state 仍是抽象方法。"""
    assert "can_handle" in CallableHandler.__abstractmethods__
    assert "get_state" in CallableHandler.__abstractmethods__
    assert "do" not in CallableHandler.__abstractmethods__

    # restore 无 @abstractmethod，但实现体直接 raise，调用仍必须失败。
    handler = NoRestoreHandler()
    with pytest.raises(NotImplementedError):
        handler.restore({})