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
        # BUG-353: 类级映射只受显式类注册影响，不再被方言实例污染。
        # 方言专属命名（REAL/TEXT）见 test_dialect_instance_isolation。
        assert SqlTypeMapper.get_sql_type(float) == 'DOUBLE'

    def test_get_sql_type_str(self):
        assert SqlTypeMapper.get_sql_type(str) == 'VARCHAR'

    def test_dialect_instance_isolation(self):
        # BUG-353: SqliteDialect 的类型映射只作用于它自己的 mapper 实例
        from vools.sql.sqlite.dialect import SqliteDialect

        mapper = SqliteDialect().get_type_mapper()
        assert mapper.get_sql_type(str) == 'TEXT'
        assert mapper.get_sql_type(float) == 'REAL'
        # 类级默认不受影响
        assert SqlTypeMapper.get_sql_type(str) == 'VARCHAR'
        assert SqlTypeMapper.get_sql_type(float) == 'DOUBLE'

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
        # BUG-353: 类级默认映射（float->DOUBLE, str->VARCHAR），不再受方言实例影响
        types = SqlTypeMapper.infer_arg_types([1, 2.5, 'hello', b'raw'])
        assert types == ['INTEGER', 'DOUBLE', 'VARCHAR', 'BLOB']

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
