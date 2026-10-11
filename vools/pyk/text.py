"""
pyk.text - vicText (VText) 的 pyspark 相关扩展

提供:
- vicText 扩展类 (挂 DataFrame 转换等方法)
- vicQuery: SQL 查询字符串包装类
- toDF / trans_df / _transfer
- build_text / generate_lambda
"""

from __future__ import absolute_import

__all__ = [
    "vicText",
    "vicQuery",
    "toDF",
    "trans_df",
    "_transfer",
    "build_text",
    "generate_lambda",
]

import os
from .df import vDF


# ============================================================
# vicText 扩展: 在 vools.data.vtext.VText 上附加 pyspark 方法
# ============================================================
class vicText(str):
    """VText 的 pyspark 兼容别名。

    纯 Python 环境建议直接用 vools.data.vtext.VText；
    本类只在需要调用 DataFrame 转换等 pyspark 扩展时使用。

    注意: 继承关系与 legacy vicText 保持一致 (str 子类)。
    """

    def __new__(cls, text="", *args, **kwargs):
        return super().__new__(cls, text)

    def __init__(self, text="", *args, **kwargs):
        pass

    # ---- pyspark 相关 ----
    def toDF(self, *args, **kwargs):
        """把 SQL 字符串转 DataFrame。

        用法:
            vicText("select * from db.t").toDF()
        """
        return vDF(str(self), *args, **kwargs)

    def run(self, func=print, *args, **kwargs):
        """执行副作用操作。"""
        func(str(self), *args, **kwargs)
        return self


# ============================================================

    def formatEx(self, **kwargs):
        """把 SQL 里的 ${run_date} / ${run_date_std±N} 等占位符替换为实际日期。

        兼容 legacy vicText.formatEx：
        ``vicText(sql).formatEx(run_date='2026-10-10')``
        """
        from ..datetime.dates_format import EnhancedDateFormatter
        from ..data.vtext import VText
        run_date = kwargs.pop('run_date', None)
        txt = self.replace("${run_", "{run_")
        vt = VText(txt)
        return EnhancedDateFormatter(vt, run_date).set(**kwargs).format()


# ============================================================
# vicQuery: SQL 查询包装
# ============================================================
class vicQuery(vicText):
    """SQL 查询字符串包装类。

    提供:
    - toDF(): 执行查询返回 DataFrame
    - run_date 变量替换
    """

    def __new__(cls, text="", run_date=None, *args, **kwargs):
        return super().__new__(cls, text)

    def __init__(self, text="", run_date=None, *args, **kwargs):
        self.run_date = run_date

    def toDF(self, *args, **kwargs):
        """执行 SQL 返回 DataFrame。"""
        return vDF(str(self), *args, **kwargs)


# ============================================================
# 函数
# ============================================================
def toDF(source, cols=None, pos_name=None, source_type="hive", view_name="", cache=False):
    """转 DataFrame。"""
    return vDF(source, cols=cols, pos_name=pos_name, source_type=source_type,
               view_name=view_name, cache=cache)


def trans_df(df, *args, **kwargs):
    """DataFrame 转换 (别名)。"""
    return df


def _transfer(source, cols=None, pos_name=None, source_type="hive"):
    """内部转换, 兼容 legacy _transfer。"""
    return vDF(source, cols=cols, pos_name=pos_name, source_type=source_type)


def build_text(raw_text_mode="", dct=None, lst=None, sep="\n ,",
               check_key="item", max_iter_num=999, prefix="", suffix=""):
    """把 dict/list 递归拼成 SQL 文本。

    参数:
        raw_text_mode: 原始模板字符串, 其中 {item} 会被替换
        dct:           字典, 形如 {'a': 1, 'b': 2}
        lst:           列表, 形如 ['a', 'b']
        sep:           分隔符
        check_key:     递归时查找的键名
        max_iter_num:  最大迭代层数
        prefix/suffix: 前后缀
    Returns:
        str: 构建好的文本
    """

    def _flatten(obj, depth=0):
        if depth > max_iter_num:
            return []
        if isinstance(obj, dict):
            out = []
            for k, v in obj.items():
                if isinstance(v, (dict, list, tuple)):
                    out.extend(_flatten(v, depth + 1))
                else:
                    out.append(str(v))
            return out
        elif isinstance(obj, (list, tuple)):
            out = []
            for v in obj:
                out.extend(_flatten(v, depth + 1))
            return out
        else:
            return [str(obj)]

    items = _flatten(lst if lst is not None else dct)
    sep_str = sep if isinstance(sep, str) else str(sep)
    return prefix + sep_str.join(items) + suffix


