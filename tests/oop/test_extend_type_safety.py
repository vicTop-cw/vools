# -*- coding: utf-8 -*-
"""tests/oop/test_extend_type_safety.py — clone() 类型注解沙箱安全（钉 BUG-95）

BUG-95: _process_args 用 ``eval(tp.strip())`` 求值类型注解字符串，
默认 __builtins__ 允许任意代码执行。实测
``clone('name:__import__("os").system("echo PWNED > marker") => 1')``
成功创建 marker 文件。

修复：用 _TYPE_NAME_WHITELIST 类型名查找表替代 eval，
仅允许 str/int/float/bool/list/dict/tuple/set/frozenset/bytes/
bytearray/complex/object/type 等白名单内类型名。
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.oop.extend import clone  # noqa: E402


class TestExtendTypeRCE:
    """clone() 类型注解不得 RCE"""

    def test_rce_via_type_annotation_blocked(self, tmp_path):
        marker = tmp_path.as_posix() + "/pwned.txt"
        expr = f'name:__import__("os").system("echo PWNED > \\"{marker}\\"") => 1'

        @clone(expr)
        class Foo:
            pass

        assert not os.path.exists(marker), "RCE via type annotation should be blocked"

    def test_os_access_blocked(self):
        @clone('name:__import__("os") => 1')
        class Foo:
            pass

        # Should not raise; type is None
        f = Foo()
        assert f.name == 1


class TestExtendTypeNormal:
    """正常类型注解不受影响"""

    def test_str(self):
        @clone('name:str => "hello"')
        class Foo:
            pass

        f = Foo()
        assert f.name == "hello"

    def test_int(self):
        @clone('count:int => 42')
        class Foo:
            pass

        f = Foo()
        assert f.count == 42

    def test_list(self):
        @clone('data:list => [1, 2, 3]')
        class Foo:
            pass

        f = Foo()
        assert f.data == [1, 2, 3]

    def test_unknown_type_does_not_crash(self):
        @clone('bad:UnknownType => 1')
        class Foo:
            pass

        f = Foo()
        assert f.bad == 1