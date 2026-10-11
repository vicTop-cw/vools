"""
pyk.postgre - PostgreSQL 辅助

提供:
- vicPostgreSupport: 表信息/类型转换/建表 SQL 生成 (以 legacy vools.py 为准)
- spark_type_to_postgres: 类型映射
- get_insert_sql_for_postgre / get_create_table_sql / get_insert_sql
- execute_sql_in_postgre
- insertData / createTemp / getTempTb / getTableInfo (以 legacy 为准)
- re_names (以 legacy 为准)
"""

from __future__ import absolute_import

__all__ = [
    "vicPostgreSupport",
    "spark_type_to_postgres",
    "get_insert_sql_for_postgre",
    "get_create_table_sql",
    "get_insert_sql",
    "execute_sql_in_postgre",
    "insertData",
    "createTemp",
    "getTempTb",
    "getTableInfo",
    "re_names",
    "vicSql",
]

import os


# ---- 公开库安全：所有生产连接信息一律走 pyk.configs（密文 + 环境变量），代码里不留影子 ----

def _default_db() -> str:
    """取默认数据库名（走 pyk.configs.default_db，环境变量/显式覆写优先）。"""
    from .configs import default_db
    return default_db()


def _env_pg() -> dict:
    """取 PostgreSQL 连接参数（走 pyk.configs.pg_credentials，密文优先）。"""
    from .configs import pg_credentials
    url, user, password = pg_credentials()
    return {
        "url": url,
        "user": user,
        "password": password,
        "driver": os.environ.get("PYK_PG_DRIVER", "org.postgresql.Driver"),
    }
import re

from .core import get_spark
from .df import vDF


# Spark → PostgreSQL 类型映射
_SPARK_TO_PG = {
    "string": "varchar",
    "varchar": "varchar",
    "char": "char",
    "int": "int",
    "integer": "int",
    "bigint": "bigint",
    "long": "bigint",
    "float": "float8",
    "double": "float8",
    "decimal": "numeric",
    "boolean": "boolean",
    "timestamp": "timestamp",
    "date": "date",
    "array": "text",
    "map": "text",
    "struct": "jsonb",
    "binary": "bytea",
}


def spark_type_to_postgres(spark_type):
    """Spark 类型 → PostgreSQL 类型。"""
    return _SPARK_TO_PG.get(str(spark_type).lower(), "varchar")


# ============================================================
# vicSql (SQL 包装类, 兼容 legacy vools.py L2284)
# ============================================================
class vicSql(str):
    """SQL 查询字符串包装类 (兼容 legacy vicSql)。

    用法:
        vicSql("select * from db.t").toDF()
    """

    def __new__(cls, sql="", *a, **k):
        return super(vicSql, cls).__new__(cls, sql)

    def __init__(self, sql="", *a, **k):
        self.sql = str(sql)

    def toDF(self, *a, **k):
        """把 SQL 转成 DataFrame。"""
        from .core import get_spark
        return get_spark().sql(str(self))


# ============================================================
# re_names (以 legacy vools.py L5738-L5789 为准)
# ============================================================
def re_names(df, new_cols="", prefix="", suffix="", null_str=False):
    """重命名 DataFrame 列。

    参数:
        df:        DataFrame
        new_cols:  新列名 (str/list/dict); 逗号分隔字符串
        prefix:    列名前缀
        suffix:    列名后缀
        null_str:  True 时过滤空列名
    Returns:
        DataFrame
    """
    from pyspark.sql import functions as F

    if (not new_cols == "" and not new_cols) or not df:
        raise ValueError("DataFrame  or new_cols is illegal !")
    prefix = (prefix or "").strip()
    suffix = (suffix or "").strip()

    if isinstance(new_cols, str):
        if "," in new_cols:
            new_cols = list(map(str.strip, new_cols.split(",")))
        else:
            if len(new_cols) == 0 and len(prefix) == 0 and len(suffix) == 0:
                return df
            cs = df.columns
            if len(new_cols) == 0:
                if len(prefix) > 0:
                    cs = ["{}{}".format(prefix, c) for c in cs]
                if len(suffix) > 0:
                    cs = ["{}{}".format(c, suffix) for c in cs]
                return df.select([F.col(col).alias(cs[i]) for i, col in enumerate(df.columns)])
            new_cols = [new_cols.strip()]

    if isinstance(new_cols, dict):
        field_replacements = dict(zip(new_cols.keys(), map(str.strip, new_cols.values())))
    else:
        if null_str:
            new_cols = list(filter(lambda x: len(x) > 0, new_cols))
        if len(prefix) > 0:
            new_cols = ["{}{}".format(prefix, c) if c else "" for c in new_cols]
        if len(suffix) > 0:
            new_cols = ["{}{}".format(c, suffix) if c else "" for c in new_cols]
        cs = df.columns
        n = len(new_cols) if len(new_cols) < len(cs) else len(cs)
        if n == 0:
            return df
        field_replacements = dict(zip(cs[:n], map(str.strip, new_cols[:n])))

    for k in list(field_replacements.keys()):
        if not field_replacements[k]:
            del field_replacements[k]

    return df.select([F.col(col).alias(field_replacements.get(col, col)) for col in df.columns])


