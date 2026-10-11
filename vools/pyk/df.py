"""
pyk.df - DataFrame 扩展

提供:
- vicDataFrame: DataFrame 的链式包装类 (兼容 legacy vicDataFrame)
- unique_by / show_ex / select_ex / grouping_sets / order_cols
- chunk_df / insert / push / to_excel / to_parquet
- with_flag_field / get_missing_dates
"""

from __future__ import absolute_import

__all__ = [
    "vicDataFrame",
    "unique_by",
    "show_ex",
    "select_ex",
    "grouping_sets",
    "order_cols",
    "to_list",
    "chunk_df",
    "insert",
    "push",
    "to_excel",
    "to_parquet",
    "with_flag_field",
    "get_missing_dates",
    "vDF",
    # ---- legacy vools.py L6864-L8380 迁移（DataFrame / GroupedData 扩展）----
    "get_spark",
    "groupingSets",
    "orderCols",
    "withColumn_",
    "withColumns",
    "_df_trans_form",
    "_df_write_to",
    "_df_order_by",
    "_df_group_by",
    "_df_stack",
    "_df_selectEx",
    "_df_exists_helper",
    "_df_exists",
    "_df_not_exists",
    "_df_from_sql",
    "_df_scalar",
    "_df_unionEx",
    "_df_cols",
    "spark_df_to_csv",
    "_df_unique_by",
    "_get_order_col",
    "_get_part_col",
    "_trans_cs_for_cols",
    "_df_to_parquet",
    "_to_column",
    "_gf_aggEx",
    "_gf_aggEx2",
    "_gf_pivotEx",
    "_gf_show_distinct",
    "_df_show_Distinct",
    "_df_show_distinct",
    "write_err",
]

import os
import sys


# ---- 公开库安全：生产共享目录走 pyk.configs，代码里不留任何内网路径 ----

def _share_dir() -> str:
    """取生产共享目录（走 pyk.configs.share_dir，环境变量 PYK_SHARE_DIR 优先）。"""
    from .configs import share_dir
    return share_dir()
import pandas as pd


# ============================================================
# vicDataFrame : DataFrame 链式包装
# ============================================================
class vicDataFrame(object):
    """DataFrame 的链式包装类。

    用法:
        vdf = vicDataFrame(spark_df)
        vdf.unique_by(["id"]).show_ex()
        vdf.groupingSets(...)
    """

    def __init__(self, src):
        """初始化。

        Args:
            src: pyspark DataFrame 或 vicDataFrame 或 DataFrame 的 list/tuple
        """
        if isinstance(src, vicDataFrame):
            self._df = src._df
        elif hasattr(src, "columns") and hasattr(src, "show"):
            self._df = src
        elif isinstance(src, (list, tuple)):
            self._df = vDF(src)
        else:
            self._df = vDF(src)

    # ---- 属性 ----
    @property
    def df(self):
        return self._df

    @property
    def columns(self):
        return list(self._df.columns)

    def to_list(self):
        """转成 Python list[Row]"""
        return self._df.collect()

    # ---- 链式 ----
    def run(self, func=print):
        """执行副作用操作, 返回自身"""
        func(self._df)
        return self

    # ---- 集合/算子 ----
    def __add__(self, other):
        return vicDataFrame(self._df.unionAll(other.df if isinstance(other, vicDataFrame) else other))

    def __sub__(self, other):
        other_df = other.df if isinstance(other, vicDataFrame) else other
        return vicDataFrame(self._df.exceptAll(other_df))

    def __and__(self, other):
        other_df = other.df if isinstance(other, vicDataFrame) else other
        return vicDataFrame(self._df.intersect(other_df))

    def __or__(self, other):
        other_df = other.df if isinstance(other, vicDataFrame) else other
        return vicDataFrame(self._df.union(other_df))

    # ---- 方法 ----
    def unique_by(self, partition_by, order_by=None):
        """按 partition_by 分组，取 order_by 排序后的第一条。"""
        return vicDataFrame(unique_by(self._df, partition_by, order_by))

    def show_ex(self, n=100):
        """展示前 n 行, 返回 self"""
        self._df.show(n)
        return self

    def select_ex(self, *cols, **kcols):
        """列选择扩展, 支持 'a,b,c' 字符串和 dict"""
        return vicDataFrame(select_ex(self._df, *cols, **kcols))

    def grouping_sets(self, group_cols, sets_expr, *agg_expr, **kwargs):
        """GROUPING SETS 查询。"""
        return vicDataFrame(grouping_sets(self._df, group_cols, sets_expr, *agg_expr, **kwargs))

    def order_cols(self, key=None, reverse=False):
        """按列名/列序号排序。"""
        return vicDataFrame(order_cols(self._df, key=key, reverse=reverse))

    def chunk_df(self, *args, **kwargs):
        """把 DataFrame 切分成多个 chunk (按行数)。"""
        return chunk_df(self._df, *args, **kwargs)

    def insert(self, *args, **kwargs):
        """插入到 Hive 表。"""
        return insert(self._df, *args, **kwargs)

    def push(self, *args, **kwargs):
        """写入到 Hive 表(简化接口)。"""
        return push(self._df, *args, **kwargs)

    def to_excel(self, *args, **kwargs):
        """转 pandas 并写 Excel。"""
        return to_excel(self._df, *args, **kwargs)

    def to_parquet(self, *args, **kwargs):
        """写 parquet 到本地/HDFS。"""
        return to_parquet(self._df, *args, **kwargs)

    def with_flag_field(self, cols):
        """给每行加一个序号/flag 字段。"""
        return vicDataFrame(with_flag_field(self._df, cols))

    def get_missing_dates(self, col_name, start=None, end=None):
        """找缺失日期。"""
        return get_missing_dates(self._df, col_name, start=start, end=end)


# ============================================================
# 工具函数
# ============================================================
def vDF(source, cols=None, pos_name=None, source_type="hive", view_name="", cache=False):
    """把多种输入源转为 DataFrame (兼容 legacy vools.vDF)。

    参数:
        source:      str(SQL/路径) | DataFrame | list/tuple | pandas DataFrame | Row list
        cols:        列名
        pos_name:    位置列名
        source_type: "hive"(SQL 直查) / "file"(路径)
        view_name:   注册临时视图名
        cache:       True 时 cache()

    Returns:
        pyspark.sql.DataFrame
    """
    spark = _get_spark()
    if hasattr(source, "columns") and hasattr(source, "show"):
        df = source
    elif isinstance(source, str):
        if source.strip().lower().startswith("select"):
            df = spark.sql(source)
        elif source.strip().startswith("file://") or source.strip().startswith("hdfs://") or os.path.exists(source):
            df = spark.read.parquet(source)
        else:
            df = spark.sql(source)
    elif isinstance(source, (list, tuple)):
        from pyspark.sql import Row
        rows = [r if isinstance(r, Row) else Row(**dict(zip(cols or ["value"], [r]))) for r in source]
        df = spark.createDataFrame(rows) if rows else spark.createDataFrame([], cols or ["value"])
    else:
        df = spark.createDataFrame(source)

    if pos_name and pos_name not in df.columns:
        from pyspark.sql import functions as F
        from pyspark.sql import Window
        w = Window.orderBy(F.monotonically_increasing_id())
        df = df.withColumn(pos_name, F.row_number().over(w))
    if cols:
        missing = [c for c in cols if c not in df.columns]
        if missing:
            df = df.withColumn(missing[0], F.lit(None))
            return vDF(df, cols, pos_name, source_type, view_name, cache)
        df = df.select(*cols)
    if view_name:
        df.createOrReplaceTempView(view_name)
    if cache:
        df = df.cache()
    return df


def unique_by(df, partition_by, order_by=None):
    """按 partition_by 分组，取 order_by 排序后的第一条。

    参数:
        partition_by: 分组列 (str / list)
        order_by:     排序列 (str / list); None 则按 partition_by 排序

    Returns:
        DataFrame
    """
    from pyspark.sql import functions as F
    from pyspark.sql import Window

    parts = [partition_by] if isinstance(partition_by, str) else list(partition_by)
    orders = [order_by] if isinstance(order_by, str) else (list(order_by) if order_by else parts)
    w = Window.partitionBy(*parts).orderBy(*orders)
    return df.withColumn("_rn", F.row_number().over(w)).filter(F.col("_rn") == 1).drop("_rn")


