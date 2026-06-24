"""
vools.sql.spark.connection - Spark SQL 连接实现

提供 Spark SQL 连接的具体实现，基于 PySpark 的 SparkSession，
封装了 SparkSession 管理、SQL 执行、数据读取等功能。
"""

from typing import Any, Optional, Sequence, List, Tuple

from ..core.connection import Connection
from ..core.result import ResultSet, Row


class SparkConnection(Connection):
    """
    Spark SQL 连接实现类

    基于 PySpark SparkSession 实现的连接类，
    提供统一的连接管理、SQL 执行、数据读写接口。

    与传统数据库连接不同，SparkConnection 封装的是 SparkSession，
    支持读取多种数据源（CSV、Parquet、JSON 等）并执行 Spark SQL 查询。

    用法：
        conn = SparkConnection(app_name='my_app', master='local[*]')
        conn.connect()
        result = conn.execute('SELECT 1')
        conn.close()

    上下文管理器用法：
        with SparkConnection(app_name='test') as conn:
            result = conn.sql('SELECT 1 + 1')
    """

    _spark: Any = None
    _app_name: str
    _master: str
    _config: dict
    _catalog: str
    _database: str
    _scala_bridge: Any = None

    def __init__(
        self,
        app_name: str = 'vools_spark',
        master: str = 'local[*]',
        catalog: str = 'spark_catalog',
        database: str = 'default',
        **kwargs
    ):
        """
        初始化 Spark 连接

        参数：
            app_name: Spark 应用名称，默认为 'vools_spark'
            master: Spark master URL，默认为 'local[*]'（本地模式，使用所有核心）
            catalog: 当前 catalog 名称，默认为 'spark_catalog'
            database: 当前数据库名称，默认为 'default'
            **kwargs: 额外的 Spark 配置项
        """
        self._app_name = app_name
        self._master = master
        self._catalog = catalog
        self._database = database
        self._config = kwargs
        self._connected = False
        self._spark = None

    def connect(self, **kwargs: Any) -> None:
        """
        创建或获取 SparkSession

        使用 SparkSession.builder 构建 SparkSession，
        连接成功后将 _connected 标记为 True。
        如果已有连接，先关闭再重新连接。

        参数：
            **kwargs: 额外的连接参数，会覆盖初始化时的参数
        """
        if self._connected:
            self.close()

        from pyspark.sql import SparkSession

        builder = SparkSession.builder.appName(self._app_name)

        if self._master:
            builder = builder.master(self._master)

        for key, value in self._config.items():
            builder = builder.config(key, value)

        for key, value in kwargs.items():
            if key == 'app_name':
                self._app_name = value
                builder = SparkSession.builder.appName(value)
                if self._master:
                    builder = builder.master(self._master)
                for k, v in self._config.items():
                    builder = builder.config(k, v)
            elif key == 'master':
                self._master = value
            elif key == 'catalog':
                self._catalog = value
            elif key == 'database':
                self._database = value
            else:
                builder = builder.config(key, value)

        self._spark = builder.getOrCreate()

        if self._catalog and self._catalog != 'spark_catalog':
            try:
                self._spark.sql(f"USE CATALOG {self._catalog}")
            except Exception:
                pass

        if self._database and self._database != 'default':
            try:
                self._spark.sql(f"USE {self._database}")
            except Exception:
                pass

        self._connected = True

    def close(self) -> None:
        """
        停止 SparkSession

        停止当前 SparkSession，释放相关资源。
        关闭后将 _connected 标记为 False。
        若连接已关闭，则不执行任何操作。
        """
        if not self._connected:
            return

        try:
            if self._spark is not None:
                self._spark.stop()
        finally:
            self._spark = None
            self._connected = False

    def execute(self, sql: str, params: Optional[Sequence] = None) -> ResultSet:
        """
        执行 SQL 查询

        使用 spark.sql(sql) 执行 SQL 查询，
        将 DataFrame 转换为 ResultSet 返回。

        如果 params 不为 None，先用 params 格式化 SQL 字符串
        （使用 %s 占位符），再执行。

        参数：
            sql: 要执行的 SQL 语句
            params: SQL 参数序列，用于替换 SQL 中的 %s 占位符

        返回：
            ResultSet 查询结果集对象

        异常：
            RuntimeError: 连接未建立
        """
        if not self._connected or self._spark is None:
            raise RuntimeError('Spark connection is not established')

        if params is not None:
            sql = sql % tuple(params)

        df = self._spark.sql(sql)
        columns = [field.name for field in df.schema.fields]
        rows_data = df.collect()
        rows = [tuple(row) for row in rows_data]

        return ResultSet(
            columns=columns,
            rows=rows,
            rowcount=len(rows),
        )

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence]) -> int:
        """
        批量执行 SQL 语句

        Spark SQL 不常用批量执行，此方法遍历参数序列逐条执行，
        返回序列长度作为受影响行数。

        参数：
            sql: 要执行的 SQL 语句
            seq_of_params: 参数序列的序列，每组参数对应一次执行

        返回：
            执行次数（序列长度）

        异常：
            RuntimeError: 连接未建立
        """
        if not self._connected or self._spark is None:
            raise RuntimeError('Spark connection is not established')

        count = 0
        for params in seq_of_params:
            formatted_sql = sql % tuple(params)
            self._spark.sql(formatted_sql)
            count += 1

        return count

    def commit(self) -> None:
        """
        提交事务

        Spark SQL 通常自动提交，此方法为空操作。
        """
        pass

    def rollback(self) -> None:
        """
        回滚事务

        Spark SQL 不支持事务，此方法为空操作。
        """
        pass

    def cursor(self) -> Any:
        """
        获取底层 SparkSession

        Spark 没有传统 cursor 概念，
        返回底层 SparkSession 本身。

        返回：
            SparkSession 实例

        异常：
            RuntimeError: 连接未建立
        """
        if not self._connected or self._spark is None:
            raise RuntimeError('Spark connection is not established')
        return self._spark

    def sql(self, sql_str: str) -> ResultSet:
        """
        执行 SQL 查询（别名方法）

        与 execute 方法功能相同，提供更符合 Spark 习惯的方法名。

        参数：
            sql_str: 要执行的 SQL 语句

        返回：
            ResultSet 查询结果集对象
        """
        return self.execute(sql_str)

    def read_csv(self, path: str, **kwargs) -> ResultSet:
        """
        读取 CSV 文件

        使用 Spark 读取 CSV 文件并返回 ResultSet。

        参数：
            path: CSV 文件路径
            **kwargs: 额外参数传递给 spark.read.csv()，如 header、inferSchema 等

        返回：
            ResultSet 查询结果集对象

        异常：
            RuntimeError: 连接未建立
        """
        if not self._connected or self._spark is None:
            raise RuntimeError('Spark connection is not established')

        df = self._spark.read.csv(path, **kwargs)
        columns = [field.name for field in df.schema.fields]
        rows_data = df.collect()
        rows = [tuple(row) for row in rows_data]

        return ResultSet(
            columns=columns,
            rows=rows,
            rowcount=len(rows),
        )

    def read_parquet(self, path: str, **kwargs) -> ResultSet:
        """
        读取 Parquet 文件

        使用 Spark 读取 Parquet 文件并返回 ResultSet。

        参数：
            path: Parquet 文件路径
            **kwargs: 额外参数传递给 spark.read.parquet()

        返回：
            ResultSet 查询结果集对象

        异常：
            RuntimeError: 连接未建立
        """
        if not self._connected or self._spark is None:
            raise RuntimeError('Spark connection is not established')

        df = self._spark.read.parquet(path, **kwargs)
        columns = [field.name for field in df.schema.fields]
        rows_data = df.collect()
        rows = [tuple(row) for row in rows_data]

        return ResultSet(
            columns=columns,
            rows=rows,
            rowcount=len(rows),
        )

    def read_json(self, path: str, **kwargs) -> ResultSet:
        """
        读取 JSON 文件

        使用 Spark 读取 JSON 文件并返回 ResultSet。

        参数：
            path: JSON 文件路径
            **kwargs: 额外参数传递给 spark.read.json()

        返回：
            ResultSet 查询结果集对象

        异常：
            RuntimeError: 连接未建立
        """
        if not self._connected or self._spark is None:
            raise RuntimeError('Spark connection is not established')

        df = self._spark.read.json(path, **kwargs)
        columns = [field.name for field in df.schema.fields]
        rows_data = df.collect()
        rows = [tuple(row) for row in rows_data]

        return ResultSet(
            columns=columns,
            rows=rows,
            rowcount=len(rows),
        )

    def create_temp_view(self, view_name: str, dataframe_or_resultset: Any) -> None:
        """
        创建临时视图

        将 DataFrame 或 ResultSet 注册为临时视图，
        可在 SQL 查询中引用。

        参数：
            view_name: 临时视图名称
            dataframe_or_resultset: PySpark DataFrame 或 ResultSet 对象

        异常：
            RuntimeError: 连接未建立
            TypeError: 参数类型不支持
        """
        if not self._connected or self._spark is None:
            raise RuntimeError('Spark connection is not established')

        from pyspark.sql import DataFrame

        if isinstance(dataframe_or_resultset, DataFrame):
            df = dataframe_or_resultset
        elif isinstance(dataframe_or_resultset, ResultSet):
            data = dataframe_or_resultset.to_list()
            df = self._spark.createDataFrame(data)
        else:
            raise TypeError(
                f'Unsupported type: {type(dataframe_or_resultset)}. '
                f'Expected DataFrame or ResultSet.'
            )

        df.createTempView(view_name)

    def create_or_replace_temp_view(self, view_name: str, dataframe_or_resultset: Any) -> None:
        """
        创建或替换临时视图

        将 DataFrame 或 ResultSet 注册为临时视图，
        如果视图已存在则替换。

        参数：
            view_name: 临时视图名称
            dataframe_or_resultset: PySpark DataFrame 或 ResultSet 对象

        异常：
            RuntimeError: 连接未建立
            TypeError: 参数类型不支持
        """
        if not self._connected or self._spark is None:
            raise RuntimeError('Spark connection is not established')

        from pyspark.sql import DataFrame

        if isinstance(dataframe_or_resultset, DataFrame):
            df = dataframe_or_resultset
        elif isinstance(dataframe_or_resultset, ResultSet):
            data = dataframe_or_resultset.to_list()
            df = self._spark.createDataFrame(data)
        else:
            raise TypeError(
                f'Unsupported type: {type(dataframe_or_resultset)}. '
                f'Expected DataFrame or ResultSet.'
            )

        df.createOrReplaceTempView(view_name)

    @property
    def spark(self) -> Any:
        """
        获取底层 SparkSession

        返回：
            SparkSession 实例

        异常：
            RuntimeError: 连接未建立
        """
        if not self._connected or self._spark is None:
            raise RuntimeError('Spark connection is not established')
        return self._spark

    @property
    def scala(self) -> Any:
        """
        获取 Scala 桥接对象

        提供与 Scala/Java 互操作的便捷接口，
        支持调用 Scala 类、注册 Scala UDF、加载 Jar 包等。

        返回：
            ScalaBridge 实例

        异常：
            RuntimeError: 连接未建立
        """
        if not self._connected or self._spark is None:
            raise RuntimeError('Spark connection is not established')
        if self._scala_bridge is None:
            from .scala_bridge import ScalaBridge
            self._scala_bridge = ScalaBridge(self)
        return self._scala_bridge

    @property
    def app_name(self) -> str:
        """
        获取应用名称

        返回：
            Spark 应用名称
        """
        return self._app_name

    @property
    def master(self) -> str:
        """
        获取 master URL

        返回：
            Spark master URL
        """
        return self._master

    @property
    def catalog(self) -> str:
        """
        获取当前 catalog

        返回：
            当前 catalog 名称
        """
        return self._catalog

    @property
    def database(self) -> str:
        """
        获取当前数据库

        返回：
            当前数据库名称
        """
        return self._database

    def __repr__(self) -> str:
        """
        返回字符串表示

        返回：
            SparkConnection 的字符串表示
        """
        status = 'connected' if self._connected else 'closed'
        return (
            f"SparkConnection(app_name={self._app_name!r}, "
            f"master={self._master!r}, "
            f"status={status})"
        )