# ============================================================
# insertData (以 legacy vools.py L5383-L5510 为准)
# ============================================================
def insertData(source, targetTable, cols=None, part_cols=None, mode="overwrite",
               check_index_only=False, drop_if_exists=False,
               dbName=None,
               update_self=False, update_self_tbName=None):
    """把 DataFrame / SQL / list / dict 写入 Hive 表 (以 legacy 为准)。

    参数:
        source:             DataFrame / list / tuple / vicSql / str / dict / vicTableInfo
        targetTable:        目标表名 (db.table)
        cols:               列名过滤
        part_cols:          分区列
        mode:               overwrite / append / ignore
        check_index_only:   True 时只按列数对齐 (不做列名校验)
        drop_if_exists:     True 时先 drop 表
        dbName:             默认库名
        update_self:        True 时先写临时表 (防自引用)
        update_self_tbName: 临时表名
    Returns:
        None
    """
    spark = get_spark()
    from pyspark.sql import DataFrame
    from pyspark.sql import Row
    from .tb import vicTableInfo
    from .df import vicDataFrame
    from .text import vicSql

    if targetTable:
        if "." not in targetTable:
            dbName = dbName or _default_db()
            targetTable = "{}.{}".format(dbName, targetTable)
    else:
        raise ValueError("targetTable can't be null !")
    if not _regexp_like(r"^[a-z][a-z_0-9]+\.[a-z_0-9]+$", targetTable.lower()):
        raise ValueError("targetTable :{} illegal !".format(targetTable))

    if isinstance(source, DataFrame):
        df = source
    elif isinstance(source, vicDataFrame):
        df = source.df
    elif isinstance(source, (list, tuple)):
        df = _to_df(source, cols)
    elif isinstance(source, vicSql):
        temp_s = source.sql
        df = spark.sql(temp_s)
        if _regexp_like("from +{}".format(targetTable.lower()), temp_s):
            update_self = True
    elif isinstance(source, str):
        if _regexp_like(r"^[a-z][a-z_0-9]+\.[a-z_0-9]+$", source.lower()):
            from .tb import vicTableInfo
            df = vicTableInfo(source).query("")
            if targetTable.lower() == source.lower():
                update_self = True
        else:
            df = spark.sql(source)
            if _regexp_like("from +{}".format(targetTable.lower()), source):
                update_self = True
    elif isinstance(source, vicTableInfo):
        df = source.query("")
        if targetTable.lower() == source.tableName:
            update_self = True
    elif isinstance(source, dict):
        df = spark.createDataFrame([Row(key=k, value=v) for k, v in source.items()])
    else:
        raise TypeError("source's type must be in (DataFrame,list,tuple,vicSql,str) !!!")

    if mode not in ("append", "overwrite", "ignore"):
        raise ValueError("""mode's value must be in ("append","overwrite","ignore")!!!""")

    if update_self:
        update_self_tbName = (
            (update_self_tbName.strip() if "." in update_self_tbName
             else "{}.vic_temp_update_self_{}".format(_default_db(), update_self_tbName.strip()))
            if isinstance(update_self_tbName, str) else None
        )
        temp_tb = update_self_tbName if update_self_tbName else \
            "{}.vic_temp_update_self_{}".format(_default_db(), _random_field())
        df.write.mode("overwrite").format("hive").saveAsTable(temp_tb)
        df = spark.sql("select * from {}".format(temp_tb))

    if drop_if_exists:
        spark.sql("drop table if exists {}".format(targetTable))

    from .tb import vicTableInfo
    tb = vicTableInfo(targetTable)
    if tb.isExists:
        cs = list(map(str.lower, tb.cols))
        part_cols = list(map(str.lower, tb.colsOfPartition)) if tb.countOfPartitionCols > 0 else None
        css = list(map(str.lower, df.columns))
        if len(set(cs) - set(css)) > 0:
            if check_index_only:
                if len(cs) != len(css):
                    raise IndexError("""targetTable's cols  size :({})  equal DataFrame cols size :({})  !!!""".format(
                        len(cs), len(css)))
                else:
                    ks = ["{} as {} ".format(x, y) for x, y in zip(css, cs)]
                    df = df.selectExpr(*ks)
            else:
                raise KeyError("""targetTable's cols :({}) must from DataFrame : ({}) !!!""".format(
                    ",".join(cs), ",".join(css)))
        else:
            df = df.select(*cs)

    if df is None:
        raise ValueError("The result Of DataFrame is None !")

    if part_cols:
        if isinstance(part_cols, str):
            ps = [part_cols]
        elif isinstance(part_cols, (list, tuple)):
            ps = [str(i) for i in part_cols]
        else:
            raise TypeError("part_cols's type must be in (str,list,tuple) !!!")
        spark.sql("set hive.exec.dynamic.partition=true")
        spark.sql("set hive.exec.dynamic.partition.mode=nonstrict")

        if not tb.isExists:
            create_table_statement = """
                CREATE TABLE IF NOT EXISTS {}({}
                ) partitioned by ({})
                """.format(
                targetTable,
                ", ".join(["`{}` {}".format(col, df.schema[col].dataType.simpleString())
                           for col in df.columns if str(col).lower() not in ps]),
                ", ".join(["`{}` {}".format(col, df.schema[col].dataType.simpleString()) for col in ps]),
            )
            spark.sql(create_table_statement)

        md = "into" if mode == "append" else mode
        tempTbName = "vic_temp_{}".format(_hhmmss())
        df.createOrReplaceTempView(tempTbName)
        ss = """
            insert {} table {} partition({})
            select * from {}
        """.format(md, targetTable, ",".join(ps), tempTbName)
        if mode in ("append", "overwrite"):
            spark.sql(ss)
        else:
            df.write.mode(mode).format("hive").insertInto(targetTable)
    else:
        if not tb.isExists:
            create_table_statement = """
                CREATE TABLE IF NOT EXISTS {}({}
                )
                """.format(
                targetTable,
                ", ".join(["`{}` {}".format(col, df.schema[col].dataType.simpleString()) for col in df.columns]),
            )
            spark.sql(create_table_statement)

        md = "into" if mode == "append" else mode
        tempTbName = "vic_temp_{}".format(_hhmmss())
        df.createOrReplaceTempView(tempTbName)
        ss = """
            insert {} table {}
            select * from {}
        """.format(md, targetTable, tempTbName)
        if mode in ("append", "overwrite"):
            spark.sql(ss)
        else:
            df.write.mode(mode).format("hive").insertInto(targetTable)


