# -*- coding: utf-8 -*-
"""不变量测试：任务载荷（args/kwargs/result）的类型对称性（BUG-334）。

`vools/task/core` 的载荷通道：`_dump_json` 用 pickle 标记写出非 JSON 原生
对象，`_safe_pickle_loads` 用受限白名单（BUG-207）读回。历史上写入侧与
读取侧多次漂移，导致「任务实参/返回值被静默换成标记字符串」：

- BUG-331：白名单缺 vools 数据类型（Table/Qax/VList...）；
- BUG-334：白名单缺 `bytearray`/`pathlib`/用户枚举；且 `IntEnum`/`VText` 这类
  **int/str 子类**会被 `json.dumps` 原生编码成数字/字符串（不触发 default），
  类型直接丢失。

修复：
1. 白名单补 `bytearray`、`pathlib.*`、vools 数据类型；
2. 用户枚举按「模块白名单（enum/__main__/vools*/tests*）+ 必须 issubclass(Enum)」
   放行，非枚举类仍拒绝；
3. `_dump_json` 增加预转换：Enum 实例与非原生 str 子类先打成 pickle 标记，
   普通 str/int 不受影响。

本测试把「常见类型 × 载荷位置」的往返固化为不变量，防止再次漂移。
"""

import datetime
import decimal
import enum
import pathlib
import pickle
import base64
import uuid
import warnings

import pytest

from vools.data.qax import Qax
from vools.data.table import Table
from vools.data.vlist import VList
from vools.data.vtext import VText
from vools.task.core.models import _dump_json, _json_prepare, _load_json


class _Color(enum.Enum):
    RED = 'r'


class _NotEnum:
    """模块级非枚举类（局部类无法 pickle，用于拒绝路径验证）。"""
    pass


class _Num(enum.IntEnum):
    ONE = 1


class _Str(enum.StrEnum if hasattr(enum, 'StrEnum') else str, enum.Enum):
    X = 'x'


# 期望「原类型往返」的样本
SAMPLES = {
    'datetime': datetime.datetime(2026, 1, 2, 3, 4, 5),
    'date': datetime.date(2026, 1, 2),
    'timedelta': datetime.timedelta(days=1),
    'Decimal': decimal.Decimal('1.25'),
    'UUID': uuid.UUID('12345678-1234-5678-1234-567812345678'),
    'set': {1, 2},
    'frozenset': frozenset({3}),
    'complex': 1 + 2j,
    'bytes': b'\x00\xff',
    'bytearray': bytearray(b'xy'),
    'PurePosixPath': pathlib.PurePosixPath('/a/b'),
    'Path': pathlib.Path('a/b'),
    'Enum': _Color.RED,
    'IntEnum': _Num.ONE,
    'VText': VText('abc'),
    'Table': Table([[1, 'a']], columns=['id', 'name']),
    'Qax': Qax([[1, 'a']], columns=['id', 'name']),
    'VList': VList([1, 2]),
}


@pytest.mark.parametrize('name', sorted(SAMPLES))
@pytest.mark.parametrize('position', ['args', 'kwargs', 'result'])
def test_payload_position_roundtrip(name, position):
    """args / kwargs / result 三个位置都必须原类型往返。"""
    obj = SAMPLES[name]
    if position == 'args':
        payload = [obj]
    elif position == 'kwargs':
        payload = {'k': obj}
    else:
        payload = obj
    back = _load_json(_dump_json(payload))
    if position == 'args':
        back = back[0]
    elif position == 'kwargs':
        back = back['k']
    assert type(back) is type(obj), (
        f'{name} @ {position} 类型漂移: {type(obj).__name__} -> {type(back).__name__}')
    if not isinstance(obj, (Table, Qax, VList, VText)):
        assert back == obj


class TestPrimitivesUnaffected:
    @pytest.mark.parametrize('obj', [42, 3.14, 'abc', True, False, None,
                                     [1, 'a'], {'k': [1, None]}])
    def test_plain_values(self, obj):
        back = _load_json(_dump_json(obj))
        assert back == obj
        assert type(back) is type(obj)

    def test_user_string_looking_like_marker_not_wrapped(self):
        # 普通 str 不会被预转换包装（只有非原生 str 子类才打标记）
        prepared = _json_prepare('__vools_pickle__:abc')
        assert prepared == '__vools_pickle__:abc'


class TestSecurityUnchanged:
    def _marker(self, obj):
        return '__vools_pickle__:' + base64.b64encode(pickle.dumps(obj)).decode()

    def test_malicious_reduce_rejected(self):
        import os

        class Evil:
            def __reduce__(self):
                return (os.system, ('echo SHOULD_NOT_RUN',))

        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter('always')
            back = _load_json('["' + self._marker(Evil()) + '"]')
        assert isinstance(back[0], str)
        assert ws, '拒绝时应告警，不静默'

    def test_non_enum_user_class_rejected(self):
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter('always')
            back = _load_json('["' + self._marker(_NotEnum()) + '"]')
        assert isinstance(back[0], str)
        assert ws

    def test_enum_from_allowed_module_accepted(self):
        # _Color 定义在 tests 前缀模块里 -> 枚举白名单放行
        back = _load_json(_dump_json([_Color.RED]))[0]
        assert type(back) is _Color