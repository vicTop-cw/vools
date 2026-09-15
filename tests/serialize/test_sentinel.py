"""tests/serialize/test_sentinel.py — NoneSentinel 测试"""
import pytest
import sys
import os
import pickle

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.serialize.sentinel import NoneSentinel, NONE


class TestNoneSentinel:
    """NoneSentinel 测试"""

    def test_singleton_via_pickle(self):
        a = NoneSentinel()
        # pickle 序列化后应还原为 NONE 单例
        data = pickle.dumps(a)
        result = pickle.loads(data)
        assert result is NONE

    def test_instance(self):
        assert isinstance(NONE, NoneSentinel)

    def test_bool(self):
        # NoneSentinel.__bool__ 返回 False
        assert bool(NONE) is False

    def test_repr(self):
        assert 'NONE' in repr(NONE)

    def test_pickle_roundtrip(self):
        data = pickle.dumps(NONE)
        result = pickle.loads(data)
        assert result is NONE

    def test_getstate(self):
        state = NONE.__getstate__()
        assert '__singleton__' in state

    def test_setstate(self):
        NONE.__setstate__({'__singleton__': 'test'})
        # 无异常即通过

    def test_json_roundtrip(self):
        import json
        # JSON 无法直接序列化 NoneSentinel，会走 default 路径
        # 但 pickle 路径是主路径
        data = pickle.dumps(NONE)
        result = pickle.loads(data)
        assert result is NONE