def createTemp(source, targetTable=None, *a, **k):
    """把 DataFrame 写入临时表 (以 legacy 为准)。

    参数:
        source:      DataFrame / SQL
        targetTable: 临时表名; None 用 vic_temp_ + run_date
    Returns:
        None
    """
    from .core import get_run_ds as _get_run_ds
    vicrun_ds = _get_run_ds()
    targetTable = targetTable.split(".")[-1] if targetTable else "vic_temp_{}".format(vicrun_ds)
    targetTable = targetTable if targetTable.startswith("vic_temp_") else "vic_temp_{}".format(targetTable)
    k["dbName"] = _default_db()
    insertData(source, targetTable, *a, **k)


def getTempTb(tbName=None):
    """取临时表 DataFrame (以 legacy 为准)。

    参数:
        tbName: 临时表名; None 用 run_date
    Returns:
        DataFrame
    """
    from .core import get_run_ds as _get_run_ds
    vicrun_ds = _get_run_ds()
    tbName = tbName or str(vicrun_ds)
    tbName = tbName if tbName.startswith("vic_temp_") else "vic_temp_{}".format(tbName)
    return vDF("select * from {}.{}".format(_default_db(), tbName))


def getTableInfo(tableName, sep=",", dsOffsetNum=3, labels=None, dstr="ds",
                 dbName=None):
    """取表元数据 dict (以 legacy 为准)。

    参数:
        tableName:  表名
        sep:        分隔符 (展示用)
        dsOffsetNum: 偏移天数
        labels:     自定义标签
        dstr:       日期列名
        dbName:     默认库名
    Returns:
        str: dict 的字符串表示 (field_name -> field_value)
    """
    from .tb import vicTableInfo
    dbName = dbName or _default_db()
    tb = vicTableInfo(tableName, sep=sep, ds_offset_num=dsOffsetNum, labels=labels, dstr=0, db_name=dbName)
    df = tb.info
    dct = {}
    for r in df.collect():
        dct[str(r[0])] = str(r[1])
    return str(dct)


