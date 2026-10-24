# -*- coding: utf-8 -*-
"""回归测试：TaskDecorator 的 db_path / func 入口校验（BUG-426）。

原实现零校验：

    TaskDecorator(db_path=123)   # 接受；直到提交任务时才抛 sqlite 天书错误
    TaskDecorator(db_path=None)  # 同上
    task(123) / TaskDecorator()(123)
                                 # 接受；得到一个"看起来是任务函数"的 wrapper，
                                 # 调用时才抛 TypeError

修复后入口即抛带上下文的 TypeError/ValueError；``db_path`` 接受 str 或
``os.PathLike``（含 ``pathlib.Path``）；合法装饰与提交链路不变。
"""

import pytest

from vools.task.decorators.task_decorator import TaskDecorator, task


class TestDbPathValidation:
    @pytest.mark.parametrize("bad", [123, None, [], (), object()])
    def test_non_path_rejected(self, bad):
        with pytest.raises(TypeError) as ei:
            TaskDecorator(db_path=bad)
        assert "TaskDecorator" in str(ei.value)

    @pytest.mark.parametrize("bad", ["", "   ", "\t"])
    def test_blank_rejected(self, bad):
        with pytest.raises(ValueError) as ei:
            TaskDecorator(db_path=bad)
        assert "db_path" in str(ei.value)

    def test_task_decorator_helper_validates_too(self):
        with pytest.raises(TypeError):
            task(db_path=123)
        with pytest.raises(ValueError):
            task(db_path="")

    def test_str_and_pathlike_accepted(self, tmp_path):
        assert TaskDecorator(db_path=str(tmp_path / "t.db")).db_path.endswith("t.db")
        from pathlib import Path

        assert TaskDecorator(db_path=Path(tmp_path / "t.db")).db_path.endswith("t.db")


class TestFuncValidation:
    @pytest.mark.parametrize("bad", [123, "not-callable", []])
    def test_non_callable_rejected(self, bad):
        with pytest.raises(TypeError) as ei:
            TaskDecorator()(bad)
        assert "TaskDecorator" in str(ei.value)
        with pytest.raises(TypeError):
            task(bad)

    def test_none_is_the_documented_decorator_factory(self):
        # ``@task`` 无括号用法：task(None) 返回装饰器（既有契约，不是缺陷）
        assert callable(task(None))
        with pytest.raises(TypeError):
            task(None)(123)

    def test_valid_function_still_works(self, tmp_path):
        db = str(tmp_path / "t.db")

        @task(db_path=db)
        def add(a, b):
            return a + b

        assert add.direct(1, 2) == 3
        assert add(1, 2) > 0     # 提交任务返回任务 id
