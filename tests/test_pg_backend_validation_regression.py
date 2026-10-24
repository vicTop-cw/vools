# -*- coding: utf-8 -*-
"""回归测试：PgTaskBackend 构造参数校验（BUG-428）。

原实现零校验：``dsn=123``、``table=123``、``max_retries=-1``、
``retry_delay_min='x'``、``autocommit='x'`` 全部被接受，错误直到真正连库/
发 SQL 才暴露（天书）；``max_retries`` 为负还会让 ``fail()`` 的重试判断出现
反向语义。修复后构造时即抛带字段名的 TypeError/ValueError；合法构造不变
（构造本身不连接数据库，测试无需真实 PG）。
"""

import pytest

from vools.task.backends.pg import PgTaskBackend

DSN = "postgresql://user:pass@host:5432/db"


class TestDsnValidation:
    @pytest.mark.parametrize("bad", [123, None, "", "   ", []])
    def test_rejected(self, bad):
        with pytest.raises(ValueError) as ei:
            PgTaskBackend(dsn=bad)
        assert "dsn" in str(ei.value)

    def test_valid(self):
        assert PgTaskBackend(dsn=DSN).dsn == DSN


class TestTableValidation:
    @pytest.mark.parametrize("bad", [123, None, "", "   "])
    def test_rejected(self, bad):
        with pytest.raises(ValueError) as ei:
            PgTaskBackend(dsn=DSN, table=bad)
        assert "table" in str(ei.value)

    def test_valid(self):
        assert PgTaskBackend(dsn=DSN, table="t1").table == "t1"


class TestMaxRetriesValidation:
    @pytest.mark.parametrize("bad", ["x", 1.5, True, None, [1]])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError) as ei:
            PgTaskBackend(dsn=DSN, max_retries=bad)
        assert "max_retries" in str(ei.value)

    @pytest.mark.parametrize("bad", [-1, -10])
    def test_negative(self, bad):
        with pytest.raises(ValueError):
            PgTaskBackend(dsn=DSN, max_retries=bad)

    def test_valid(self):
        assert PgTaskBackend(dsn=DSN, max_retries=0).max_retries == 0


class TestRetryDelayValidation:
    @pytest.mark.parametrize("bad", ["x", 1.5, True, None])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError) as ei:
            PgTaskBackend(dsn=DSN, retry_delay_min=bad)
        assert "retry_delay_min" in str(ei.value)

    def test_negative(self):
        with pytest.raises(ValueError):
            PgTaskBackend(dsn=DSN, retry_delay_min=-1)

    def test_valid(self):
        assert PgTaskBackend(dsn=DSN, retry_delay_min=0).retry_delay_min == 0


class TestAutocommitValidation:
    @pytest.mark.parametrize("bad", ["x", 1, 0, None])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError) as ei:
            PgTaskBackend(dsn=DSN, autocommit=bad)
        assert "autocommit" in str(ei.value)

    def test_valid(self):
        assert PgTaskBackend(dsn=DSN, autocommit=False).autocommit is False


class TestCombinedValid:
    def test_all_options(self):
        b = PgTaskBackend(dsn=DSN, table="t", max_retries=2,
                          retry_delay_min=3, autocommit=False)
        assert (b.dsn, b.table, b.max_retries, b.retry_delay_min,
                b.autocommit) == (DSN, "t", 2, 3, False)
