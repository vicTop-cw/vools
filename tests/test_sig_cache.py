"""vools.sig_cache 功能验证测试"""
import sys
import os
import builtins

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.sig_cache import (
    get_signature, add_custom_sig, cached_getsignature,
    clear_cache, cache_info,
)
from inspect import Signature, Parameter

P = Parameter.POSITIONAL_OR_KEYWORD


class TestSigCache:
    """测试 sig_cache 模块"""

    def setup_method(self):
        """在每个测试方法前清理缓存"""
        clear_cache()

    def teardown_method(self):
        """在每个测试方法后清理缓存"""
        clear_cache()

    def test_get_signature_basic(self):
        """测试 get_signature 基本功能"""
        sig = get_signature(print)
        assert isinstance(sig, Signature)
        params = [p.name for p in sig.parameters.values()]
        assert 'sep' in params and 'end' in params
        
        sig2 = get_signature(print)
        assert sig2 is sig

    def test_preloaded_builtins(self):
        """测试预加载的内置函数"""
        for name in ['len', 'map', 'filter', 'zip', 'sorted', 'open', 'type']:
            func = getattr(builtins, name)
            s = get_signature(func)
            assert isinstance(s, Signature)

    def test_add_custom_sig(self):
        """测试 add_custom_sig"""
        def myfunc(x, y=0):
            return x + y

        custom_sig = Signature([
            Parameter('a', P),
            Parameter('b', P, default=0),
        ])
        add_custom_sig(myfunc, custom_sig)
        sig3 = get_signature(myfunc)
        assert sig3 is custom_sig
        assert 'a' in [p.name for p in sig3.parameters.values()]

    def test_add_custom_sig_force(self):
        """测试 add_custom_sig force 参数"""
        def myfunc(x, y=0):
            return x + y

        custom_sig = Signature([Parameter('a', P), Parameter('b', P, default=0)])
        add_custom_sig(myfunc, custom_sig)
        
        new_sig = Signature([Parameter('x', P)])
        add_custom_sig(myfunc, new_sig, force=False)
        sig4 = get_signature(myfunc)
        params4 = list(sig4.parameters.keys())
        assert params4 == ['a', 'b']

        add_custom_sig(myfunc, new_sig, force=True)
        sig5 = get_signature(myfunc)
        params5 = list(sig5.parameters.keys())
        assert params5 == ['x']

    def test_lru_eviction(self):
        """测试 LRU 淘汰机制"""
        clear_cache()
        funcs = []
        for i in range(5000):
            def f(i=i):
                return i
            funcs.append(f)
            get_signature(f)
        info = cache_info()
        assert info['size'] <= 4096

    def test_cached_getsignature_decorator(self):
        """测试 cached_getsignature 装饰器"""
        @cached_getsignature
        def add(a: int, b: int = 0) -> int:
            return a + b

        assert hasattr(add, '__cached_sig__')
        assert isinstance(add.__cached_sig__, Signature)

    def test_clear_cache(self):
        """测试 clear_cache"""
        get_signature(len)
        clear_cache()
        info = cache_info()
        assert info['size'] == 0
        assert info['hits'] == 0

    def test_cache_info(self):
        """测试 cache_info"""
        get_signature(len)
        get_signature(len)
        info = cache_info()
        assert info['size'] >= 1
        assert info['hits'] >= 1
        assert info['maxsize'] == 4096
        assert 0 <= info['hit_ratio'] <= 1.0

    def test_parameter_validation(self):
        """测试参数验证"""
        def myfunc(x, y=0):
            return x + y

        try:
            add_custom_sig(123, Signature([]))
            assert False, "Expected TypeError"
        except TypeError:
            pass

        try:
            add_custom_sig(myfunc, "not a signature")
            assert False, "Expected ValueError"
        except ValueError:
            pass


if __name__ == '__main__':
    import unittest
    unittest.main()