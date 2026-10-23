# -*- coding: utf-8 -*-
"""不变量测试：类型注册表 × 全部后端 的往返对称性（BUG-333 及防漂移）。

背景：`vools.serialize` 的**写入侧**（`vools_preprocess`/`vools_default`/
`vools_object_hook`）与**读取侧**的各类白名单（`_ALLOWED_IMPORT_MODULES`、
`_SafeUnpickler._ALLOWED`）历史上多次漂移，产生「写入成功、读回静默降级」
的问题（BUG-303/309/325/331/332）。本测试把「注册表里的每个类型 × 每个
可用后端 都必须原类型往返」固化成不变量，任何新类型/新后端漏接都会被它抓住。

BUG-333 具体覆盖：pathlib 处理器曾丢失**具体风格**——
`PurePosixPath('/a/b')` 在 Windows 上往返成 `PureWindowsPath`；具体
`pathlib.Path` 还会退化成 `Pure*`（丢失 exists/read_text 等 IO 能力）。
修复后在 `{'path':...}` 基础上记录 `flavor`（posix/windows）与 `concrete`。
"""

import datetime
import decimal
import enum
import fractions
import pathlib
import uuid

import pytest

from vools.serialize import MSGPACK_AVAILABLE, dumps, loads
from vools.serialize.type_registry import _TYPE_HANDLERS, _deserialize_path

BACKENDS = ['json', 'vb_json', 'pickle'] + (['msgpack'] if MSGPACK_AVAILABLE else [])


class _Color(enum.Enum):
    RED = 'r'
    BLUE = 'b'


# 注册表里每个类型的一个代表实例（新增注册类型时应同步补这里）
SAMPLES = {
    'datetime': datetime.datetime(2026, 1, 2, 3, 4, 5),
    'date': datetime.date(2026, 1, 2),
    'time': datetime.time(3, 4, 5),
    'timedelta': datetime.timedelta(days=1, seconds=2),
    'complex': 1 + 2j,
    'Decimal': decimal.Decimal('1.25'),
    'Fraction': fractions.Fraction(1, 3),
    'Enum': _Color.RED,
    'bytearray': bytearray(b'xy'),
    'set': {1, 2},
    'frozenset': frozenset({3}),
    'uuid': uuid.UUID('12345678-1234-5678-1234-567812345678'),
    'PurePosixPath': pathlib.PurePosixPath('/a/b'),
    'PureWindowsPath': pathlib.PureWindowsPath('C:/a/b'),
    'Path': pathlib.Path('a/b'),
}


def test_samples_cover_registry():
    """注册表里的每个类型都应有样本，否则本不变量测试本身会漏测。"""
    registered = {t.__name__ for t in _TYPE_HANDLERS}
    covered = set()
    for name, obj in SAMPLES.items():
        for t in _TYPE_HANDLERS:
            if isinstance(obj, t):
                covered.add(t.__name__)
    # PurePath 处理器覆盖三种路径样本；Enum 覆盖 _Color
    missing = registered - covered
    assert not missing, f'注册类型缺少样本: {sorted(missing)}'


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('name', sorted(SAMPLES))
def test_roundtrip_preserves_type(backend, name):
    obj = SAMPLES[name]
    back = loads(dumps(obj, backend=backend), backend=backend)
    assert type(back) is type(obj), (
        f'{name} 经 {backend} 往返后类型漂移: {type(obj).__name__} -> {type(back).__name__}')
    assert back == obj


class TestPathFlavor:
    @pytest.mark.parametrize('backend', BACKENDS)
    def test_posix_flavor_preserved(self, backend):
        p = pathlib.PurePosixPath('/a/b')
        back = loads(dumps(p, backend=backend), backend=backend)
        assert type(back) is pathlib.PurePosixPath
        assert back.parts == ('/', 'a', 'b')

    @pytest.mark.parametrize('backend', BACKENDS)
    def test_windows_flavor_preserved(self, backend):
        p = pathlib.PureWindowsPath('C:/a/b')
        back = loads(dumps(p, backend=backend), backend=backend)
        assert type(back) is pathlib.PureWindowsPath

    @pytest.mark.parametrize('backend', BACKENDS)
    def test_concrete_path_keeps_io_methods(self, backend):
        # 修复前：具体 Path 退化成 Pure*，exists/read_text 全部 AttributeError
        back = loads(dumps(pathlib.Path('a/b'), backend=backend), backend=backend)
        assert hasattr(back, 'exists') and callable(back.exists)
        assert isinstance(back.exists(), bool)

    def test_pure_path_has_no_io_methods(self):
        back = loads(dumps(pathlib.PurePosixPath('/a'), backend='json'),
                     backend='json')
        assert not hasattr(back, 'read_text')

    def test_legacy_payload_without_flavor(self):
        # 旧 payload 只有 {'path': ...} -> 保持历史行为（平台默认 PurePath）
        assert type(_deserialize_path({'path': 'x/y'})) is type(
            pathlib.PurePath('x/y'))