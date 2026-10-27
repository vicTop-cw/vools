# -*- coding: utf-8 -*-
"""回归测试：batch_execute 的参数校验（BUG-352）。

修复前（全部静默接受或晚期裸错）：

    batch_execute(task_args=[(1,)], priority="x")      # 接受
    batch_execute(task_args=[(1,)], max_retries=-1)    # 接受
    batch_execute(task_args=[(1,)], worker_nums=0)     # 接受（0 个 worker，任务永不执行）
    batch_execute(task_args=[(1,)], is_worker="x")     # 接受且 **静默改变语义**
                                                       #   （返回任务 ID 而非执行结果）
    batch_execute(task_args=[(1,)], queue=123)         # 接受
    batch_execute(task_args=[1])                       # 晚期裸错
                                                       #   TypeError: can only concatenate tuple
    batch_execute(task_args="ab")                      # 同上

修复：priority/max_retries/worker_nums 必须整数（bool 拒绝）、max_retries>=0、
worker_nums>=1、is_worker 必须 bool、queue 必须 TaskQueue 或 None、
task_args/task_kwargs 必须是序列且元素分别是 tuple/list 与 dict。
"""

import pytest

from vools.task.decorators.task_decorator import batch_execute


def _double(x=1):
    return x * 2


class TestFactoryParameterValidation:
    @pytest.mark.parametrize("bad", ["x", 1.5, True, None])
    def test_priority_type(self, bad):
        with pytest.raises(TypeError) as ei:
            batch_execute(task_args=[(1,)], priority=bad)
        assert "priority" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", 1.5, True])
    def test_max_retries_type(self, bad):
        with pytest.raises(TypeError) as ei:
            batch_execute(task_args=[(1,)], max_retries=bad)
        assert "max_retries" in str(ei.value)

    def test_max_retries_negative(self):
        with pytest.raises(ValueError):
            batch_execute(task_args=[(1,)], max_retries=-1)

    @pytest.mark.parametrize("bad", ["x", 1.5, True])
    def test_worker_nums_type(self, bad):
        with pytest.raises(TypeError) as ei:
            batch_execute(task_args=[(1,)], worker_nums=bad)
        assert "worker_nums" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_worker_nums_range(self, bad):
        with pytest.raises(ValueError):
            batch_execute(task_args=[(1,)], worker_nums=bad)

    @pytest.mark.parametrize("bad", ["x", 1, 0, None])
    def test_is_worker_must_be_bool(self, bad):
        with pytest.raises(TypeError) as ei:
            batch_execute(task_args=[(1,)], is_worker=bad)
        assert "is_worker" in str(ei.value)

    def test_queue_must_be_taskqueue(self):
        with pytest.raises(TypeError) as ei:
            batch_execute(task_args=[(1,)], queue=123)
        assert "queue" in str(ei.value)


class TestTaskArgsValidation:
    @pytest.mark.parametrize("bad", ["ab", 123, {"a": 1}])
    def test_task_args_must_be_sequence(self, bad):
        with pytest.raises(TypeError) as ei:
            batch_execute(task_args=bad)
        assert "task_args" in str(ei.value)

    @pytest.mark.parametrize("bad", [[1], ["ab"]])
    def test_task_args_element_must_be_sequence(self, bad):
        with pytest.raises(TypeError) as ei:
            batch_execute(task_args=bad)
        assert "task_args[0]" in str(ei.value)

    @pytest.mark.parametrize("bad", ["ab", 123])
    def test_task_kwargs_must_be_sequence(self, bad):
        with pytest.raises(TypeError) as ei:
            batch_execute(task_kwargs=bad)
        assert "task_kwargs" in str(ei.value)

    def test_task_kwargs_element_must_be_dict(self):
        with pytest.raises(TypeError) as ei:
            batch_execute(task_args=[(1,)], task_kwargs=[1])
        assert "task_kwargs[0]" in str(ei.value)


class TestBehaviourUnchanged:
    def test_direct_execution(self, tmp_path):
        fn = batch_execute(task_args=[(1,), (2,)], db_path=str(tmp_path / "t.db"))(_double)
        assert fn() == [2, 4]

    def test_call_time_args(self, tmp_path):
        fn = batch_execute(db_path=str(tmp_path / "t.db"))(_double)
        assert fn(task_args=[(3,)]) == [6]

    def test_kwargs_mode(self, tmp_path):
        fn = batch_execute(task_kwargs=[{"x": 5}], db_path=str(tmp_path / "t.db"))(_double)
        assert fn() == [10]

    def test_worker_mode_returns_task_ids(self, tmp_path):
        fn = batch_execute(
            task_args=[(1,), (2,)], is_worker=True, db_path=str(tmp_path / "t.db")
        )(_double)
        ids = fn()
        assert isinstance(ids, list) and ids and all(isinstance(i, int) for i in ids)

    def test_length_mismatch_still_raises(self):
        fn = batch_execute(task_args=[(1,), (2,)], task_kwargs=[{}])(_double)
        with pytest.raises(ValueError):
            fn()