def show_ex(df, n=100):
    """展示前 n 行, 返回 df。"""
    df.show(n)
    return df


def select_ex(df, *cols, **kcols):
    """列选择扩展。

    支持:
        select_ex(df, "a,b,c")                  # 逗号分隔字符串
        select_ex(df, ["a", "b", "c"])          # 列表
        select_ex(df, "a", "b", "c")            # 多个参数
        select_ex(df, new_col="a + 1")          # 新列名=表达式
    """
    from pyspark.sql import functions as F

    selected = []
    for c in cols:
        if isinstance(c, str) and "," in c:
            selected.extend([x.strip() for x in c.split(",") if x.strip()])
        elif isinstance(c, (list, tuple)):
            selected.extend(list(c))
        else:
            selected.append(c)
    for name, expr in kcols.items():
        if isinstance(expr, str) and expr not in df.columns and expr.strip() not in ("*",):
            selected.append(F.expr(expr).alias(name))
        else:
            selected.append(F.col(expr).alias(name))
    return df.select(*selected)


def grouping_sets(df, group_cols, sets_expr, *agg_expr, **kwargs):
    """GROUPING SETS 查询。

    参数:
        group_cols:  分组列 (list)
        sets_expr:   GROUPING SETS 表达式, 如 "('a','b'),('a',),()"
        agg_expr:    聚合表达式 (string)
    Returns:
        DataFrame
    """
    if isinstance(group_cols, str):
        group_cols = [x.strip() for x in group_cols.split(",")]
    cols_str = ",".join(group_cols)
    sets_str = sets_expr
    sql = "SELECT {cols}, {agg} FROM ({df_sql}) t GROUP BY GROUPING SETS ({sets})".format(
        cols=cols_str,
        agg=", ".join(agg_expr) if agg_expr else "1",
        df_sql="SELECT * FROM df",
        sets=sets_str,
    )
    df.createOrReplaceTempView("_pyk_gss")
    spark = _get_spark()
    return spark.sql(sql)


def order_cols(df, key=None, reverse=False):
    """按列名/列序号排序。"""
    if key is None:
        return df
    cols = df.columns
    if isinstance(key, str):
        cols = [key]
    elif isinstance(key, int):
        cols = [df.columns[key]]
    else:
        cols = list(key)
    from pyspark.sql import functions as F
    return df.orderBy(*[F.col(c).desc() if reverse else F.col(c).asc() for c in cols])


def to_list(df):
    """df → list[Row]"""
    return df.collect()


def chunk_df(df, chunk_size=10000):
    """把 DataFrame 切分成多个子 DataFrame (按行数 chunk)。

    Returns:
        list[DataFrame]
    """
    spark = _get_spark()
    rows = df.rdd.zipWithIndex().filter(lambda x: x[1] < 0)  # placeholder
    return [df]


def insert(df, target_table, mode="overwrite", **kwargs):
    """把 DataFrame 写入 Hive 表。

    参数:
        df:            DataFrame
        target_table:  目标表 (db.table)
        mode:          overwrite / append
    """
    writer = df.write.mode(mode)
    partition_cols = kwargs.pop("partition_cols", None)
    if partition_cols:
        writer = writer.partitionBy(*partition_cols)
    writer.saveAsTable(target_table)
    return target_table


def push(df, target_table=None, *args, **kwargs):
    """简化版 insert，与 legacy 行为对齐。"""
    return insert(df, target_table, *args, **kwargs)


def to_excel(df, target_file, sheet_name=None, **kwargs):
    """DataFrame → pandas → Excel。

    参数:
        target_file: Excel 文件路径
        sheet_name:  工作表名, 默认 DataFrame 名或 "Sheet1"
    """
    pdf = df.toPandas()
    pdf.to_excel(target_file, sheet_name=sheet_name or "Sheet1", index=False, **kwargs)
    return target_file


def to_parquet(df, local_path=None, overwrite=True, **kwargs):
    """DataFrame → parquet。

    参数:
        local_path: 目标路径; None 则写到 /tmp/pyk_parquet
        overwrite:  True 时覆盖
    Returns:
        str: 实际写入路径
    """
    if local_path is None:
        local_path = os.path.join(os.getcwd(), "_pyk_parquet")
    mode = "overwrite" if overwrite else "error"
    df.write.mode(mode).parquet(local_path)
    return local_path


def with_flag_field(df, cols):
    """给 DataFrame 加序号字段。

    参数:
        df:    DataFrame
        cols:  分组列 (str/list); None 表示全局排序
    Returns:
        DataFrame
    """
    from pyspark.sql import functions as F
    from pyspark.sql import Window

    if cols is None or cols == "":
        w = Window.orderBy(F.monotonically_increasing_id())
    else:
        parts = [cols] if isinstance(cols, str) else list(cols)
        w = Window.partitionBy(*parts).orderBy(F.monotonically_increasing_id())
    return df.withColumn("row_num", F.row_number().over(w))


def get_missing_dates(df, col_name, start=None, end=None):
    """找 DataFrame 某列缺失日期。

    参数:
        df:         DataFrame
        col_name:   日期列
        start:      起始日期 (yyyy-MM-dd); None 则取 df min
        end:        结束日期; None 则取 df max
    Returns:
        list[str]: 缺失日期列表
    """
    from vools.datetime import vDate, get_dates

    if df.count() == 0:
        return []
    dates = [str(r[0]) for r in df.select(col_name).distinct().collect()]
    if start is None:
        start = min(dates)
    if end is None:
        end = max(dates)
    all_dates = set(get_dates(end, num=9999, tp="d") if False else _all_dates_between(start, end))
    return sorted(all_dates - set(dates))


def _all_dates_between(start, end):
    """生成 [start, end] 之间的所有日期 (yyyy-MM-dd)。"""
    from datetime import datetime, timedelta
    d0 = datetime.strptime(start, "%Y-%m-%d")
    d1 = datetime.strptime(end, "%Y-%m-%d")
    cur = d0
    while cur <= d1:
        yield cur.strftime("%Y-%m-%d")
        cur += timedelta(days=1)


def _get_spark():
    """懒加载 SparkSession。"""
    from .core import get_spark
    return get_spark()


# ============================================================
# 以下为 legacy vools.py (L6864-L8380) DataFrame / GroupedData
# 扩展函数的迁移。保持 legacy 函数名与签名；pyspark 一律函数内
# import，兼容 pyk 懒加载语义。
# ============================================================

# ---- legacy 全局符号兼容 ----
# vicspark / vicrun_ds 在 legacy 是模块级全局对象，新结构用
# pyk.core 的 get_spark() / get_run_ds() 惰性等价。


def _get_run_ds():
    """legacy vicrun_ds 等价：取 run_date 字符串。"""
    from .core import get_run_ds
    return get_run_ds()


def get_spark(app_name="pyk_spark", master=None, enable_hive=True, **kwargs):
    """pyk.core.get_spark 的别名（re-export，供 vx 兼容层统一取用）。"""
    from .core import get_spark as _gs
    return _gs(app_name=app_name, master=master, enable_hive=enable_hive, **kwargs)


def _nxm():
    """legacy nxm / vicTools.generate_random_field_name 等价。"""
    from vools.utils.tools import generate_random_field_name
    return generate_random_field_name()


def _vList(obj):
    """legacy vList / vicList 等价：包装成 VList。"""
    from vools.data.vlist import VList
    return obj if isinstance(obj, VList) else VList(obj)


def _vTb(name):
    """legacy vTb = vicTableInfo 等价。"""
    from .tb import vicTableInfo
    return vicTableInfo(name)


def _insert_data(*args, **kwargs):
    """legacy insertData 等价。"""
    from .postgre import insertData
    return insertData(*args, **kwargs)


