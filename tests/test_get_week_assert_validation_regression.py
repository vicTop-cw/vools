# -*- coding: utf-8 -*-
"""回归测试：get_week 入参校验不依赖 assert（BUG-240）。

原 `get_week` 用 `assert` 做公开入参校验（weekday 1-7、日期长度 8|10）——
`python -O` 会剥离 assert，优化部署下校验整体消失（非法 weekday=0 静默
算出错误周起始日），且非 -O 下抛 `AssertionError` 不便业务捕获。

修复：两处 assert 改显式 `ValueError`（BUG-7 同族收口），合法路径零变化。
"""

import subprocess
import sys

import pytest

from vools.datetime.utils import get_week


class TestValidationUnderNormalMode:
    """常规模式下非法输入抛 ValueError（非 AssertionError）。"""

    @pytest.mark.parametrize("bad", [0, 8, -1, 100])
    def test_invalid_weekday(self, bad):
        with pytest.raises(ValueError, match="weekday 必须在 1-7"):
            get_week('20240101', weekday=bad)

    @pytest.mark.parametrize("bad", ['2024010', '2024-1-1x', '24'])
    def test_invalid_length(self, bad):
        with pytest.raises(ValueError, match="长度必须为 8 或 10"):
            get_week(bad)


class TestValidationUnderOptimizeMode:
    """BUG-240 核心：-O 优化模式下校验仍然生效（assert 会被剥离）。"""

    def test_optimize_mode_still_validates(self):
        code = (
            "from vools.datetime.utils import get_week\n"
            "for bad in (0, 8, -1):\n"
            "    try:\n"
            "        get_week('20240101', weekday=bad)\n"
            "    except ValueError:\n"
            "        continue\n"
            "    raise SystemExit('weekday not rejected under -O: ' + repr(bad))\n"
            "try:\n"
            "    get_week('2024010')\n"
            "except ValueError:\n"
            "    pass\n"
            "else:\n"
            "    raise SystemExit('length not rejected under -O')\n"
        )
        r = subprocess.run([sys.executable, '-O', '-c', code],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


class TestLegalPathsUnchanged:
    """合法路径零变化（防修复过度）。"""

    def test_none_returns_none(self):
        assert get_week(None) is None

    def test_default_monday(self):
        # 2024-01-01 是周一
        assert get_week('20240101') == '20240101'

    def test_mid_week(self):
        assert get_week('2024-01-03') == '2024-01-01'

    def test_week_offset(self):
        assert get_week('20240101', num=1) == '20231225'

    def test_dash_format_preserved(self):
        assert get_week('2024-01-03') == '2024-01-01'