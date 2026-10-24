# -*- coding: utf-8 -*-
"""回归测试：PostgreSQLConnection 显式参数校验（BUG-461）。

修复前构造器零校验，且因 ``or`` 短路产生**静默替换**：

    PostgreSQLConnection(host='')      # host 被静默换成 env/config/localhost
    PostgreSQLConnection(database='')  # database 被静默换成 postgres
    PostgreSQLConnection(port='x')     # 原样存下，直到 psycopg2.connect 才炸
    PostgreSQLConnection(port=-1)      # 同上
    PostgreSQLConnection(port=70000)   # 同上

修复后显式参数在构造时就校验；env/config 兜底路径保持不变。
"""

import vools.db.postgresql as pg

C = pg.PostgreSQLConnection


class TestHostUserDatabaseValidation:
    def test_empty_host(self):
        try:
            C(host="")
        except ValueError as e:
            assert "host" in str(e)
        else:
            raise AssertionError("空 host 应被拒")

    def test_whitespace_user(self):
        try:
            C(user="   ")
        except ValueError as e:
            assert "user" in str(e)
        else:
            raise AssertionError("空白 user 应被拒")

    def test_empty_database(self):
        try:
            C(database="")
        except ValueError as e:
            assert "database" in str(e)
        else:
            raise AssertionError("空 database 应被拒")


class TestPortValidation:
    def test_non_int(self):
        try:
            C(port="x")
        except TypeError as e:
            assert "port" in str(e)
        else:
            raise AssertionError("字符串 port 应被拒")

    def test_bool_rejected(self):
        try:
            C(port=True)
        except TypeError:
            pass
        else:
            raise AssertionError("bool port 应被拒")

    def test_out_of_range(self):
        for bad in (-1, 0, 65536, 70000):
            try:
                C(port=bad)
            except ValueError as e:
                assert "65535" in str(e)
            else:
                raise AssertionError(f"越界 port {bad} 应被拒")

    def test_valid_boundaries(self):
        assert C(port=1)._port == 1
        assert C(port=65535)._port == 65535


class TestPasswordValidation:
    def test_non_str(self):
        try:
            C(password=123)
        except TypeError as e:
            assert "password" in str(e)
        else:
            raise AssertionError("非字符串 password 应被拒")

    def test_empty_str_allowed(self):
        # 空密码在 trust 认证下合法：只校验类型
        assert C(password="", host="h")._password == ""


class TestValidAndFallback:
    def test_defaults(self):
        c = C()
        assert c._host and c._port and c._user and c._database

    def test_explicit_values_stored(self):
        c = C(host="db.example", port=1234, user="u", password="p", database="d")
        assert c._host == "db.example"
        assert c._port == 1234
        assert c._user == "u"
        assert c._password == "p"
        assert c._database == "d"

    def test_env_fallback(self, monkeypatch):
        monkeypatch.setenv("PG_HOST", "envhost")
        monkeypatch.setenv("PG_PORT", "5555")
        c = C()
        assert c._host == "envhost"
        assert c._port == 5555

    def test_env_bad_port_is_loud(self, monkeypatch):
        monkeypatch.setenv("PG_PORT", "not-a-port")
        try:
            C()
        except ValueError as e:
            assert "端口" in str(e) or "port" in str(e)
        else:
            raise AssertionError("env 里非法端口应报错")

    def test_no_connection_at_construction(self):
        """构造不应触碰网络/驱动（psycopg2 缺失环境下也必须可构造）。"""
        assert C()._connection is None
