# -*- coding: utf-8 -*-
"""回归测试：driver_name 仅在连接成功后置位（BUG-237）。

原 `connect` 在真实连接**之前**就写 `_driver_name`——驱动已安装但连接失败
（认证失败/服务未启动/网络不可达）时残留驱动名，违背 `driver_name` 属性
docstring 的「未连接时为 None」契约，令 `if conn.driver_name:` 类状态判断
误以为已连接。

修复：两处 `_driver_name = ...` 移到 connect() 成功之后、与 `_connected`
同步置位；失败路径保持 None（异常照常传播）。
"""

import sys
import types

import pytest

from vools.sql.postgres.connection import PostgresConnection


class _FakeDriver:
    """模拟已安装的 psycopg2 驱动。"""

    def __init__(self, connect_impl):
        self.connect = connect_impl
        self.OperationalError = RuntimeError


@pytest.fixture
def fake_psycopg2():
    """注入假 psycopg2 模块，返回可替换 connect 的驱动对象。"""
    module = types.ModuleType('psycopg2')
    holder = {}

    class _Op(RuntimeError):
        pass

    module.OperationalError = _Op

    def connect(**kwargs):
        impl = holder.get('connect')
        if impl is None:
            raise _Op('not configured')
        return impl(**kwargs)

    module.connect = connect
    sys.modules['psycopg2'] = module
    holder['Op'] = _Op
    yield holder
    sys.modules.pop('psycopg2', None)


class TestDriverNameOnFailure:
    """BUG-237 核心：连接失败后 driver_name 必须保持 None。"""

    def test_auth_failure_keeps_none(self, fake_psycopg2):
        Op = fake_psycopg2['Op']

        def fail(**kwargs):
            raise Op('password authentication failed')

        fake_psycopg2['connect'] = fail
        c = PostgresConnection(password='wrong')
        with pytest.raises(Op):
            c.connect()
        assert c.driver_name is None
        assert c._connected is False

    def test_state_predicate_not_misled(self, fake_psycopg2):
        Op = fake_psycopg2['Op']
        fake_psycopg2['connect'] = lambda **kw: (_ for _ in ()).throw(Op('down'))
        c = PostgresConnection()
        with pytest.raises(Op):
            c.connect()
        # 调用方常见的状态判断不被残留值误导
        assert bool(c.driver_name) is False


class TestDriverNameOnSuccess:
    """连接成功后 driver_name 正常置位。"""

    def test_success_sets_driver(self, fake_psycopg2):
        class _Conn:
            def cursor(self):
                return None

            def close(self):
                pass

        fake_psycopg2['connect'] = lambda **kw: _Conn()
        c = PostgresConnection()
        c.connect()
        assert c.driver_name == 'psycopg2'
        assert c._connected is True


class TestNoDriverAvailable:
    """无驱动时 ImportError 且 driver_name 保持 None。"""

    def test_import_error(self, monkeypatch):
        monkeypatch.delitem(sys.modules, 'psycopg2', raising=False)
        monkeypatch.delitem(sys.modules, 'psycopg', raising=False)
        c = PostgresConnection()
        with pytest.raises(ImportError, match="No PostgreSQL driver"):
            c.connect()
        assert c.driver_name is None