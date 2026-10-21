# -*- coding: utf-8 -*-
"""回归测试：py3.6 fromisoformat 兼容分支保留时区（BUG-242）。

原 py3.6 分支的正则允许 `Z`/`±HH:MM` 后缀，但构造 datetime 时**从不传入
tzinfo**——带时区输入被静默当 naive 时间：
- `'2024-01-01T10:30:00+08:00'` → tzinfo None（stdlib py3.7+ 保留 UTC+08:00）
- 同一 UTC 时刻的两个值相减得到 8 小时差（stdlib 为 0）
- `time_fromisoformat('10:30:00+08:00')` → ValueError（stdlib 接受）

修复：正则捕获时区组，`_parse_tzinfo` 构造 tzinfo（Z→UTC、±HH:MM→timezone），
datetime/time 两个解析器都传递 tzinfo，行为与 stdlib py3.7+ 对齐。

测试方式：py3.11 上无法直接导入 3.6 分支（被 `_HAS_FROMISOFORMAT` 门挡住），
故用 AST 提取 else 分支源码后 exec，再与 stdlib 逐项对拍。
"""

import ast
import datetime
import os

import pytest


def _load_py36_branch():
    """提取并执行 core/datetime_compat.py 的 py3.6 兼容分支。"""
    path = os.path.join(os.path.dirname(__file__), "..", "vools", "core",
                        "datetime_compat.py")
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    else_body = next(
        n.orelse for n in tree.body
        if isinstance(n, ast.If) and '_HAS_FROMISOFORMAT' in ast.unparse(n.test))
    mod = ast.Module(body=else_body, type_ignores=[])
    ast.fix_missing_locations(mod)
    ns = {'datetime': datetime}
    exec(compile(mod, "<py36branch>", "exec"), ns)
    return ns['datetime_fromisoformat'], ns['time_fromisoformat']


_F_DT, _F_TIME = _load_py36_branch()


class TestDatetimeTimezonePreserved:
    """BUG-242 核心：带时区后缀返回 aware datetime（与 stdlib 一致）。"""

    @pytest.mark.parametrize("s", [
        "2024-01-01T10:30:00",
        "2024-01-01 10:30:00",
        "2024-01-01T10:30:00.123456",
        "2024-01-01T10:30",
    ])
    def test_without_tz_matches_stdlib(self, s):
        got = _F_DT(s)
        std = datetime.datetime.fromisoformat(s)
        assert got == std
        assert got.tzinfo is None

    @pytest.mark.parametrize("s", [
        "2024-01-01T10:30:00+08:00",
        "2024-01-01T10:30:00-05:30",
        "2024-01-01T10:30:00+00:00",
        "2024-01-01T10:30:00Z",
    ])
    def test_with_tz_matches_stdlib(self, s):
        got = _F_DT(s)
        std = datetime.datetime.fromisoformat(s)
        assert got == std
        assert got.tzinfo is not None
        # 关键：时区偏移一致（修复前 tzinfo 为 None）
        assert got.utcoffset() == std.utcoffset()

    def test_same_utc_instant_zero_diff(self):
        # 同一 UTC 时刻：修复前算出 8 小时差
        a = _F_DT('2024-01-01T10:00:00+08:00')
        b = _F_DT('2024-01-01T02:00:00+00:00')
        assert (a - b) == datetime.timedelta(0)

    def test_z_suffix_is_utc(self):
        got = _F_DT('2024-01-01T10:30:00Z')
        assert got.tzinfo == datetime.timezone.utc
        assert got.utcoffset() == datetime.timedelta(0)


class TestTimeTimezone:
    """time_fromisoformat 的时区支持（修复前直接 ValueError）。"""

    @pytest.mark.parametrize("s", [
        "10:30:00",
        "10:30",
        "10:30:00.5",
        "10:30:00+08:00",
    ])
    def test_matches_stdlib(self, s):
        got = _F_TIME(s)
        std = datetime.time.fromisoformat(s)
        assert got == std
        assert got.utcoffset() == std.utcoffset()


class TestInvalidStillRejected:
    """非法输入仍明确 ValueError（防修复过度）。"""

    @pytest.mark.parametrize("bad", [
        "not-a-date", "2024-13-01T00:00:00", "2024-01-01T25:00:00", "",
    ])
    def test_invalid_raises(self, bad):
        with pytest.raises(ValueError):
            _F_DT(bad)