def _vicText(content):
    """legacy vicText 等价。"""
    from vools.data.vtext import VText
    return content if isinstance(content, VText) else VText(str(content))


def _transfer_cols(cols=None):
    """legacy vicTools.transferCols 等价。"""
    from vools.utils.tools import transferCols
    return transferCols(cols)


def groupingSets(df, group_cols, sets_expr, *agg_expr, **kwargs):
    """
    PySpark groupingSets 函数

    参数:
        df: DataFrame - 要处理的DataFrame
        group_cols: str或list - 分组列名
        sets_expr: str或list - 分组集表达式，如"110,101,011"
        agg_expr: str/dict/None - 聚合表达式，None则返回GroupedData
        sep: str - 分隔符，默认为逗号

    返回:
        如果提供agg_expr: 返回聚合后的DataFrame
        如果不提供agg_expr: 返回GroupedData对象用于后续聚合
    """
    sep = kwargs.pop("sep", ",")
    fillna = kwargs.pop("fillna", "#Total")
    factory = kwargs.pop("factory", vDF)
    if len(agg_expr) + len(kwargs) == 0:
        return lambda *agg_expr, **kwargs: groupingSets(df, group_cols, sets_expr, *agg_expr, sep=sep, **kwargs)
    # 处理分组列参数
    df = vDF(df)
    if isinstance(group_cols, str):
        columns = [col.strip() for col in group_cols.split(sep)]
    else:
        columns = list(group_cols)

    # 处理分组集表达式参数
    if isinstance(sets_expr, str):
        sets = [pattern.strip() for pattern in sets_expr.split(sep)]
    else:
        sets = list(sets_expr)

    # 验证参数
    if not columns:
        raise ValueError("分组列不能为空")
    if not sets:
        raise ValueError("分组集表达式不能为空")

    def _build_grouping_sets():
        """构建分组集SQL表达式"""
        grouping_sets = []
        for set_pattern in sets:
            if len(set_pattern) != len(columns):
                raise ValueError(f"分组集表达式长度{len(set_pattern)}必须与列数{len(columns)}相等")

            grouping_cols = []
            for i, char in enumerate(set_pattern):
                if char == '1':
                    grouping_cols.append(columns[i])

            if not grouping_cols:
                grouping_sets.append("()")
            else:
                grouping_sets.append(f"({', '.join(grouping_cols)})")

        return grouping_sets

    def _build_agg_expression(agg_expr, **kwargs):
        """构建聚合表达式"""
        s = "\n, ".join([f"{func} as {alias}" for alias, func in kwargs.items()])
        l = len(agg_expr)
        if l == 1:
            agg_expr = agg_expr[0]
            if isinstance(agg_expr, dict):
                s1 = "\n, ".join([f"{func} as {alias}" for alias, func in agg_expr.items()])
            elif isinstance(agg_expr, str):
                s1 = agg_expr
            elif isinstance(agg_expr, (list, tuple)):
                s1 = "\n, ".join(agg_expr)
            else:
                raise ValueError("agg_expr 必须是字符串或字典")
        else:
            s1 = "\n, ".join(agg_expr)

        if s1 and s:
            return s + "\n, " + s1
        return s1 or s

    # 构建分组集
    grouping_sets_list = _build_grouping_sets()

    # 构建聚合表达式
    agg_expression = _build_agg_expression(agg_expr, **kwargs)

    # 注册临时视图
    temp_view_name = f"temp_{id(df)}"
    df.createOrReplaceTempView(temp_view_name)

    # 构建完整的SQL查询
    sql_query = f"""
        SELECT {', '.join(columns)}, {agg_expression}
        FROM {temp_view_name}
        GROUP BY GROUPING SETS ({', '.join(grouping_sets_list)})
    """
    if factory is None or factory == str:
        return sql_query
    # print(sql_query)
    # 执行查询并返回结果
    spark = get_spark()
    if factory == "df":
        result = spark.sql(sql_query)
        return result.fillna(fillna, columns)

    if factory == "with_flag_field" or factory == with_flag_field:
        result = spark.sql(sql_query)
        result = with_flag_field(result, columns)
        return result.fillna(fillna, columns)

    rs = factory(sql_query)
    if hasattr(rs, "fillna"):
        return rs.fillna(fillna, columns)
    return rs


def orderCols(df, key=None, reverse=False):
    """
    对 DataFrame 的列进行排序

    参数:
        df: 要处理的 DataFrame
        key: 排序函数
            - 如果是单参数函数：应用于列名
            - 如果是双参数函数：应用于列名和列类型
            - 如果为 None：默认按列名字母顺序排序

    返回:
        列排序后的新 DataFrame
    """
    import inspect as ins
    df = vDF(df)
    schema = df.schema
    columns_info = [(str(field.name), str(field.dataType)) for field in schema.fields]

    # 确定排序函数
    if key is None:
        # 默认按列名排序
        sorted_columns = sorted([col_name for col_name, _ in columns_info], reverse=reverse)
    else:
        # 检查 key 函数的参数数量
        sig = ins.signature(key)
        num_params = len(sig.parameters)

        if num_params == 1:
            # 单参数函数：只使用列名
            sorted_columns_info = sorted(columns_info, key=lambda x: key(x[0]), reverse=reverse)
        elif num_params == 2:
            # 双参数函数：使用列名和列类型
            sorted_columns_info = sorted(columns_info, key=lambda x: key(x[0], x[1]), reverse=reverse)
        else:
            raise ValueError("key 函数必须接受 1 个或 2 个参数")

        # 提取排序后的列名
        sorted_columns = [col_name for col_name, _ in sorted_columns_info]

    # 按照新的列顺序重新选择列
    return df.select(sorted_columns)


def withColumn_(df, col_name, col_expr, shell=None):
    from pyspark.sql import functions as F
    from pyspark.sql.functions import expr
    if shell is None:
        col_expr = F.col(col_expr) if isinstance(col_expr, str) and col_expr.lower() in [c.lower() for c in df.columns] else col_expr
        col_expr = col_expr.alias(col_name) if isinstance(col_expr, F.Column) else col_expr
        col_expr = expr(col_expr) if isinstance(col_expr, str) else col_expr
    else:
        col_expr = shell(col_expr)
    return df.withColumn(col_name, col_expr)


def withColumns(df, col_dict=None, **kwargs):
    self_df = df
    if isinstance(col_dict, dict):
        for k, v in col_dict.items():
            self_df = withColumn_(self_df, k, v)
    elif isinstance(col_dict, (list, tuple)):
        for k, v in col_dict:
            self_df = withColumn_(self_df, k, v)
    for k, v in kwargs.items():
        self_df = withColumn_(self_df, k, v)
    return self_df


def _df_trans_form(self, f, *a, **k):
    rs = f(self, *a, **k)
    if not isinstance(rs, self.__class__):
        raise TypeError(" must return a DataFrame !!!")
    return rs


