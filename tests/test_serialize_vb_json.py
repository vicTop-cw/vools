"""
BUG-185 回归：VBJsonBackend.parse 对畸形字面量不得无限循环挂死。

根因：_parse_boolean / _parse_null / _parse_number 在失败路径只 append
错误而不推进 index[0]，_parse_array 的 while True 会原地重进同一字符。
"""

import concurrent.futures as cf

import pytest

from vools.serialize.backends.vb_json_backend import VBJsonBackend


def _parse(b, raw, timeout=3.0):
    """在独立线程里解析，超过 timeout 视为回归（原实现会永久挂死）。"""
    with cf.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(b.parse, raw).result(timeout=timeout)


HANG_CASES = [
    "[tru]",
    "[nul]",
    '["ok", tru]',
    "[tru, 1]",
    "[nulx]",
]


@pytest.mark.parametrize("raw", HANG_CASES)
def test_malformed_literals_do_not_hang(raw):
    """畸形 true/false/null 字面量必须有限时间内返回并记录错误。"""
    b = VBJsonBackend()
    result = _parse(b, raw)
    assert isinstance(result, list)
    assert b.get_errors(), "畸形输入应记录至少一条错误"


def test_valid_input_still_parses():
    """正常输入不受修复影响，仍解析正确且无错误记录。"""
    b = VBJsonBackend()
    assert _parse(b, "[1,2,3]") == [1, 2, 3]
    assert _parse(b, '{"a":1}') == {"a": 1}
    assert _parse(b, "[true, false, null]") == [True, False, None]
    assert not b.get_errors()