# ============================================================
# 旧版 insertData 别名 (兼容现代签名)
# ============================================================
def insert_data(source, target_table, cols=None, part_cols=None, mode="overwrite",
                check_index_only=False, drop_if_exists=False, db_name="default",
                update_self=False, update_self_tb_name=None):
    """insertData 的 snake_case 别名。"""
    return insertData(source, target_table, cols=cols, part_cols=part_cols, mode=mode,
                      check_index_only=check_index_only, drop_if_exists=drop_if_exists,
                      dbName=db_name, update_self=update_self, update_self_tbName=update_self_tb_name)


# ============================================================
# 现代版工具函数 (纯生成 SQL)
# ============================================================
def get_create_table_sql(df, table_name, schema="public", if_not_exists=True):
    """生成 PostgreSQL CREATE TABLE SQL。"""
    cols = []
    for f in df.schema.fields:
        pg_type = spark_type_to_postgres(f.dataType)
        cols.append('"{}" {}'.format(f.name, pg_type))
    prefix = "CREATE TABLE IF NOT EXISTS " if if_not_exists else "CREATE TABLE "
    schema_prefix = "{}.{}".format(schema, table_name) if schema else table_name
    return "{}{} (\n  {}\n);".format(prefix, schema_prefix, ",\n  ".join(cols))


def get_insert_sql(df, table_name, schema="public", batch=1000):
    """根据 Spark DataFrame 生成 PostgreSQL INSERT SQL (多值批量)。"""
    cols = df.columns
    col_str = ", ".join('"{}"'.format(c) for c in cols)
    schema_prefix = "{}.{}".format(schema, table_name) if schema else table_name
    rows = []
    for row in df.collect():
        vals = []
        for i, c in enumerate(cols):
            v = row[i]
            if v is None:
                vals.append("NULL")
            elif isinstance(v, bool):
                vals.append("TRUE" if v else "FALSE")
            elif isinstance(v, (int, float)):
                vals.append(str(v))
            else:
                vals.append("'" + str(v).replace("'", "''") + "'")
        rows.append("({})".format(", ".join(vals)))
        if len(rows) >= batch:
            break
    if not rows:
        return ""
    return "INSERT INTO {} ({}) VALUES\n{};".format(schema_prefix, col_str, ",\n".join(rows))


def get_insert_sql_for_postgre(df, table_name, schema="public", cols=None, mode="overwrite"):
    """兼容接口: 生成 PostgreSQL INSERT SQL。"""
    return get_insert_sql(df, table_name, schema=schema)


def execute_sql_in_postgre(sql, conn=None, fetch=True):
    """在 PostgreSQL 中执行 SQL (需要 psycopg2)。"""
    try:
        import psycopg2
    except ImportError as e:
        raise ImportError("执行 PostgreSQL SQL 需要 psycopg2: {}".format(e))
    if conn is None:
        conn = psycopg2.connect(
            host=os.environ.get("PG_HOST", "localhost"),
            port=os.environ.get("PG_PORT", "5432"),
            dbname=os.environ.get("PG_DB", ""),
            user=os.environ.get("PG_USER", ""),
            password=os.environ.get("PG_PASSWORD", ""),
        )
    cur = conn.cursor()
    cur.execute(sql)
    result = cur.fetchall() if fetch else None
    conn.commit()
    cur.close()
    return result


