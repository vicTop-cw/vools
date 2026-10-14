"""tests/concurrent/test_multiprocessing_mod.py — 多进程工具测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.concurrent.multiprocessing_mod import (
    VProcess, VProcessPool, SharedValue, SharedDict, SharedList,
    cpu_count, process_pool, run_in_process,
)


def _factorial(x):
    """可序列化的阶乘函数"""
    import math
    return math.factorial(x)


# process_pool / run_in_process 需要被 pickle 的目标函数必须位于模块顶层，
# 不能是测试方法内的局部函数：Windows spawn 的子进程无法 import `<locals>`。
@process_pool(processes=2)
def _compute_pool(x):
    return _factorial(x)


@run_in_process()
def _heavy_task(x):
    return _factorial(x)


# process_pool / run_in_process 的 target 必须是模块级（可被 import）函数：
# 定义在测试方法内的 `<locals>` 函数在 Windows spawn 下子进程无法重新导入，
# 这也是旧 skipif(win32) 一直在掩盖的问题。
@process_pool(processes=2)
def _compute_pool(x):
    return _factorial(x)


@run_in_process()
def _heavy_task(x):
    return _factorial(x)


class TestVProcess:
    """VProcess 增强进程测试"""

    def test_creation(self):
        p = VProcess(target=_factorial, args=(5,))
        assert p is not None

    def test_start_and_result(self):
        p = VProcess(target=_factorial, args=(5,))
        p.start()
        result = p.get_result(timeout=5)
        assert result == 120

    def test_exception(self):
        import math
        p = VProcess(target=math.factorial, args=(-1,))
        p.start()
        with pytest.raises(ValueError):
            p.get_result(timeout=5)

    def test_result_queue(self):
        p = VProcess(target=_factorial, args=(5,))
        p.start()
        p.get_result(timeout=5)
        assert p.result_queue is not None

    def test_context_manager(self):
        with VProcess(target=_factorial, args=(5,)) as p:
            result = p.get_result(timeout=5)
        assert result == 120


class TestVProcessPool:
    """VProcessPool 进程池测试"""

    def test_creation(self):
        pool = VProcessPool(processes=2)
        assert pool is not None

    def test_add_task(self):
        pool = VProcessPool(processes=2)
        pool.start()
        pool.add_task(_factorial, 5)
        pool.close()

    def test_map(self):
        pool = VProcessPool(processes=2)
        pool.start()
        results = list(pool.map(abs, [-1, -2, -3]))
        assert results == [1, 2, 3]
        pool.close()

    def test_context_manager(self):
        with VProcessPool(processes=2) as pool:
            pool.start()
        assert True  # 无异常即通过


class TestSharedValue:
    """SharedValue 共享值测试"""

    def test_get_set(self):
        sv = SharedValue('i', 0)
        sv.set(42)
        assert sv.get() == 42

    def test_raw(self):
        sv = SharedValue('i', 0)
        assert sv.raw is not None

    def test_context_manager(self):
        sv = SharedValue('i', 0)
        with sv:
            sv.set(1)
        assert True  # 无异常即通过


class TestSharedDict:
    """SharedDict 共享字典测试"""

    def test_getitem_setitem(self):
        sd = SharedDict()
        sd['key'] = 'value'
        assert sd['key'] == 'value'

    def test_contains(self):
        sd = SharedDict()
        sd['key'] = 'value'
        assert 'key' in sd
        assert 'missing' not in sd

    def test_len(self):
        sd = SharedDict()
        sd['a'] = 1
        sd['b'] = 2
        assert len(sd) == 2

    def test_delitem(self):
        sd = SharedDict()
        sd['key'] = 'value'
        del sd['key']
        assert 'key' not in sd

    def test_get(self):
        sd = SharedDict()
        sd['key'] = 'value'
        assert sd.get('key') == 'value'
        assert sd.get('missing') is None

    def test_keys(self):
        sd = SharedDict()
        sd['a'] = 1
        sd['b'] = 2
        keys = list(sd.keys())
        assert 'a' in keys
        assert 'b' in keys

    def test_values(self):
        sd = SharedDict()
        sd['a'] = 1
        sd['b'] = 2
        vals = list(sd.values())
        assert 1 in vals
        assert 2 in vals

    def test_items(self):
        sd = SharedDict()
        sd['a'] = 1
        items = list(sd.items())
        assert ('a', 1) in items

    def test_update(self):
        sd = SharedDict()
        sd.update({'a': 1, 'b': 2})
        assert sd['a'] == 1
        assert sd['b'] == 2

    def test_to_dict(self):
        sd = SharedDict()
        sd['key'] = 'value'
        d = sd.to_dict()
        assert d['key'] == 'value'

    def test_close(self):
        sd = SharedDict()
        sd.close()
        assert True  # 无异常即通过


class TestSharedList:
    """SharedList 共享列表测试"""

    def test_getitem_setitem(self):
        sl = SharedList()
        sl.append('item')
        assert sl[0] == 'item'

    def test_append(self):
        sl = SharedList()
        sl.append(1)
        sl.append(2)
        assert len(sl) == 2

    def test_extend(self):
        sl = SharedList()
        sl.extend([1, 2, 3])
        assert len(sl) == 3

    def test_pop(self):
        sl = SharedList()
        sl.append(1)
        sl.append(2)
        popped = sl.pop()
        assert popped == 2
        assert len(sl) == 1

    def test_len(self):
        sl = SharedList()
        sl.append(1)
        sl.append(2)
        assert len(sl) == 2

    def test_contains(self):
        sl = SharedList()
        sl.append('item')
        assert 'item' in sl

    def test_to_list(self):
        sl = SharedList()
        sl.extend([1, 2, 3])
        lst = sl.to_list()
        assert lst == [1, 2, 3]

    def test_close(self):
        sl = SharedList()
        sl.close()
        assert True  # 无异常即通过


class TestCpuCount:
    """cpu_count 测试"""

    def test_returns_int(self):
        count = cpu_count()
        assert isinstance(count, int)
        assert count >= 1


class TestProcessPoolDecorator:
    """process_pool 装饰器测试

    Windows 兼容说明：vools.concurrent.multiprocessing_mod 里针对 Windows
    spawn 模式做了专门处理（_RegisteredCaller + __mp_main__ 归一化），因此
    本测试**可以在 win32 上跑**。旧的 ``skipif(win32)`` 是过时残留，会掩盖
    真实回归；这里去掉 skip，让它真正验证 Windows spawn 下的注册表机制。
    """

    def test_decorator(self):
        # target 必须是模块级函数 _compute_pool（见文件顶部注释）
        assert _compute_pool(5) == 120


class TestRunInProcessDecorator:
    """run_in_process 装饰器测试（同上，去掉过时的 win32 skip）"""

    def test_decorator(self):
        assert _heavy_task(5) == 120