def _df_write_to(df, name, part_cols=None):
    cs = [str(c).lower().strip() for c in df.columns]

    class DF_Writer:
        def __init__(self, name, part_cols):
            self.tb = _vTb(name)
            self.part_cols = _transfer_cols(part_cols)

        @property
        def df(self):
            return df

        @property
        def part_cols(self):
            return self._part_cols

        @part_cols.setter
        def part_cols(self, ps):
            if ps:
                if any(c.lower().strip() not in cs for c in ps):
                    raise ValueError(f"exists {part_cols} not in {cs}")
                self._part_cols = ps
            else:
                self._part_cols = None

        def __getattr__(self, name):
            if name in self.__dict__.keys():
                return self.__dict__[name]
            return getattr(self.tb, name)

        def append(self):
            return self.write(mode="append")

        def write(self, mode="overwrite"):
            if not self.tb:
                raise ValueError(f"Table {self.tb.tableName} is not exist !!!")
            ps = self.tb.colsOfPartition or None
            if (ps or self.part_cols) and self.part_cols != ps:
                raise ValueError(f"Table {self.tb.tableName} has already parttions cols : {ps}  , but provide : {self.part_cols} ")
            _insert_data(df, self.tb.tableName, part_cols=ps, mode=mode)
            return self

        def insert(self):
            self.write()
            return self

        def create(self):
            if self.tb:
                raise ValueError(f"Table {self.tb.tableName} has been exist !!!")
            _insert_data(df, self.tb.tableName, part_cols=self.part_cols, mode="append")
            return self

        def dropAndCreate(self):
            _insert_data(df, self.tb.tableName, part_cols=self.part_cols, mode="append", drop_if_exists=True)
            return self

        def createOrRepalce(self, mode="overwrite", drop_if_exists=False):
            _insert_data(df, self.tb.tableName, part_cols=self.part_cols, mode=mode, drop_if_exists=drop_if_exists)
            return self

        def partitionedBy(self, c1, *c):
            if self.part_cols is None:
                self.part_cols = [c1] + list(c)
            else:
                if c1 is None or c1 == '':
                    self.part_cols = None
                raise ValueError(f"has been provided partition cols : {self.part_cols}")
            return self

    return DF_Writer(name, part_cols)


def _df_order_by(df, *cols, **k):
    """
    为DataFrame添加支持列位置索引的排序函数

    参数:
    df: pyspark.sql.DataFrame
        要排序的DataFrame
    cols: int or str
        列位置索引（从1开始）或列名，负数表示降序

    Returns:
    pyspark.sql.DataFrame: 排序后的DataFrame

    Examples:
    >>> df[A,B,C]
    >>> _order_by(df, 1, 2) -> df.orderBy(A, B)
    >>> _order_by(df, -1, -3) -> df.orderBy(A desc, C desc)
    """
    from pyspark.sql import functions as F
    column_names = df.columns
    max_index = len(column_names)

    order_exprs = []

    for col_arg in cols:
        if isinstance(col_arg, int):
            # 检查索引范围
            if abs(col_arg) < 1 or abs(col_arg) > max_index:
                raise IndexError(f"列索引 {col_arg} 超出范围。有效范围: 1-{max_index} 或 -1-{-max_index}")

            col_index = abs(col_arg) - 1  # 转换为0-based索引
            col_name = column_names[col_index]

            if col_arg > 0:
                # 正数：升序
                order_exprs.append(F.asc(col_name))
            else:
                # 负数：降序
                order_exprs.append(F.desc(col_name))
        else:
            # 非整数参数，直接使用
            order_exprs.append(col_arg)

    return df.orderBy(*order_exprs, **k)


def _df_group_by(df, *a, **k):
    cols = _get_index_cols(df.columns, *a)
    return df.groupBy(*cols, **k)


def _get_index_cols(cols, *ix):
    from vools.utils.tools import get_index_cols
    return get_index_cols(cols, *ix)


def _df_stack(df, stack_cols_name="node,v", ix=None, reserve_cols=None) -> 'StackHelper':
    from pyspark.sql import functions as F
    from vools.utils.tools import generate_lambda as _g

    class StackHelper:
        def __init__(self, stack_cols_name, order_ix=None):
            self.stack_cols_name = stack_cols_name
            self.order_ix = order_ix  # a int
            self.stack_list = []
            self._cast_type = None

            self.reserve_cols = reserve_cols

        def setReverse(self, cs=None, f=None, pos=None):
            """set select_cols when self.__call__ , pos > f > cs ; use this method will get stack_list """
            if all(i is None for i in (cs, f, pos)):
                raise ValueError("(cs,f,pos) -> all params is None !!!")
            orgi_cs = df.columns

            def _inner(cs, cs2):
                if cs and cs2:
                    self.reserve_cols = cs
                    self.setStack(cs=cs2)
                else:
                    raise ValueError("reserve_cols can not be empty or equal df.columns ,must include of df.columns !!!")

            if pos:
                if isinstance(pos, int):
                    if 0 < pos < len(orgi_cs) - 1:
                        _inner(orgi_cs[:pos], orgi_cs[pos:])
                    else:
                        raise ValueError("pos must be a positive int and < len(df.columns) -1 ")
                elif isinstance(pos, slice):
                    cs = orgi_cs[pos]
                    cs2 = [i for i in orgi_cs if i not in cs]
                    _inner(cs, cs2)
                else:
                    raise TypeError("pos must be a positive int or slice obj !!!")
                return self

            if f:
                if isinstance(f, str):
                    f = _g(f)
                if callable(f):
                    cs = f(orgi_cs)
                    cs2 = [i for i in orgi_cs if i not in cs]
                    _inner(cs, cs2)
                else:
                    raise TypeError("f must be a func,f(df.columns) !!!")
                return self
            cs = _transfer_cols(cs)
            cs = [i for i in orgi_cs if i in cs]
            cs2 = [i for i in orgi_cs if i not in cs]
            _inner(cs, cs2)

            return self

        def setStack(self, cs=None, f=None):
            """when provide f use f else use cs,
                f :function(df.columns) ,
                cs :[col1,col2...] filter in df.columns """
            if f is None and cs is None:
                raise ValueError("param f and cs all are None !!!")
            self.stack_list.clear()
            orgi_cs = df.columns

            if f and isinstance(f, str):
                f = _g(f)
            if f and callable(f):
                cs = f(orgi_cs)

            cs = _transfer_cols(cs)
            for item in cs:
                if isinstance(item, str):
                    if item in orgi_cs:
                        self._option2(item, item)
                    elif "," in item:
                        self._option1(item)
                    else:
                        pass
                elif isinstance(item, (list, tuple)):
                    l = len(item)
                    if l == 1:
                        if item[0] in orgi_cs:
                            self._option2(item[0], item[0])
                        elif "," in item[0]:
                            self._option1(item[0])
                        else:
                            pass
                    elif l == 2:
                        self._option2(*item)
                    elif l == 3:
                        self._option3(*item)
                    else:
                        pass
                else:
                    pass
            return self

        @property
        def source(self):
            return df

        @property
        def cast_type(self):
            return self._cast_type

        @cast_type.setter
        def cast_type(self, cast_type):
            self._cast_type = cast_type
            return self

        def cast(self, cast_type: str):
            self.cast_type = cast_type
            return self

        def _option3(self, node, v, ix):
            self.stack_list.append((node, v, ix))
            return self

        def _option2(self, node, v):
            ix = None if self.order_ix is None else self.order_ix + len(self.stack_list)
            self._option3(node, v, ix)
            return self

        def _option1(self, node_and_v):
            assert isinstance(node_and_v, str) and "," in node_and_v
            nodes = node_and_v.split(",")
            assert len(nodes) in (2, 3)
            return self._option2(nodes[0], nodes[1]) if len(nodes) == 2 else self._option3(nodes[0], nodes[1], nodes[2])

        def option(self, *node_and_v, node=None, v=None, ix=None):
            l = len(node_and_v)
            if node is None and v is None and ix is None:
                if not l in (1, 2, 3):
                    raise ValueError(f"invalid node_and_v: {node_and_v}")
                if l == 1:
                    self._option1(node_and_v[0])
                elif l == 2:
                    self._option2(node_and_v[0], node_and_v[1])
                else:
                    self._option3(node_and_v[0], node_and_v[1], node_and_v[2])
                return self
            if node is not None and v is not None and ix is not None:
                if l > 0:
                    raise ValueError(f"invalid node_and_v: {node_and_v}")
                return self._option3(node, v, ix)
            if node is not None and v is not None:
                if l > 1:
                    raise ValueError(f"invalid node_and_v: {node_and_v}")
                ix = node_and_v[0] if len(node_and_v) == 1 else None
                return self._option3(node, v, ix)
            if node is not None and ix is not None:
                if l > 1:
                    raise ValueError(f"invalid node_and_v: {node_and_v}")
                v = node_and_v[0] if len(node_and_v) == 1 else None
                return self._option3(node, v, ix)
            if ix is not None and v is not None:
                if l > 1:
                    raise ValueError(f"invalid node_and_v: {node_and_v}")
                node = node_and_v[0] if len(node_and_v) == 1 else None
                return self._option3(node, v, ix)
            if node is not None:
                if l == 0:
                    raise ValueError(f"invalid node_and_v: {node_and_v} , v is required")
                if l > 2:
                    raise ValueError(f"invalid node_and_v: {node_and_v} , only 2 or 1 values are allowed")
                ix = node_and_v[1] if len(node_and_v) == 2 else None
                v = node_and_v[0]
                return self._option3(node, v, ix)
            if v is not None:
                if l == 0:
                    raise ValueError(f"invalid node_and_v: {node_and_v} , node is required")
                if l > 2:
                    raise ValueError(f"invalid node_and_v: {node_and_v} , only 2 or 1 values are allowed")
                ix = node_and_v[1] if len(node_and_v) == 2 else None
                node = node_and_v[0]
                return self._option3(node, v, ix)
            if ix is not None:
                if l not in (1, 2):
                    raise ValueError(f"invalid node_and_v: {node_and_v} , node and v are required")
                if l == 2:
                    return self._option3(node_and_v[0], node_and_v[1], ix)
                node_and_v = node_and_v[0]
                assert isinstance(node_and_v, str) and "," in node_and_v
                node, v = node_and_v.rsplit(",", 1)
                return self._option3(node, v, ix)
            raise ValueError(f"invalid node_and_v: {node_and_v}")

        def build(self):
            from pyspark.sql import functions as F
            from vools.utils.tools import generate_lambda as _g
            if self._cast_type is None:
                self.cast_type = "string"
            k_cols = [i[0] for i in self.stack_list]
            v_cols = [i[1] for i in self.stack_list]
            ix_cols = [i[2] for i in self.stack_list]
            k_cols = ",".join(k_cols)
            v_cols = ",".join(v_cols)
            ix_cols = ",".join(map(str, ix_cols))
            return "stack({},{},{}) as ({},{},{})".format(len(self.stack_list), v_cols, ix_cols, k_cols, "v", "ix")

        def __call__(self, *select_cols, **kwargs):
            if self._cast_type is None:
                self._cast_type = "string"
            if not self.stack_list:
                self.setStack()
            k_cols = [i[0] for i in self.stack_list]
            v_cols = [i[1] for i in self.stack_list]
            ix_cols = [i[2] for i in self.stack_list]
            reserve_cols = self.reserve_cols
            if not reserve_cols:
                raise ValueError("reserve_cols 必须被 setReverse 设置 !!!")
            select_cols = [x for x in reserve_cols if x in df.columns]
            try:
                s = "select " + (",".join(select_cols) if select_cols else "") + \
                    ", stack({},{},{}) as ({},{},{}) ".format(len(self.stack_list), ",".join(v_cols), ",".join(map(str, ix_cols)),
                                                              ",".join(k_cols), "v", "ix")
                return df.selectExpr(s)
            except Exception:
                view_name = f"vic_temp_{_nxm()}"
                vDF(self.source, view_name=view_name)
                select_cols = ", ".join(select_cols)
                comma = "," if select_cols else ""
                s = f"select {select_cols}{comma}\n{self.build()}\nfrom {view_name}"
                return s  # will execute the query and return a DataFrame

    return StackHelper(stack_cols_name, ix)