# ============================================================
# vicPostgreSupport (以 legacy vools.py L5836-L6099 为准)
# ============================================================
class vicPostgreSupport(object):
    """PostgreSQL 表支持类。

    用法:
        p = vicPostgreSupport("pg_table", sql="select * from public.tb")
        p.query()                       # 读表
        p.pushData(df, "public.tb")     # 写表
        p("drop table if exists t")     # 执行 DDL
    """

    def __init__(self, dbtable="", sql="", dbName="public", spark=None,
                 url=None, user=None, password=None,
                 driver=None):
        """初始化。

        参数:
            dbtable:  表名 (支持 public.tb)
            sql:      默认 SQL
            dbName:   默认 schema
            spark:    SparkSession; None 用 get_spark()
            url:      JDBC 连接串；None 用 env PYK_PG_URL
            user:     用户名；None 用 env PYK_PG_USER
            password: 密码；None 用 env PYK_PG_PASSWORD
            driver:   JDBC 驱动类名；None 用 env PYK_PG_DRIVER
        """
        _pg = _env_pg()
        if url is None:
            url = _pg["url"]
        if user is None:
            user = _pg["user"]
        if password is None:
            password = _pg["password"]
        if driver is None:
            driver = _pg["driver"]
        self.spark = spark or get_spark()
        self.user = user
        self.url = url
        self._isExists = None
        self.password = password
        self.driver = driver
        self.dbName = dbName
        self.last_error = None
        self.sql = sql
        if dbtable and self.regexp_like(r"^[a-z][a-z_0-9]+$", str(dbtable).lower().strip()):
            dbtable = "{}.{}".format(dbName, dbtable)
        self._dbtable = str(dbtable).lower().strip()

    @staticmethod
    def regexp_like(pattern, text, flags=0):
        """正则匹配 (兼容 legacy vicTools.regexp_like)。"""
        return re.search(pattern, str(text), flags) is not None

    @property
    def dbtable(self):
        return self._dbtable

    @dbtable.setter
    def dbtable(self, value):
        temp = str(value).strip().lower()
        if self._dbtable != temp:
            self._isExists = None
            self._dbtable = temp

    @property
    def isExists(self):
        """表是否已存在。"""
        if self._isExists is not None:
            return self._isExists
        try:
            df = self.query(self.dbtable).limit(1)
            df.count()
            self._isExists = True
        except Exception as e:
            self._isExists = False
            self.last_error = e
        return self._isExists

    @property
    def properties(self):
        """JDBC 连接属性 dict。"""
        return {
            "url": self.url,
            "user": self.user,
            "password": self.password,
            "driver": self.driver,
        }

    def execute_sql_in_postgre(self, sql=None):
        """执行 DDL/DML 语句 (通过 JVM JDBC)。

        参数:
            sql: SQL 语句; None 用 self.sql
        Returns:
            bool: 是否成功
        """
        if not sql:
            sql = self.sql
        if not sql:
            return False
        p = True
        try:
            jvm = self.spark.sparkContext._gateway.jvm
            jvm.Class.forName("org.postgresql.Driver")
            conn = jvm.java.sql.DriverManager.getConnection(self.url, self.user, self.password)
            stmt = conn.createStatement()
            stmt.execute(sql)
        except Exception as e:
            print("失败: {}".format(e))
            p = False
            self.last_error = e
        finally:
            if 'stmt' in locals():
                stmt.close()
            if 'conn' in locals():
                conn.close()
        return p

    def drop(self, dbtable=None):
        """DROP TABLE IF EXISTS。

        参数:
            dbtable: 表名; None 用 self.dbtable
        Returns:
            bool: 是否成功
        """
        if not dbtable:
            dbtable = self.dbtable
        if not dbtable:
            self.last_error = ValueError(" dbtable is None or blank ")
            return False
        sql = dbtable
        if self.regexp_like(r"^[a-z][a-z_0-9]+\.[a-z_0-9]+$", str(dbtable).lower().strip()):
            sql = "DROP TABLE IF EXISTS {}".format(dbtable)
        elif self.regexp_like(r"^[a-z][a-z_0-9]+$", str(dbtable).lower().strip()):
            sql = "DROP TABLE IF EXISTS public.{}".format(dbtable)
        p = True
        try:
            jvm = self.spark.sparkContext._gateway.jvm
            jvm.Class.forName("org.postgresql.Driver")
            conn = jvm.java.sql.DriverManager.getConnection(self.url, self.user, self.password)
            stmt = conn.createStatement()
            stmt.execute(sql)
            print("表删除成功！")
            self._isExists = False
        except Exception as e:
            self._isExists = None
            self.last_error = e
            print("删除失败: {}".format(e))
            p = False
        finally:
            if 'stmt' in locals():
                stmt.close()
            if 'conn' in locals():
                conn.close()
        return p

    def __bool__(self):
        return self.isExists

    def query(self, sql=""):
        """读取 PostgreSQL 表/视图为 DataFrame (Spark JDBC)。

        参数:
            sql: 查询语句; None 用 self.sql
        Returns:
            DataFrame
        """
        if sql:
            return self.spark.read.format("jdbc").options(**self.properties).option("query", sql).load()
        if self.dbtable:
            return self.spark.read.format("jdbc").options(**self.properties).option("dbtable", self.dbtable).load()
        raise ValueError("vicPostgreSupport.query needs sql or dbtable !!!")

    @staticmethod
    def spark_type_to_postgres(data_type):
        """Spark 类型 → PostgreSQL 类型 (legacy 静态方法)。"""
        return _SPARK_TO_PG.get(str(data_type).lower(), "varchar")

    def pushData(self, source, targetTable="", mode="overwrite",
                 drop_if_exists=False, part_cols=None):
        """把 DataFrame 写入 PostgreSQL 表 (Spark JDBC)。

        参数:
            source:         DataFrame / list / tuple / vicSql / str
            targetTable:    目标表名; None 用 self.dbtable
            mode:           overwrite / append
            drop_if_exists: True 时先 drop 表
            part_cols:      分区列 (Spark JDBC 不使用, 兼容接口)
        Returns:
            None
        """
        from pyspark.sql import DataFrame
        from .tb import vicTableInfo
        from .df import vicDataFrame
        from .text import vicSql

        if not targetTable:
            targetTable = self.dbtable
        if isinstance(source, DataFrame):
            df = source
        elif isinstance(source, (list, tuple)):
            df = _to_df(source)
        elif isinstance(source, str):
            if self.regexp_like(r"^[a-z][a-z_0-9]+\.[a-z_0-9]+$", source.lower().strip()):
                df = self.query("select * from {}".format(source))
            else:
                df = self.spark.sql(source)
        elif isinstance(source, vicSql):
            df = self.spark.sql(source.sql)
        elif isinstance(source, vicTableInfo):
            df = source.query("")
        elif isinstance(source, vicDataFrame):
            df = source.df
        else:
            df = _to_df(source)

        postgres_config = self.properties
        if drop_if_exists:
            self.drop(targetTable)
        if part_cols and mode == "overwrite":
            self.spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
            df = df.repartition(*part_cols)
        df.write.format("jdbc").options(**postgres_config).mode(mode).save()

    def __call__(self, **kwargs):
        """执行 SQL / 查询。

        参数:
            sql: SQL 语句
            exe: True 时走 execute_sql_in_postgre; False 走 query
        Returns:
            DataFrame / bool
        """
        sql = kwargs.pop("sql", self.sql).strip()
        if sql:
            p = sql.lower().startswith("select") or sql.lower().startswith("show")
            exe = kwargs.pop("exe", not p)
            from .text import vicText
            sql = vicText(sql).formatEx(**kwargs)
            f = self.execute_sql_in_postgre if exe else self.query
            return f(sql)
        return self.query()


# ============================================================
# 内部工具
# ============================================================
def _regexp_like(pattern, text, flags=0):
    """正则匹配 (兼容 legacy vicTools.regexp_like)。"""
    return re.search(pattern, str(text), flags) is not None


def _random_field():
    """生成随机字段名 (兼容 legacy vicTools.generate_random_field_name)。"""
    import random
    import string
    return "vq_{}".format("".join(random.choices(string.ascii_lowercase, k=6)))


def _hhmmss():
    """取 HHMMSS 格式当前时间 (兼容 legacy toDate(fmt='HHmmSS'))。"""
    from datetime import datetime
    return datetime.now().strftime("%H%M%S")


def _to_df(source, cols=None):
    """兼容 legacy vicTools.toDF 的简单实现。"""
    if isinstance(source, (list, tuple)):
        return vDF(source, cols=cols)
    return vDF(source)






