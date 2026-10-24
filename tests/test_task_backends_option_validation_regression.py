# -*- coding: utf-8 -*-
"""回归测试：memory / sqlite 后端构造参数校验（BUG-429）。

与 BUG-428（pg 后端）同族：三个后端原先对 ``max_retries`` /
``retry_delay_min`` 零校验——``max_retries='x'`` 让 ``fail()`` 里的
``retry_count >= max_retries`` 在运行期抛 TypeError；``max_retries=-1`` 被
静默接受，使首次失败即终态（与 ``max_retries=0`` 语义重复且含义不明）；
``retry_delay_min=1.5`` 被接受但调度里按整数使用。sqlite 后端还额外存在
``db_path=''`` 被接受（连到无名临时库）的问题。

修复后构造时即校验：``max_retries``/``retry_delay_min`` 为非负整数
（bool 除外）、sqlite 的 ``db_path`` 为非空 str/PathLike、``table`` 为非空 str。
"""

import pytest

from vools.task.backends.memory_backend import MemoryTaskBackend
from vools.task.backends.sqlite_backend import SqliteTaskBackend


class TestMemoryBackendOptions:
    @pytest.mark.parametrize("bad", ["x", 1.5, True, None, [1]])
    def test_max_retries_bad_type(self, bad):
        with pytest.raises(TypeError) as ei:
            MemoryTaskBackend(max_retries=bad)
        assert "max_retries" in str(ei.value)

    @pytest.mark.parametrize("bad", [-1, -10])
    def test_max_retries_negative(self, bad):
        with pytest.raises(ValueError):
            MemoryTaskBackend(max_retries=bad)

    @pytest.mark.parametrize("bad", ["x", 1.5, True, None])
    def test_retry_delay_bad_type(self, bad):
        with pytest.raises(TypeError) as ei:
            MemoryTaskBackend(retry_delay_min=bad)
        assert "retry_delay_min" in str(ei.value)

    def test_retry_delay_negative(self):
        with pytest.raises(ValueError):
            MemoryTaskBackend(retry_delay_min=-1)

    def test_valid(self):
        be = MemoryTaskBackend(max_retries=0, retry_delay_min=0)
        assert be.max_retries == 0
        assert be.retry_delay_min == 0


class TestSqliteBackendOptions:
    @pytest.mark.parametrize("bad", ["", "   ", "\t"])
    def test_blank_db_path(self, bad):
        with pytest.raises(ValueError) as ei:
            SqliteTaskBackend(db_path=bad)
        assert "db_path" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, None, []])
    def test_bad_db_path_type(self, bad):
        with pytest.raises(TypeError) as ei:
            SqliteTaskBackend(db_path=bad)
        assert "db_path" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, "", "  "])
    def test_bad_table(self, bad, tmp_path):
        with pytest.raises(ValueError) as ei:
            SqliteTaskBackend(db_path=str(tmp_path / "t.db"), table=bad)
        assert "table" in str(ei.value)

    def test_max_retries_negative(self, tmp_path):
        with pytest.raises(ValueError):
            SqliteTaskBackend(db_path=str(tmp_path / "t.db"), max_retries=-1)

    def test_retry_delay_bad_type(self, tmp_path):
        with pytest.raises(TypeError):
            SqliteTaskBackend(db_path=str(tmp_path / "t.db"),
                              retry_delay_min="x")

    def test_valid(self, tmp_path):
        be = SqliteTaskBackend(
            db_path=str(tmp_path / "t.db"), table="t", max_retries=2,
            retry_delay_min=3)
        assert be.table == "t"
        assert be.max_retries == 2
        be.close()