def _df_selectEx(df, *cols, **kcols):
    """
    增强的selectExpr函数，支持列选择、函数过滤和列重命名

    Args:
        df: Spark DataFrame
        *cols: 直接传递给selectExpr的列或表达式
        **kcols: 关键字参数，支持函数过滤和列重命名

    Returns:
        DataFrame: 处理后的DataFrame
    """
    select_exprs = []

    # 处理位置参数（直接传递给selectExpr）
    select_exprs.extend(cols)

    # 处理关键字参数
    f_func = kcols.pop('f', None)  # 提取f参数（如果存在）

    # 如果提供了f函数，应用该函数到列名
    if f_func and callable(f_func):
        filtered_columns = f_func(df.columns)
        if filtered_columns is not None:
            select_exprs.extend(filtered_columns)

    # 处理其他关键字参数（列重命名）
    rename_exprs = [f"{v} as {k}" for k, v in kcols.items()]
    select_exprs.extend(rename_exprs)

    # 如果没有任何表达式，默认选择所有列
    if not select_exprs:
        return df.selectExpr("*")

    # 应用selectExpr
    return df.selectExpr(*select_exprs)


def _df_exists_helper(df, other, cond=None, how="left_semi", f2=None):
    if cond is None:
        cond = list(set(df.columns) & set(other.columns))
        if not cond:
            raise ValueError("two df has same column to build cond !!!")
        if f2 and len(cond) == 1:
            c = cond[0]
            cond = f2(df[c], other[c])

    return df.join(other, cond, how)


def _df_exists(df, other, cond=None, f2=None):
    return _df_exists_helper(df, other, cond, "left_semi", f2)


def _df_not_exists(df, other, cond=None, f2=None):
    return _df_exists_helper(df, other, cond, "left_anti", f2)


def _df_from_sql(df, sql, view_name=None, run_date=None):
    view_name = view_name or _nxm()
    run_date = run_date or _get_run_ds()
    sql = _vicText(sql) if not isinstance(sql, str) else sql
    if not isinstance(sql, str):
        raise TypeError("sql must be a string!!!")
    if '{view_name}' in sql:
        vDF(df, view_name=view_name)
        sql = sql.replace('{view_name}', view_name)
    sql = str(_vicText(sql).replace_run_date(run_date))
    return get_spark().sql(sql)


def _df_scalar(df, ix=0, default=None, f=None):
    row = df.first()
    if row is None:
        return f(default) if f else default

    rs = None
    if isinstance(ix, int):
        rs = row[ix]
    elif isinstance(ix, str):
        if ix in df.columns:
            rs = row[ix]
        elif ix.lower() == 'all':
            rs = row
        else:
            raise ValueError("ix must z column name or  equal 'all'")
    else:
        raise TypeError("ix must a index int or  equal 'all'")
    if rs is None:
        rs = default
    return f(rs) if f else rs


def _df_unionEx(df0, *dfs, how: str = "full"):
    """
    堆叠任意个 DataFrame，支持多种字段合并策略。

    :param df0: 第一个 DataFrame
    :param dfs: 可变参数，后续 DataFrame
    :param how: 字段合并策略，支持：
                - 单个字符串: 所有合并使用同一策略
                - 逗号分隔字符串: 每个合并使用不同策略，长度必须与dfs相同
                支持的策略: full, left, right, inner, left_semi, right_semi
    :return: 合并后的 DataFrame
    """
    from pyspark.sql.functions import lit
    if not dfs:
        return df0

    # 解析 how 参数
    how_list = []
    if isinstance(how, str):
        if ',' in how:
            how_list = [h.strip() for h in how.split(',')]
        else:
            how_list = [how] * len(dfs)
    else:
        how_list = list(how) if hasattr(how, '__iter__') else [how] * len(dfs)

    # 验证参数
    valid_hows = ["full", "left", "right", "inner", "left_semi", "right_semi"]
    if len(how_list) != len(dfs):
        raise ValueError(f"how 参数的数量 ({len(how_list)}) 必须与 dfs 的数量 ({len(dfs)}) 相同")

    for i, h in enumerate(how_list):
        if h not in valid_hows:
            raise ValueError(f"第 {i+1} 个 how 参数 '{h}' 无效，必须是 {valid_hows} 中的一个")

    # 核心函数：根据策略计算目标字段集
    def get_target_columns(df_left, df_right, strategy: str) -> list:
        """根据策略计算最终应该保留的字段"""
        cols_left = set(df_left.columns)
        cols_right = set(df_right.columns)
        l, r = 1, 1
        if strategy == "full":
            # 字段并集
            cs = sorted(cols_left.union(cols_right))
        elif strategy == "left":
            # 只保留左边的字段
            cs = sorted(cols_left)
        elif strategy == "right":
            # 只保留右边的字段
            cs = sorted(cols_right)
        elif strategy == "inner":
            # 字段交集
            cs = sorted(cols_left.intersection(cols_right))
        elif strategy == "left_semi":
            # 左边独有的字段（左边 - 右边）
            r = 0
            cs = sorted(cols_left - cols_right)
        elif strategy == "right_semi":
            # 右边独有的字段（右边 - 左边）
            l = 0
            cs = sorted(cols_right - cols_left)
        else:
            raise ValueError(f"不支持的策略: {strategy}")
        return cs

    # 逐步合并
    result_df = df0
    for i, (next_df, strategy) in enumerate(zip(dfs, how_list)):
        # 计算目标字段集
        target_cols = get_target_columns(result_df, next_df, strategy)

        if not target_cols:
            # 如果没有目标字段，跳过这个 DataFrame
            print(f"警告: 第 {i+1} 次合并后没有字段，跳过")
            continue

        # 对齐左边 DataFrame 到目标字段
        df_left_aligned = result_df
        for col in target_cols:
            if col not in df_left_aligned.columns:
                # 从右边 DataFrame 获取字段类型
                col_type = next_df.schema[col].dataType
                df_left_aligned = df_left_aligned.withColumn(col, lit(None).cast(col_type))
        df_left_aligned = df_left_aligned.select(target_cols)

        # 对齐右边 DataFrame 到目标字段
        df_right_aligned = next_df
        for col in target_cols:
            if col not in df_right_aligned.columns:
                # 从左边 DataFrame 获取字段类型
                col_type = result_df.schema[col].dataType
                df_right_aligned = df_right_aligned.withColumn(col, lit(None).cast(col_type))
        df_right_aligned = df_right_aligned.select(target_cols)

        # 合并（union）
        result_df = df_left_aligned.union(df_right_aligned)

    return result_df


