"""
vools.sql.spark.dialect - Spark SQL 方言实现

提供 Spark SQL 方言的具体实现，包括类型映射、连接创建、
标识符引用等功能，基于 PySpark 的 SparkSession。
"""

from ..core.dialect import Dialect
from ..core.config import DialectConfig
from ..core.types import SqlTypeMapper
from ..core.builder import BaseSqlBuilder


class SparkSqlDialect(Dialect):
    """
    Spark SQL 方言实现类

    基于 PySpark 实现的 SQL 方言，
    提供 Spark SQL 特有的类型映射、标识符引用等功能。

    用法：
        dialect = SparkSqlDialect()
        conn = dialect.create_connection(app_name='my_app')
        conn.connect()
    """

    _config: DialectConfig = None
    _type_mapper: SqlTypeMapper = None

    def __init__(self):
        """
        初始化 Spark SQL 方言
        """
        self._init_config()
        self._init_type_mapper()

    def _init_config(self) -> None:
        """
        初始化方言配置
        """
        self._config = DialectConfig(
            name='spark',
            driver='pyspark',
            default_port=0,
            default_host='',
            default_user='',
            default_database='default',
            paramstyle='pyformat',
            identifier_quote='`',
            string_quote="'",
        )

    def _init_type_mapper(self) -> None:
        """
        初始化 Spark SQL 类型映射器

        基于基础 SqlTypeMapper，注册 Spark SQL 特有的类型。
        Spark 类型：StringType, IntegerType, LongType, DoubleType,
        FloatType, BooleanType, DateType, TimestampType, DecimalType,
        ArrayType, MapType, StructType, BinaryType
        """
        self._type_mapper = SqlTypeMapper

        self._type_mapper.register_type(str, 'STRING')
        self._type_mapper.register_type(int, 'INTEGER')
        self._type_mapper.register_type(float, 'DOUBLE')
        self._type_mapper.register_type(bool, 'BOOLEAN')
        self._type_mapper.register_type(bytes, 'BINARY')

        import datetime
        import decimal
        self._type_mapper.register_type(datetime.date, 'DATE')
        self._type_mapper.register_type(datetime.datetime, 'TIMESTAMP')
        self._type_mapper.register_type(decimal.Decimal, 'DECIMAL')

        self._type_mapper.register_type(list, 'ARRAY')
        self._type_mapper.register_type(dict, 'MAP')

    def get_config(self) -> DialectConfig:
        """
        获取 Spark SQL 方言配置

        返回：
            DialectConfig 实例
        """
        return self._config

    def get_type_mapper(self) -> SqlTypeMapper:
        """
        获取 Spark SQL 类型映射器

        返回：
            SqlTypeMapper 实例
        """
        return self._type_mapper

    def create_connection(self, **kwargs) -> 'SparkConnection':
        """
        创建 Spark 连接

        参数：
            **kwargs: 连接参数，如 app_name, master, catalog, database 等

        返回：
            SparkConnection 实例
        """
        from .connection import SparkConnection
        return SparkConnection(**kwargs)

    def quote_identifier(self, identifier: str) -> str:
        """
        用反引号引用标识符（表名、列名等）

        Spark SQL 使用反引号引用标识符，内部的反引号需要转义为两个反引号。

        参数：
            identifier: 标识符名称

        返回：
            引用后的标识符
        """
        escaped = identifier.replace('`', '``')
        return f"`{escaped}`"

    def quote_string(self, value: str) -> str:
        """
        用单引号引用字符串值

        Spark SQL 使用单引号引用字符串，内部的单引号需要转义为两个单引号。

        参数：
            value: 字符串值

        返回：
            引用后的字符串
        """
        escaped = value.replace("'", "''")
        return f"'{escaped}'"

    def get_builder_class(self) -> type:
        """
        获取 SQL 构建器类

        Spark SQL 直接使用基础构建器 BaseSqlBuilder。

        返回：
            SQL 构建器类
        """
        return BaseSqlBuilder

    def get_paramstyle(self) -> str:
        """
        获取参数占位符风格

        Spark SQL 本身不支持参数化查询，使用 pyformat 风格（%s 占位符）
        通过字符串格式化执行。

        返回：
            'pyformat'
        """
        return 'pyformat'

    def is_available(self) -> bool:
        """
        检查 pyspark 驱动是否可用

        尝试导入 pyspark.sql 模块，判断 PySpark 是否已安装。

        返回：
            True 表示可用，False 表示不可用
        """
        try:
            from pyspark.sql import SparkSession
            return True
        except ImportError:
            return False
