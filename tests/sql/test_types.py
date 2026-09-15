"""tests/sql/test_types.py — SQL 类型映射器测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.sql.core.types import SqlTypeMapper


class TestSqlTypeMapper:
    """SqlTypeMapper 类型映射测试"""

    def test_register_and_get_sql_type(self):
        SqlTypeMapper.register_type(bool, 'BOOLEAN')
        assert SqlTypeMapper.get_sql_type(bool) == 'BOOLEAN'

    def test_get_sql_type_int(self):
        assert SqlTypeMapper.get_sql_type(int) == 'INTEGER'

    def test_get_sql_type_float(self):
        assert SqlTypeMapper.get_sql_type(float) == 'REAL'

    def test_get_sql_type_str(self):
        assert SqlTypeMapper.get_sql_type(str) == 'TEXT'

    def test_get_sql_type_bytes(self):
        assert SqlTypeMapper.get_sql_type(bytes) == 'BLOB'

    def test_get_sql_type_unknown(self):
        class CustomClass:
            pass
        assert SqlTypeMapper.get_sql_type(CustomClass) is None

    def test_get_py_type(self):
        # 注意：SqliteDialect 注册了以下覆盖映射：
        #   bool -> INTEGER（覆盖 int -> INTEGER）
        #   datetime.date -> TEXT（覆盖 str -> TEXT）
        #   datetime.datetime -> TEXT（覆盖 datetime.date -> TEXT）
        # 所以 get_py_type 返回的是最后注册的映射
        assert SqlTypeMapper.get_py_type('REAL') == float
        assert SqlTypeMapper.get_py_type('BLOB') == bytes

    def test_get_py_type_case_insensitive(self):
        # get_py_type 内部使用 .upper()
        assert SqlTypeMapper.get_py_type('real') == float
        assert SqlTypeMapper.get_py_type('blob') == bytes

    def test_get_py_type_unknown(self):
        assert SqlTypeMapper.get_py_type('UNKNOWN_TYPE') is None

    def test_infer_arg_types_mixed(self):
        types = SqlTypeMapper.infer_arg_types([1, 2.5, 'hello', b'raw'])
        assert types == ['INTEGER', 'REAL', 'TEXT', 'BLOB']

    def test_infer_arg_types_empty(self):
        assert SqlTypeMapper.infer_arg_types([]) == []

    def test_infer_arg_types_unknown_defaults_varchar(self):
        class CustomType:
            pass
        types = SqlTypeMapper.infer_arg_types([CustomType()])
        assert types == ['VARCHAR']

    def test_infer_ret_type_int(self):
        assert SqlTypeMapper.infer_ret_type(int) == 'INTEGER'

    def test_infer_ret_type_none(self):
        assert SqlTypeMapper.infer_ret_type(None) is None
        assert SqlTypeMapper.infer_ret_type(type(None)) is None

    def test_infer_ret_type_unknown(self):
        class CustomType:
            pass
        assert SqlTypeMapper.infer_ret_type(CustomType) == 'INTEGER'

    def test_convert_args(self):
        args = [1, 'hello', 3.14]
        types = ['INTEGER', 'TEXT', 'REAL']
        result = SqlTypeMapper.convert_args(args, types)
        assert result == args

    def test_convert_result(self):
        assert SqlTypeMapper.convert_result(42, int) == 42
        assert SqlTypeMapper.convert_result('text', str) == 'text'

    def test_roundtrip_type_mapping(self):
        SqlTypeMapper.register_type(complex, 'TEXT')
        assert SqlTypeMapper.get_sql_type(complex) == 'TEXT'
        # 注意：register_type 会覆盖 _sql_to_py 中 'TEXT' 的映射
        assert SqlTypeMapper.get_py_type('TEXT') == complex


class TestDialectConfig:
    """DialectConfig 配置测试"""

    def test_config_creation(self):
        from vools.sql.core.config import DialectConfig
        config = DialectConfig(
            name='test_db',
            driver='test_driver',
            default_port=5432,
            default_host='localhost',
            default_user='user',
            default_database='testdb',
            paramstyle='pyformat',
            identifier_quote='"',
            string_quote="'",
        )
        assert config.name == 'test_db'
        assert config.default_port == 5432