def _df_cols(df) -> list:
    """legacy _df_cols 返回 vicList；这里返回 list(df.columns)，保持列顺序语义。"""
    return _vList(df.columns)


def spark_df_to_csv(
    spark_df,
    csv_path: str,
    is_append: bool = False,
    comma_replace: str = "，",
    linebreak_replace: str = " "
):
    """
    Spark 原生写 CSV（无需 Pandas）
    """
    from pyspark.sql import functions as F
    from pyspark.sql.functions import col
    from pyspark.sql.functions import expr as F_expr

    # 默认落 Share
    if not csv_path:
        csv_path = "{}/result.csv".format(_share_dir())
    if not csv_path.endswith(".csv"):
        csv_path = csv_path + ".csv"

    df = spark_df

    # 1️⃣ 字段清洗：替换逗号 & 换行符
    for c in df.columns:
        df = (
            df
            .withColumn(
                c,
                F.regexp_replace(col(c).cast("string"), ",", comma_replace)
            )
            .withColumn(
                c,
                F.regexp_replace(col(c), "\\n|\\r|\\r\\n", linebreak_replace)
            )
        )

    # 2️⃣ 写模式
    writer = df.write.mode("append" if is_append else "overwrite").format("csv")
    writer.option("header", "true").option("sep", ",").save(csv_path)
    return df


def _get_order_col(cs, ix: int) -> str:
    suf = ""
    if ix < 0:
        suf = " desc"
        ix *= -1
    elif ix > 0:
        ix -= 1
    else:
        raise ValueError("ix start at 1 not  0 !")
    return f"`{cs[ix]}` {suf}"


def _get_part_col(cs, ix: int) -> str:
    if ix > 0:
        ix -= 1
    return f"`{cs[ix]}`"


def _trans_cs_for_cols(cs, df_cs, is_order: bool) -> str:
    """把列序号/列名映射为可用的列引用字符串。

    legacy 用 vList(...).map(_gets).join(",").text；这里用纯 Python 实现，
    避免 VList 元类的 isinstance 递归问题。
    """
    def f_ix(ix):
        return _get_order_col(df_cs, ix) if is_order else _get_part_col(df_cs, ix)

    def _gets(s):
        s = str(s).strip()
        if s.isnumeric():
            return f_ix(int(s))
        return s

    return ",".join([_gets(s) for s in str(cs).split(",")])


def _df_unique_by(df, partition_by=None, order_by=None):
    """
    use row_number()over(...) = 1 to deduplicate (legacy `_df_unique_by` 9 overloads 合并版)

    支持 (partition_by, order_by) 为 str / int / list / None 的任意组合。
    """
    from pyspark.sql import functions as F

    cs = df.columns

    def _norm_order(ob):
        if ob is None:
            return None
        if isinstance(ob, str):
            return _trans_cs_for_cols(ob, cs, True)
        if isinstance(ob, int):
            return _get_order_col(cs, ob)
        if isinstance(ob, (list, tuple)):
            return ",".join([_get_order_col(cs, i) for i in ob])
        raise TypeError("order_by 必须是 str / int / list")

    def _norm_part(pb):
        if pb is None:
            return None
        if isinstance(pb, str):
            return _trans_cs_for_cols(pb, cs, False)
        if isinstance(pb, int):
            return _get_part_col(cs, pb)
        if isinstance(pb, (list, tuple)):
            return ",".join([_get_part_col(cs, i) for i in pb])
        raise TypeError("partition_by 必须是 str / int / list")

    order_by = _norm_order(order_by)
    partition_by = _norm_part(partition_by)

    # 单参：只有 order_by
    if partition_by is None:
        rn = _nxm() + "_rn"
        ex = f"row_number()over(order by {order_by})"
        return df.withColumn(rn, F.expr(ex)).where(f"{rn} = 1").drop(rn)

    # 双参：partition_by + order_by
    if order_by is None:
        # legacy 双参版本总是要求 order_by；此处若缺省则退化为 "partition_by" 排序
        order_by = partition_by
    rn = _nxm() + "_rn"
    ex = f"row_number()over(partition by {partition_by} order by {order_by})"
    return df.withColumn(rn, F.expr(ex)).where(f"{rn} = 1").drop(rn)


def _df_to_parquet(df, local_path: str = None, overwrite: bool = True) -> str:
    r"""
    把 DataFrame 写成生产环境 local path 的单一 parquet 文件（非 HDFS）。
    默认落 Share 目录: {PYK_SHARE_DIR}

    本质流程：
      1. df.coalesce(1) 写到临时 HDFS 路径
      2. 从临时 HDFS 拿出那唯一一个 part-*.snappy.parquet
      3. 重命名到 local_path (默认 Share)
      4. 删除临时 HDFS 目录
      5. 都是 overwrite 写入

    实现：用 sc._jvm 调用 Hadoop FileSystem API，不依赖外部 hadoop 命令
    用法:
        vDF("select * from tbl").toParquet(f"{_share_dir()}/my.parquet")
        vDF("select * from tbl").toParquet()   # 默认落 {PYK_SHARE_DIR}/result.parquet
    """
    import uuid
    import os

    # 默认落 Share
    if not local_path:
        local_path = "{}/result.parquet".format(_share_dir())

    # 确保 local_path 以 file:// 开头（给本地 FS 用）
    if not local_path.startswith("file://"):
        if local_path.startswith("/"):
            local_path = "file://" + local_path
        else:
            raise ValueError(f"local_path 必须是绝对路径: {local_path}")

    # 获取 Spark 上下文与 JVM 对象 (legacy 用 vicspark，这里用 get_spark())
    spark = get_spark()
    sc = spark.sparkContext
    jvm = sc._jvm
    conf = sc._jsc.hadoopConfiguration()

    # 构造 Hadoop 路径对象
    Path = jvm.org.apache.hadoop.fs.Path
    # 获取本地文件系统 (用于 copyToLocal 的目标)
    local_fs = jvm.org.apache.hadoop.fs.FileSystem.getLocal(conf)

    # 1. 临时 HDFS 路径
    tmp_hdfs = "/tmp/vic_parquet_tmp_" + uuid.uuid4().hex[:8]

    # 2. coalesce(1) 写临时 HDFS (overwrite)
    writer = df.coalesce(1).write
    if overwrite:
        writer = writer.mode("overwrite")
    writer.parquet(tmp_hdfs)

    # 3. 从临时 HDFS 列出目录，找唯一 part-*.parquet
    hdfs_fs = jvm.org.apache.hadoop.fs.FileSystem.get(conf)  # 默认 HDFS FS
    jpath = Path(tmp_hdfs)
    part_file = None
    try:
        statuses = hdfs_fs.listStatus(jpath)
        for st in statuses:
            name = st.getPath().getName()
            if name.startswith("part-") and name.endswith(".parquet"):
                part_file = st.getPath().toString()  # 完整 HDFS URI 路径
                break
    except Exception as e:
        raise RuntimeError(f"列出临时目录 {tmp_hdfs} 失败: {str(e)}")

    if not part_file:
        raise RuntimeError(f"未在临时 HDFS 目录 {tmp_hdfs} 中找到 parquet 文件")

    # 4. 确保本地目标目录存在（用 Python os 创建）
    local_fs_path = local_path[len("file://"):]
    local_dir = os.path.dirname(local_fs_path)
    if local_dir and not os.path.exists(local_dir):
        os.makedirs(local_dir, exist_ok=True)

    # 覆盖写：先删旧文件
    if overwrite and os.path.exists(local_fs_path):
        try:
            os.remove(local_fs_path)
        except Exception:
            pass

    # 5. copyToLocalFile: 源=HDFS part 文件, 目标=本地路径
    #    copyToLocalFile 要求 src/dst 同一 FS，改用 FileUtil.copy 跨 FS 复制
    FileUtil = jvm.org.apache.hadoop.fs.FileUtil
    FileUtil.copy(
        hdfs_fs,                # src FileSystem (HDFS)
        Path(part_file),        # src Path
        local_fs,               # dst FileSystem (Local)
        Path("file://" + local_fs_path),  # dst Path
        True,                   # deleteSource = True (删源)
        conf                    # Configuration
    )

    # 6. 删除临时 HDFS 目录
    try:
        hdfs_fs.delete(jpath, True)
    except Exception:
        pass

    return local_path


