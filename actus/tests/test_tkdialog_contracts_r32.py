"""tkdialog 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- validate_spec/validate_options/validate_fields 校验失效 → 非法参数进入 GUI 层
- GUI 层收到坏参数 → 崩溃或行为异常
"""
import pytest


class TestValidateSpec:
    def test_valid_spec(self):
        """退步了会怎样：合法 spec 应返回 None。"""
        from vools.actus.tkdialog import validate_spec
        assert validate_spec("消息", "locked", 5, "info") is None

    def test_none_message_ok(self):
        """退步了会怎样：message=None 应合法（无消息模式）。"""
        from vools.actus.tkdialog import validate_spec
        assert validate_spec(None, "locked", 5, "info") is None

    def test_message_too_long(self):
        """退步了会怎样：message > 2000 字符应报错。"""
        from vools.actus.tkdialog import validate_spec
        err = validate_spec("x" * 2001, "locked", 5, "info")
        assert err is not None
        assert err["code"] == "param_invalid"

    def test_message_non_string(self):
        """退步了会怎样：message 非字符串应报错。"""
        from vools.actus.tkdialog import validate_spec
        err = validate_spec(123, "locked", 5, "info")
        assert err is not None
        assert "字符串" in err["message"]

    def test_invalid_focus_policy(self):
        """退步了会怎样：非法 focus_policy 应报错。"""
        from vools.actus.tkdialog import validate_spec
        err = validate_spec("消息", "invalid", 5, "info")
        assert err is not None
        assert "focus_policy" in err["message"]

    def test_invalid_kind(self):
        """退步了会怎样：非法 kind 应报错。"""
        from vools.actus.tkdialog import validate_spec
        err = validate_spec("消息", "locked", 5, "invalid")
        assert err is not None
        assert "kind" in err["message"]

    def test_timeout_out_of_range(self):
        """退步了会怎样：timeout_seconds 超出范围应报错。"""
        from vools.actus.tkdialog import validate_spec
        err = validate_spec("消息", "locked", 0, "info")
        assert err is not None
        assert "timeout_seconds" in err["message"]

    def test_timeout_non_numeric(self):
        """退步了会怎样：timeout_seconds 非数字应报错。"""
        from vools.actus.tkdialog import validate_spec
        err = validate_spec("消息", "locked", "abc", "info")
        assert err is not None
        assert "数字" in err["message"]

    def test_timeout_none_ok(self):
        """退步了会怎样：timeout_seconds=None 应合法（无超时）。"""
        from vools.actus.tkdialog import validate_spec
        assert validate_spec("消息", "locked", None, "info") is None


class TestValidateOptions:
    def test_valid_options(self):
        """退步了会怎样：合法 options 应返回 None。"""
        from vools.actus.tkdialog import validate_options
        assert validate_options(["选项A", "选项B"]) is None

    def test_empty_options(self):
        """退步了会怎样：空 options 应报错。"""
        from vools.actus.tkdialog import validate_options
        err = validate_options([])
        assert err is not None
        assert "非空数组" in err["message"]

    def test_too_many_options(self):
        """退步了会怎样：options > 20 项应报错。"""
        from vools.actus.tkdialog import validate_options
        err = validate_options([f"opt{i}" for i in range(21)])
        assert err is not None
        assert "20" in err["message"]

    def test_option_too_long(self):
        """退步了会怎样：单 option > 60 字符应报错。"""
        from vools.actus.tkdialog import validate_options
        err = validate_options(["x" * 61])
        assert err is not None
        assert "60" in err["message"]

    def test_option_non_string(self):
        """退步了会怎样：option 非字符串应报错。"""
        from vools.actus.tkdialog import validate_options
        err = validate_options([123])
        assert err is not None
        assert "字符串" in err["message"]

    def test_options_not_list(self):
        """退步了会怎样：options 非列表应报错。"""
        from vools.actus.tkdialog import validate_options
        err = validate_options("not a list")
        assert err is not None
        assert "非空数组" in err["message"]


class TestValidateFields:
    def test_valid_fields(self):
        """退步了会怎样：合法 fields 应返回 None。"""
        from vools.actus.tkdialog import validate_fields
        assert validate_fields([
            {"key": "name", "label": "姓名"},
            {"key": "age", "label": "年龄", "type": "text"},
        ]) is None

    def test_empty_fields(self):
        """退步了会怎样：空 fields 应报错。"""
        from vools.actus.tkdialog import validate_fields
        err = validate_fields([])
        assert err is not None
        assert "非空数组" in err["message"]

    def test_too_many_fields(self):
        """退步了会怎样：fields > 12 个应报错。"""
        from vools.actus.tkdialog import validate_fields
        err = validate_fields([{"key": f"f{i}", "label": f"L{i}"} for i in range(13)])
        assert err is not None
        assert "12" in err["message"]

    def test_duplicate_key(self):
        """退步了会怎样：重复 key 应报错。"""
        from vools.actus.tkdialog import validate_fields
        err = validate_fields([
            {"key": "name", "label": "A"},
            {"key": "name", "label": "B"},
        ])
        assert err is not None
        assert "重复" in err["message"]

    def test_invalid_key_format(self):
        """退步了会怎样：非法 key 格式应报错。"""
        from vools.actus.tkdialog import validate_fields
        err = validate_fields([{"key": "INVALID-KEY", "label": "A"}])
        assert err is not None
        assert "key" in err["message"]

    def test_select_with_invalid_options(self):
        """退步了会怎样：select 类型无 options 应报错。"""
        from vools.actus.tkdialog import validate_fields
        err = validate_fields([{"key": "choice", "label": "选择", "type": "select"}])
        assert err is not None

    def test_checkbox_default_must_be_bool(self):
        """退步了会怎样：checkbox default 非布尔应报错。"""
        from vools.actus.tkdialog import validate_fields
        err = validate_fields([{"key": "agree", "label": "同意", "type": "checkbox", "default": "yes"}])
        assert err is not None
        assert "布尔" in err["message"]

    def test_select_default_not_in_options(self):
        """退步了会怎样：select default 不在 options 中应报错。"""
        from vools.actus.tkdialog import validate_fields
        err = validate_fields([
            {"key": "choice", "label": "选择", "type": "select",
             "options": ["A", "B"], "default": "C"},
        ])
        assert err is not None
        assert "options" in err["message"]

    def test_field_not_dict(self):
        """退步了会怎样：field 非 dict 应报错。"""
        from vools.actus.tkdialog import validate_fields
        err = validate_fields([{"key": "a", "label": "A"}, "not a dict"])
        assert err is not None
        assert "对象" in err["message"]
