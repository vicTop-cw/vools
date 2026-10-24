# -*- coding: utf-8 -*-
"""回归测试：序列化后端对「不可保真映射键」发出可见告警（BUG-408）。

不同后端对映射键的表达能力不同，原实现一律静默：

1. **json / vb_json**：JSON 规范只允许字符串键 → int/float/bool 键被静默
   转成字符串，往返后键类型改变：

       loads(dumps({1: 'a'}, backend='json'), backend='json')   # -> {'1': 'a'}

2. **msgpack**：tuple 键被编码成 array key，读取端无法还原 → 写得进去、
   读不回来：

       loads(dumps({(1, 2): 'd'}, backend='msgpack'), backend='msgpack')
       # ValueError: list is not allowed for map key

修复：`dumps` 时做一次**有界**键扫描（`MAX_SCAN_NODES` 上限），发现不可保真
键时发 `RuntimeWarning`（含样例键与替代方案）；**不改变序列化结果**，与
json 标准库/msgpack 既有行为保持一致。pickle 无此限制、不受影响。
"""

import warnings

import pytest

from vools.serialize import dumps, loads
from vools.serialize.backends._keycheck import (
    MAX_SCAN_NODES,
    find_non_scalar_msgpack_keys,
    find_non_str_keys,
)


def _warnings_of(fn):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        fn()
    return [w for w in caught if issubclass(w.category, RuntimeWarning)]


class TestJsonBackendsWarn:
    @pytest.mark.parametrize('backend', ['json', 'vb_json'])
    @pytest.mark.parametrize('payload', [
        {1: 'a'}, {1.5: 'b'}, {True: 'c'},
        {'outer': {2: 'nested'}},
        [{'k': 1}, {3: 'v'}],
    ])
    def test_non_str_keys_warn(self, backend, payload):
        assert len(_warnings_of(lambda: dumps(payload, backend=backend))) == 1

    @pytest.mark.parametrize('backend', ['json', 'vb_json'])
    def test_string_keys_do_not_warn(self, backend):
        assert _warnings_of(
            lambda: dumps({'a': 1, 'b': {'c': [1, 2]}}, backend=backend)) == []

    @pytest.mark.parametrize('backend', ['json', 'vb_json'])
    def test_result_unchanged(self, backend):
        # 行为保持：JSON 仍把 int 键转成字符串（不抛错、不改契约）
        assert loads(dumps({1: 'a'}, backend=backend), backend=backend) == {'1': 'a'}


class TestMsgpackWarn:
    def test_tuple_key_warns(self):
        assert len(_warnings_of(
            lambda: dumps({(1, 2): 'd'}, backend='msgpack'))) == 1

    def test_frozenset_key_warns(self):
        assert len(_warnings_of(
            lambda: dumps({frozenset({1}): 'd'}, backend='msgpack'))) == 1

    def test_scalar_keys_do_not_warn(self):
        assert _warnings_of(
            lambda: dumps({1: 'a', 'k': 2, 1.5: 3}, backend='msgpack')) == []

    def test_roundtrip_fidelity_for_scalar_keys(self):
        assert loads(dumps({1: 'a'}, backend='msgpack'),
                     backend='msgpack') == {1: 'a'}


class TestPickleUnrestricted:
    def test_tuple_keys_roundtrip_without_warning(self):
        payload = {(1, 2): 'd'}
        assert _warnings_of(lambda: dumps(payload, backend='pickle')) == []
        assert loads(dumps(payload, backend='pickle'), backend='pickle') == payload


class TestKeyCheckHelper:
    def test_sampling_capped(self):
        payload = {i: 'v' for i in range(100)}
        samples, truncated = find_non_str_keys(payload)
        assert len(samples) == 5
        assert truncated is False

    def test_bounded_scan(self):
        # 超过扫描预算时 truncated=True（不保证穷举）
        deep = {'k': [{'k': [{i: i} for i in range(50)]}]}
        samples, truncated = find_non_str_keys(deep)
        assert isinstance(samples, list)
        assert MAX_SCAN_NODES == 10000

    def test_msgpack_helper_only_flags_non_scalar(self):
        samples, _ = find_non_scalar_msgpack_keys({(1,): 1, 'a': 2, 3: 4})
        assert samples == [(1,)]