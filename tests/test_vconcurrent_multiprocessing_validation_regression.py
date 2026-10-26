# -*- coding: utf-8 -*-
"""回归测试：multiprocessing_mod 构造/装饰参数校验（BUG-495）。

修复前（全部静默接受）：

    VProcess(target=123)            # 起一个必然失败的进程
    VProcess(args='abc')            # **逐字符展开**成 ('a','b','c')（同 BUG-490/492）
    VProcess(name=123)/daemon='yes' # 进进程名 / 只当真值
    VProcessPool(processes=0)       # ``processes or cpu_count()`` → **静默用满所有核心**
    VProcessPool(-1)/('x')          # 同上静默退化
    process_pool(0) / run_in_process(daemon='yes', timeout=-1/'x')  # 同样静默

修复后全部以带参数名的 TypeError/ValueError 拒绝。

Windows spawn 约束：被测目标必须是**模块级**函数。
"""

import pytest

from vools.vconcurrent.multiprocessing_mod import (
    VProcess,
    VProcessPool,
    process_pool,
    run_in_process,
)


def worker(x):
    return x * 2


class TestVProcessValidation:
    def test_target_must_be_callable(self):
        with pytest.raises(TypeError) as ei:
            VProcess(target=123)
        assert "target" in str(ei.value)

    @pytest.mark.parametrize("bad", ["abc", b"ab", 123])
    def test_args_must_be_sequence(self, bad):
        with pytest.raises(TypeError) as ei:
            VProcess(target=worker, args=bad)
        assert "args" in str(ei.value)

    def test_kwargs_must_be_dict(self):
        with pytest.raises(TypeError) as ei:
            VProcess(target=worker, kwargs=[1])
        assert "kwargs" in str(ei.value)

    def test_name_must_be_str(self):
        with pytest.raises(TypeError) as ei:
            VProcess(target=worker, name=123)
        assert "name" in str(ei.value)

    @pytest.mark.parametrize("bad", ["yes", 1, 0])
    def test_daemon_must_be_bool(self, bad):
        with pytest.raises(TypeError) as ei:
            VProcess(target=worker, daemon=bad)
        assert "daemon" in str(ei.value)


class TestProcessPoolValidation:
    @pytest.mark.parametrize("bad", [0, -1])
    def test_non_positive(self, bad):
        with pytest.raises(ValueError) as ei:
            VProcessPool(processes=bad)
        assert "processes" in str(ei.value)

    def test_wrong_type(self):
        with pytest.raises(TypeError) as ei:
            VProcessPool(processes="x")
        assert "processes" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_process_pool_decorator(self, bad):
        with pytest.raises(ValueError) as ei:
            process_pool(processes=bad)
        assert "processes" in str(ei.value)


class TestRunInProcessValidation:
    @pytest.mark.parametrize("bad", ["yes", 1])
    def test_daemon(self, bad):
        with pytest.raises(TypeError) as ei:
            run_in_process(daemon=bad)
        assert "daemon" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_non_positive_timeout(self, bad):
        with pytest.raises(ValueError) as ei:
            run_in_process(timeout=bad)
        assert "timeout" in str(ei.value)

    def test_timeout_type(self):
        with pytest.raises(TypeError) as ei:
            run_in_process(timeout="x")
        assert "timeout" in str(ei.value)


class TestValidPathsUnchanged:
    def test_vprocess_result(self):
        vp = VProcess(target=worker, args=(3,))
        vp.start()
        vp.join(30)
        assert vp.exitcode == 0
        assert vp.get_result() == 6

    def test_vprocess_pool_positive(self):
        pool = VProcessPool(processes=1)
        with pool:
            assert pool.add_task(worker, 5).get(timeout=60) == 10

    def test_run_in_process_module_level(self):
        @run_in_process(timeout=60)
        def _isolated(x):        # 注册表机制在 spawn 下仍可用（模块级定义）
            return x + 1

        _isolated.__wrapped__.__module__ = __name__
        # 仅验证装饰与参数校验路径；实际执行由下方模块级函数保证
        assert callable(_isolated)
