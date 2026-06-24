"""
vools.sql.spark - Spark SQL 方言包

提供 Spark SQL 方言的完整实现，包括方言类、连接类
以及便捷的连接函数。基于 PySpark 的 SparkSession。

用法：
    from vools.sql.spark import connect, SparkSqlDialect, SparkConnection

    # 便捷方式
    conn = connect(app_name='my_app')
    result = conn.execute('SELECT 1')

    # 手动方式
    dialect = SparkSqlDialect()
    conn = dialect.create_connection(app_name='my_app')
    conn.connect()
"""

import os as _os
import sys as _sys


def _setup_pyspark_env():
    """
    配置 PySpark 环境

    优先使用 pip 安装的 PySpark，如果 pip 没有安装则尝试使用 SPARK_HOME。
    """
    try:
        import importlib.metadata
        importlib.metadata.version('pyspark')
        _os.environ.pop('SPARK_HOME', None)
        return
    except Exception:
        pass

    spark_home = _os.environ.get('SPARK_HOME')
    if spark_home:
        spark_python = _os.path.join(spark_home, 'python')
        if _os.path.isdir(spark_python) and spark_python not in _sys.path:
            _sys.path.insert(0, spark_python)
            lib_dir = _os.path.join(spark_python, 'lib')
            if _os.path.isdir(lib_dir):
                for f in _os.listdir(lib_dir):
                    if f.startswith('py4j') and f.endswith('.zip'):
                        py4j_zip = _os.path.join(lib_dir, f)
                        if py4j_zip not in _sys.path:
                            _sys.path.insert(0, py4j_zip)
                        break


_setup_pyspark_env()

from .dialect import SparkSqlDialect
from .connection import SparkConnection
from .scala_bridge import ScalaBridge


_dialect: SparkSqlDialect = None


def _get_dialect() -> SparkSqlDialect:
    """
    获取全局 Spark SQL 方言实例

    返回：
        SparkSqlDialect 单例实例
    """
    global _dialect
    if _dialect is None:
        _dialect = SparkSqlDialect()
    return _dialect


def is_available() -> bool:
    """
    检查 PySpark 驱动是否可用

    尝试导入 pyspark.sql 模块，判断 PySpark 是否已安装。

    返回：
        True 表示可用，False 表示不可用
    """
    return _get_dialect().is_available()


def connect(
    app_name: str = 'vools_spark',
    master: str = 'local[*]',
    catalog: str = 'spark_catalog',
    database: str = 'default',
    **kwargs
) -> SparkConnection:
    """
    创建并连接 Spark SQL

    便捷函数，创建 SparkConnection 并自动建立连接。

    参数：
        app_name: Spark 应用名称，默认为 'vools_spark'
        master: Spark master URL，默认为 'local[*]'
        catalog: 当前 catalog 名称，默认为 'spark_catalog'
        database: 当前数据库名称，默认为 'default'
        **kwargs: 额外的 Spark 配置项

    返回：
        已连接的 SparkConnection 实例

    用法：
        conn = connect(app_name='my_app')
        result = conn.execute('SELECT 1')
        conn.close()
    """
    conn = SparkConnection(
        app_name=app_name,
        master=master,
        catalog=catalog,
        database=database,
        **kwargs
    )
    conn.connect()
    return conn


__all__ = [
    'SparkSqlDialect',
    'SparkConnection',
    'ScalaBridge',
    'connect',
    'is_available',
]
