# -*- coding: utf-8 -*-
"""回归测试：VProcessPool 关闭后不得静默复活（BUG-403）。

`VProcessPool.close()` 把 `_pool` 置 None，而 `_ensure_pool()` 只要发现
`_pool is None` 就新建进程池：

    pool.close()
    pool.add_task(f, 1)     # 修复前：**静默重建**进程池，「已关闭」的池悄悄复活
    pool.gather()           # -> [结果]（调用方以为池已关闭）

与 `VThreadPoolExecutor.shutdown()` 后 `submit()` 抛
``RuntimeError: cannot submit to shutdown executor`` 的语义不一致，
也让资源/生命周期意图失效。

修复：close()/terminate() 置 `_closed`；`_ensure_pool()`（被 start/add_task/
map 等调用）在已关闭时抛 RuntimeError 并提示新建实例。正常使用与幂等 close
不变。

注意：进程池使用 Windows spawn，目标函数必须是模块级可 pickle 函数，故本文件
在模块顶层定义 `_square`；`main()` 由 pytest 直接调用，无需 `if __name__`
守卫（子进程只 import 本模块，不会重跑测试逻辑）。
"""

import pytest

from vools.vconcurrent.multiprocessing_mod import VProcessPool


def _square(x):
    return x * x


@pytest.fixture()
def pool():
    p = VProcessPool(processes=1)
    p.start()
    yield p
    try:
        p.close()
    except Exception:
        pass


class TestNormalUsage:
    def test_add_task_and_gather(self, pool):
        result = pool.add_task(_square, 3)
        assert result.get(timeout=30) == 9
        assert pool.gather(timeout=30) == [9]

    def test_map(self, pool):
        assert pool.map(_square, [2, 3]) == [4, 9]

    def test_close_idempotent(self):
        p = VProcessPool(processes=1)
        p.close()
        p.close()          # 重复 close 不应报错
        assert True


class TestClosedStateRejected:
    def test_add_task_after_close(self):
        p = VProcessPool(processes=1)
        p.start()
        p.add_task(_square, 1)
        p.close()
        # 修复前：静默重建进程池
        with pytest.raises(RuntimeError) as ei:
            p.add_task(_square, 2)
        assert '关闭' in str(ei.value)

    def test_start_after_close(self):
        p = VProcessPool(processes=1)
        p.close()
        with pytest.raises(RuntimeError):
            p.start()

    def test_map_after_close(self):
        p = VProcessPool(processes=1)
        p.start()
        p.close()
        with pytest.raises(RuntimeError):
            p.map(_square, [1])

    def test_after_terminate(self):
        p = VProcessPool(processes=1)
        p.start()
        p.terminate()
        with pytest.raises(RuntimeError):
            p.add_task(_square, 5)
        with pytest.raises(RuntimeError):
            p.start()

    def test_new_instance_still_usable(self):
        p = VProcessPool(processes=1)
        p.close()
        p2 = VProcessPool(processes=1)
        try:
            assert p2.map(_square, [6]) == [36]
        finally:
            p2.close()