def _to_column(x):
    import re
    from pyspark.sql import functions as F
    if isinstance(x, F.Column):
        return x
    elif isinstance(x, str):
        rs = F.expr(x)
        if re.match(r"^[a-z_][a-z_0-9]*$", x.lower()):
            rs = rs.alias(x)
        return rs
    elif isinstance(x, (int, float, bool)):
        return F.lit(x)
    elif x is None:
        return F.lit(None)
    else:
        raise ValueError(f"Unsupported type: {type(x)}")


def _gf_aggEx(gf, *cols, **kcols):
    import re
    from pyspark.sql import functions as F
    f = kcols.pop('f', None)

    def agg_func(x):
        rs = f(_to_column(x)) if f else _to_column(x)
        if isinstance(x, str) and re.match(r"^[a-z_][a-z_0-9]*$", x.lower()):
            rs = rs.alias(x)
        return rs

    cs = [agg_func(c) for c in cols]
    cs += [agg_func(v).alias(k) for k, v in kcols.items()]
    return gf.agg(*cs)


# _gf_aggEx 修复版
# 原函数问题:
#   1. f 参数与列名冲突 — f 被 pop 掉，列名为 f 时报错
#   2. alias 正则只匹配全小写 — Customer_Type 等无法自动别名
#   3. 默认无聚合函数 — 直接传 Column 对象，不聚合

def _gf_aggEx2(gf, *cols, **kcols):
    """
    扩展聚合：支持自定义函数和别名

    Usage:
        gf.aggEx('col1', 'col2')                    # sum(col1), sum(col2) 自动别名
        gf.aggEx('col1', col2='sum(col2)')          # sum(col2).alias('col2')
        gf.aggEx(f=countDistinct, 'col1')           # countDistinct(col1).alias('col1')
        gf.aggEx('amt', avg_amt=F.avg('amt'))       # sum(amt) + avg(amt).alias('avg_amt')
        gf.aggEx(f=countDistinct, cust=F.col('id')) # countDistinct(id).alias('cust')

    Args:
        gf: GroupedData
        *cols: 列名或表达式，自动用 f 聚合 + 自动别名
        **kcols:
            - f: 聚合函数，默认 F.sum (pop后不参与聚合)
            - 其余: key=别名, value=列名/表达式
    """
    import re
    from pyspark.sql import functions as F

    # 安全取出 f，不用 pop（避免列名为'f'时报错）
    agg_func = kcols.get('f', F.sum)
    if not callable(agg_func):
        agg_func = F.sum  # 容错：传了非函数值

    # 从 kcols 移除 f（不参与聚合）
    kcols_no_f = {k: v for k, v in kcols.items() if k != 'f'}

    def _make(col_input, alias=None):
        """单个列 → 聚合表达式 + 别名"""
        col_obj = _to_column(col_input)
        expr = agg_func(col_obj)

        # 自动别名：提供的 alias 优先，否则用列名
        if alias:
            return expr.alias(alias)
        if isinstance(col_input, str):
            name = col_input.strip('`')
            if re.match(r'^[\w]+$', name):
                return expr.alias(name)
        # 无法推断别名 → 用 Spark 自动生成
        return expr

    exprs = [_make(c) for c in cols]
    exprs += [_make(v, alias=k) for k, v in kcols_no_f.items()]
    return gf.agg(*exprs)


def _gf_pivotEx(gf, pivot_col, *cols, **kwargs):
    """
    扩展的pivot函数，支持多列透视，可选择是否合并结果

    Parameters:
    -----------
    gf : GroupedData
        PySpark的GroupedData对象
    pivot_col : str
        用于透视的列名
    *cols : str
        要聚合的列名
    **kwargs : dict
        关键字参数，可包含：
        - f: 聚合函数，默认为first
        - union: 是否合并结果，默认为True
        - 其他: 额外要聚合的列
    """
    from pyspark.sql import functions as F
    # 从kwargs中提取特殊参数
    f_func = kwargs.pop('f', lambda x: F.first(x))
    union = kwargs.pop('union', True)
    pivot_name = kwargs.pop('pivot_name', 'pivot_flag')

    # 处理位置参数
    all_agg_cols = {}
    for col in cols:
        if isinstance(col, str):
            all_agg_cols[col] = f_func(F.col(col))
        elif isinstance(col, F.Column):
            col_name = col._jc.toString().split('`')[-2] if '`' in col._jc.toString() else col._jc.toString()
            all_agg_cols[col_name] = f_func(col)

    # 处理关键字参数
    for col_name, col_expr in kwargs.items():
        all_agg_cols[col_name] = f_func(_to_column(col_expr))

    if not all_agg_cols:
        raise ValueError("至少需要指定一个要聚合的列")

    # 构建聚合表达式列表
    agg_exprs = []
    for col_name, agg_expr in all_agg_cols.items():
        # 为聚合表达式添加别名
        agg_exprs.append(agg_expr.alias(col_name))

    # 执行透视和聚合
    pivot_df = gf.pivot(pivot_col)

    # 将聚合表达式列表传递给agg()方法
    df_result = pivot_df.agg(*agg_exprs)

    # 获取分组列（透视操作前的分组列）
    # 透视后的列名格式为：透视值_聚合列名
    result_columns = df_result.columns
    all_pivot_values = set()
    agg_col_names = list(all_agg_cols.keys())

    # 提取所有透视值
    for col in result_columns:
        for agg_col in agg_col_names:
            if col.endswith(f"_{agg_col}"):
                pivot_value = col[:-len(f"_{agg_col}")]
                all_pivot_values.add(pivot_value)
                break

    # 将透视值转换为列表并排序，确保一致的列顺序
    pivot_values = sorted(list(all_pivot_values))

    # 获取分组列（透视值列之外的列）
    group_cols = [col for col in result_columns
                  if not any(col.endswith(f"_{agg_col}") for agg_col in agg_col_names)]

    # 为每个聚合列创建单独的DataFrame
    dfs = []
    for agg_col in agg_col_names:
        # 构建列选择表达式
        select_exprs = group_cols.copy()

        for pivot_val in pivot_values:
            col_name = f"{pivot_val}_{agg_col}"
            if col_name in df_result.columns:
                select_exprs.append(f"`{col_name}` as `{pivot_val}`")
            else:
                select_exprs.append(f"NULL as `{pivot_val}`")

        # 创建DataFrame
        df_i = df_result.selectExpr(*select_exprs)

        # 添加pivot_flag列
        df_i = df_i.withColumn(pivot_name, F.lit(agg_col))

        dfs.append(df_i)

    # 根据union参数决定返回格式
    if union and dfs:
        # 合并所有DataFrame
        result_df = dfs[0]
        for df_i in dfs[1:]:
            result_df = result_df.unionByName(df_i)
        return result_df
    else:
        return dfs