def generate_lambda(expr, param_symbols="x"):
    """从表达式生成 lambda 函数。

    参数:
        expr:           表达式, 如 "x + 1" 或 "x, y -> x + y"
        param_symbols:  单参变量名
    Returns:
        callable
    """
    if "->" in expr:
        params, body = expr.split("->", 1)
        return eval("lambda {}: {}".format(params.strip(), body.strip()), {})
    return eval("lambda {}: {}".format(param_symbols, expr.strip()), {})
# ============================================================
# _transfer (以 legacy vools.py L5800-L5833 为准)
# ============================================================
def _transfer(source, cols=None, pos_name=None, source_type="hive"):
    """把多种源类型统一转成 Spark DataFrame (以 legacy 为准)。

    参数:
        source:      DataFrame / pd.DataFrame / vicDataFrame / str(SQL) / vicSql / vicTableInfo / vicPostgreSupport / dict
        cols:        重命名列 (str/list/dict); None 不重命名
        pos_name:    加行号列 (如 "pos"); None 不加
        source_type: "hive" / "spark" / "postgre" / "postgresql"
    Returns:
        DataFrame
    """
    from pyspark.sql import DataFrame
    from pyspark.sql import Row
    from pyspark.sql.functions import row_number, lit
    from pyspark.sql.window import Window

    from .core import get_spark
    from .df import vDF, vicDataFrame
    from .postgre import vicPostgreSupport
    from .tb import vicTableInfo
    from .postgre import re_names

    spark = get_spark()
    if isinstance(source, DataFrame):
        df = source
    elif isinstance(source, pd.DataFrame):
        df = spark.createDataFrame(source)
    elif isinstance(source, vicDataFrame):
        df = source.df
    elif isinstance(source, str):
        source_type = (source_type or "hive").lower().strip()
        p1 = _regexp_like(r"^[a-z][a-z_0-9]+\.[a-z_0-9]+$", source.lower())
        p2 = _regexp_like(r"^[a-z][a-z_0-9]+$", source.lower())
        p = p1 or p2
        if source_type in ("hive", "", "spark"):
            df = vicTableInfo(source).query("") if p else spark.sql(source)
        elif source_type in ("post", "postgresql", "postgre"):
            df = vicPostgreSupport().query("select * from {}".format(source) if p else source)
        else:
            raise ValueError("source_type is illegality !!!")
    elif isinstance(source, _real_vic_sql):
        df = spark.sql(source.sql)
    elif isinstance(source, (vicTableInfo, vicPostgreSupport)):
        df = source.query("")
    elif isinstance(source, dict):
        df = spark.createDataFrame([Row(key=k, value=v) for k, v in source.items()])
    else:
        df = vDF(source)
    if pos_name:
        pos_name = str(pos_name)[:99]
        df = df.coalesce(1).withColumn(pos_name, row_number().over(Window.orderBy(lit(1))))
    return re_names(df, cols) if cols else df


def _regexp_like(pattern, text, flags=0):
    """正则匹配 (兼容 legacy vicTools.regexp_like)。"""
    import re
    return re.search(pattern, str(text), flags) is not None


class _vicSql(object):
    """vicSql 占位类 (legacy: vicSql 包装 SQL 字符串); 仅在 postgre.vicSql 不可用时兜底。"""

    def __init__(self, sql=""):
        self.sql = sql



