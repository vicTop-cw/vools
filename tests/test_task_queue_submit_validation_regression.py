# -*- coding: utf-8 -*-
"""回归测试：TaskQueue.submit 的任务选项类型校验（BUG-431）。

修复前（BUG-385 的同名冲突检测之外没有任何选项校验）：

    submit('not-callable')     # ValueError: Cannot serialize function: ...
    submit(fn, 1, task_options='x')  # AttributeError: 'str' object has no attribute 'get'
    submit(fn, 1, priority='x')      # **静默接受**（直到 acquire 比较优先级）
    submit(fn, 1, max_retries=-1)    # **静默接受**（重试语义反向）
    submit(fn, 1, depends_on='abc')  # 被逐字符展开 -> DagValidationError:
                                     # Dependency task b not found（完全看不出原因）
    submit(fn, 1, depends_on=999)    # TypeError: 'int' object is not iterable

修复后入口即抛带字段名的 TypeError/ValueError；合法提交与 BUG-385 冲突检测、
既有 DAG 校验（未知 int 依赖 -> DagValidationError）保持不变。
"""

import pytest

from vools.task.core.queue import TaskQueue
from vools.task.core.queue import DagValidationError  # noqa: F401  (契约引用)


def _fn(a, b=1):
    return a + b


@pytest.fixture()
def queue(tmp_path):
    q = TaskQueue(db_path=str(tmp_path / "q.db"))
    yield q
    try:
        q.storage.close()
    except Exception:
        pass


class TestFuncValidation:
    @pytest.mark.parametrize("bad", ["not-callable", 123, None, []])
    def test_non_callable(self, queue, bad):
        with pytest.raises(TypeError) as ei:
            queue.submit(bad)
        assert "func" in str(ei.value)


class TestTaskOptionsValidation:
    @pytest.mark.parametrize("bad", ["x", 123, [], object()])
    def test_non_dict(self, queue, bad):
        with pytest.raises(TypeError) as ei:
            queue.submit(_fn, 1, task_options=bad)
        assert "task_options" in str(ei.value)

    def test_none_allowed(self, queue):
        assert queue.submit(_fn, 1, task_options=None) > 0


class TestPriorityValidation:
    @pytest.mark.parametrize("bad", ["x", 1.5, True, None])
    def test_non_int(self, queue, bad):
        with pytest.raises(TypeError) as ei:
            queue.submit(_fn, 1, priority=bad)
        assert "priority" in str(ei.value)


class TestMaxRetriesValidation:
    @pytest.mark.parametrize("bad", ["x", 1.5, True, None])
    def test_non_int(self, queue, bad):
        with pytest.raises(TypeError) as ei:
            queue.submit(_fn, 1, max_retries=bad)
        assert "max_retries" in str(ei.value)

    @pytest.mark.parametrize("bad", [-1, -10])
    def test_negative(self, queue, bad):
        with pytest.raises(ValueError):
            queue.submit(_fn, 1, max_retries=bad)


class TestDependsOnValidation:
    def test_string_rejected(self, queue):
        # 原实现把 'abc' 逐字符展开成 3 个"任务ID"
        with pytest.raises(TypeError) as ei:
            queue.submit(_fn, 1, depends_on="abc")
        assert "depends_on" in str(ei.value)

    def test_int_rejected(self, queue):
        with pytest.raises(TypeError):
            queue.submit(_fn, 1, depends_on=999)

    def test_non_int_elements_rejected(self, queue):
        with pytest.raises(TypeError) as ei:
            queue.submit(_fn, 1, depends_on=["x"])
        assert "depends_on" in str(ei.value)

    def test_via_task_options(self, queue):
        with pytest.raises(TypeError):
            queue.submit(_fn, 1, task_options={"depends_on": "ab"})
        with pytest.raises(TypeError):
            queue.submit(_fn, 1, task_options={"depends_on": 5})

    def test_unknown_int_dependency_still_dag_error(self, queue):
        with pytest.raises(Exception) as ei:
            queue.submit(_fn, 1, depends_on=[999999])
        assert "Dependency" in str(ei.value)


class TestValidSubmitAndCollisionContract:
    def test_valid_submit(self, queue):
        tid = queue.submit(_fn, 1, priority=5, max_retries=2, depends_on=[])
        assert tid > 0

    def test_bug385_collision_detection_unchanged(self, queue):
        with pytest.raises(ValueError) as ei:
            queue.submit(lambda priority=0: priority, 1, priority=2)
        assert "冲突" in str(ei.value)

    def test_no_collision_with_task_options(self, queue):
        # 显式通道：kwargs 全部转发给函数
        tid = queue.submit(lambda priority=0: priority, 1,
                           task_options={"priority": 7})
        assert tid > 0