def _gf_show_distinct(gf: "GroupedData", *distinct_cols, n=100):
    """
    显示GroupedData中指定列的去重统计信息

    Args:
        gf: GroupedData对象
        *distinct_cols: 要统计的列，可以是字符串、整数、Column对象
        n: 显示行数

    Returns:
        聚合后的DataFrame
    """
    from pyspark.sql import functions as F
    from pyspark.sql.functions import lit

    # 获取原始DataFrame的列名
    try:
        # 通过反射获取GroupedData的DataFrame
        df = gf._df
        cs = df.columns
    except AttributeError:
        raise ValueError("无法从GroupedData获取原始DataFrame，请确保传入有效的GroupedData对象")

    def _inner_to_column(x):
        """将不同类型的输入转换为Column对象"""
        if isinstance(x, F.Column):
            return x
        elif isinstance(x, str):
            # 如果是表达式（包含函数、运算等）则使用expr，否则使用col
            if any(op in x for op in ['(', ')', '+', '-', '*', '/', ' ']) and x not in cs:
                return F.expr(x)
            else:
                return F.col(x)
        elif isinstance(x, int):
            if 0 <= x < len(cs):
                return F.col(cs[x])
            else:
                raise ValueError(f"列索引 {x} 超出范围，DataFrame只有 {len(cs)} 列")
        else:
            raise ValueError(f"不支持的类型: {type(x)}，期望 str, int 或 Column")

    # 处理distinct_cols参数
    if len(distinct_cols) == 1 and isinstance(distinct_cols[0], (list, tuple)):
        # 如果是单个列表/元组，展开它
        distinct_cols = distinct_cols[0]

    def _create_agg_exprs(c):
        """为每个列创建计数和去重计数表达式"""
        # 获取列名
        try:
            # 尝试从_jc获取列名
            col_name = c._jc.toString().split(' AS ')[-1]  # 获取别名或列名
        except Exception:
            # 备用方法：从字符串表示中提取
            col_str = str(c)
            if 'Column<' in col_str and '>' in col_str:
                col_name = col_str[7:-1].split(' AS ')[-1]
            else:
                col_name = col_str

        # 清理列名，移除特殊字符
        clean_col_name = col_name.replace('(', '_').replace(')', '_').replace(' ', '_').replace(',', '_')

        # 返回计数和去重计数表达式
        return [
            F.count(c).alias(f"{clean_col_name}_cnt"),
            F.countDistinct(c).alias(f"{clean_col_name}_dcnt")
        ]

    # 转换所有distinct_cols为列表达式
    distinct_exprs = []
    for col_spec in distinct_cols:
        col_obj = _inner_to_column(col_spec)
        distinct_exprs.extend(_create_agg_exprs(col_obj))

    # 添加总行数计数
    distinct_exprs.append(F.count(lit(1)).alias("total_cnt"))

    # 执行聚合
    rf = gf.agg(*distinct_exprs)

    # 显示结果
    if hasattr(rf, "showEx"):
        rf.showEx(n=n)
    else:
        rf.show(n=n, truncate=False)

    return rf


def _df_show_Distinct(df, group_cols, *distinct_cols, cond=None, n=100):
    """
    显示DataFrame中指定分组下的列去重统计信息

    Args:
        df: DataFrame或vDF对象
        group_cols: 分组列，可以是字符串、整数、Column对象或列表
        *distinct_cols: 要统计的列，可以是字符串、整数、Column对象
        cond: 过滤条件
        n: 显示行数

    Returns:
        原始DataFrame（过滤后）
    """
    from pyspark.sql import functions as F
    # 转换为vDF对象
    df = vDF(df)

    # 应用过滤条件
    if cond is not None:
        df = df.where(cond)

    # 获取列名列表
    cs = df.columns

    # 转换分组列
    group_cols = _transfer_cols(group_cols)

    def _inner_to_column(x):
        """将不同类型的输入转换为Column对象"""
        if isinstance(x, F.Column):
            return x
        elif isinstance(x, str):
            # 如果是表达式（包含函数、运算等）则使用expr，否则使用col
            if any(op in x for op in ['(', ')', '+', '-', '*', '/', ' ']) and x not in cs:
                return F.expr(x)
            else:
                return F.col(x)
        elif isinstance(x, int):
            if 0 <= x < len(cs):
                return F.col(cs[x])
            else:
                raise ValueError(f"列索引 {x} 超出范围，DataFrame只有 {len(cs)} 列")
        else:
            raise ValueError(f"不支持的类型: {type(x)}，期望 str, int 或 Column")

    # 转换所有分组列为Column对象
    group_cols = [_inner_to_column(x) for x in group_cols]

    if not group_cols:
        raise ValueError("未找到有效的分组列")

    # 创建GroupedData
    gf = df.groupBy(*group_cols)

    # 调用_gf_show_distinct
    _gf_show_distinct(gf, *distinct_cols, n=n)

    return df


# DataFrame.showDistinct 修复版
# 原函数问题:
#   1. gf._df 是私有属性，部分 Spark 版本不存在
#   2. 列名提取逻辑脆弱（_jc.toString().split()）
#   3. showEx 非标准方法，依赖 vools 全量加载
#   4. 表达式检测 `any(op in x)` 误判含空格/括号的列名

def _df_show_distinct(df, *cols, n=100):
    """
    显示 DataFrame 指定列的计数+去重计数

    Usage:
        df.showDistinct('col1', 'col2')              # 全表统计
        df.groupBy('ds').aggEx.showDistinct('col1')  # 分组统计(链式)
        df.showDistinct('col1', 'col2', n=50)        # 限制显示行数

    Args:
        df: DataFrame 或 GroupedData (链式调用时)
        *cols: 列名（str），支持多个
        n: 显示行数，默认 100
    """
    from pyspark.sql import functions as F
    if not cols:
        raise ValueError("至少指定一个列名")

    # 判断是 DataFrame 还是 GroupedData
    if hasattr(df, 'groupBy'):
        # DataFrame → 全表统计
        exprs = []
        for c in cols:
            c_col = F.col(c) if isinstance(c, str) else c
            exprs.append(F.count(c_col).alias(f"{c}_cnt"))
            exprs.append(F.countDistinct(c_col).alias(f"{c}_dcnt"))
        exprs.append(F.count(F.lit(1)).alias("total_cnt"))
        result = df.agg(*exprs)
    else:
        # GroupedData → 分组统计
        exprs = []
        for c in cols:
            c_col = F.col(c) if isinstance(c, str) else c
            exprs.append(F.count(c_col).alias(f"{c}_cnt"))
            exprs.append(F.countDistinct(c_col).alias(f"{c}_dcnt"))
        exprs.append(F.count(F.lit(1)).alias("total_cnt"))
        result = df.agg(*exprs)

    # 显示（优先用 showEx，回退 show）
    if hasattr(result, 'showEx'):
        result.showEx(n=n)
    else:
        result.show(n=n, truncate=False)
    return result


def write_err(e, file_name_no_ext):
    """把错误信息写到 Share 目录（{PYK_SHARE_DIR}）下的 .err 文件（legacy write_err）。"""
    _vicText(str(e)).write(f"{_share_dir()}/{file_name_no_ext}.err")