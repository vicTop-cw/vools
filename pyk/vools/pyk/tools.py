"""vools.pyk.tools — legacy ``vicTools`` 的对应物。

legacy ``vools.py`` 里 ``vicTools`` 是 ``vicSql``/``vicTableInfo``/``vicCompare``/
``vicPostgreSupport`` 的**共同父类**，承载 42 个静态工具方法。新结构把这些
方法拆到了多个模块：

- 纯 Python 工具（trim / regexp_* / get_date_seq / ...）→ ``vools.utils.tools``
- pyspark 相关（toDF / stack / pivot / get_df / ...）→ ``vools.pyk.df`` / ``.postgre``

本模块把两者**重新聚合成一个类**，让 legacy 的 ``vicTools.xxx(...)`` 调用方式
继续可用，同时不复制任何实现（全部转发到唯一真源）。

用法::

    from vools.pyk.tools import vicTools
    vicTools.get_df("select 1")
    vicTools.trim("  x  ")
    vicTools.toDF([1, 2, 3])
"""

from __future__ import absolute_import

__all__ = ["vicTools"]


class vicTools(object):
    """legacy ``vicTools`` 聚合类。

    所有方法都是静态转发：纯 Python 部分转发到 ``vools.utils.tools``，
    pyspark 部分转发到 ``vools.pyk.df`` / ``vools.pyk.postgre``。
    这样既保留了 legacy 的调用入口，又保证实现只有一份（核心库是唯一真源）。
    """

    # ── 纯 Python 工具：转发到 vools.utils.tools ──
    # 这些在 vools.utils.tools 里是模块级函数，这里按 legacy 名字挂上。

    @staticmethod
    def trim(string, chars=None, left=True, right=True):
        """按侧裁剪空白/字符（legacy ``vicTools.trim``）。"""
        from vools.utils.tools import trim as _f
        return _f(string, chars, left, right)

    @staticmethod
    def regexp_findall(pattern, source_string, flags=0):
        from vools.utils.tools import regexp_findall as _f
        return _f(pattern, source_string, flags)

    @staticmethod
    def regexp_replace(pattern, source_string, replacement, flags=0, count=0):
        from vools.utils.tools import regexp_replace as _f
        return _f(pattern, source_string, replacement, flags, count)

    @staticmethod
    def regexp_like(pattern, source_string, flags=0, complete_matching=True):
        from vools.utils.tools import regexp_like as _f
        return _f(pattern, source_string, flags, complete_matching)

    @staticmethod
    def regexp_substr(pattern, source_string, flags=0, occurrence=0):
        from vools.utils.tools import regexp_substr as _f
        return _f(pattern, source_string, flags, occurrence)

    @staticmethod
    def regexp_count(pattern, source_string, flags=0):
        from vools.utils.tools import regexp_count as _f
        return _f(pattern, source_string, flags)

    @staticmethod
    def regexp_instr(pattern, source_string, flags=0, occurrence=0):
        from vools.utils.tools import regexp_instr as _f
        return _f(pattern, source_string, flags, occurrence)

    @staticmethod
    def get_char(string, rep='★'):
        from vools.utils.tools import get_char as _f
        return _f(string, rep)

    @staticmethod
    def check_no_overlap(strings):
        from vools.utils.tools import check_no_overlap as _f
        return _f(strings)

    @staticmethod
    def regexp_split(pattern, source_string, flags=0, rep='★'):
        from vools.utils.tools import regexp_split as _f
        return _f(pattern, source_string, flags, rep)

    @staticmethod
    def split(string, separator, rep='★'):
        from vools.utils.tools import split as _f
        return _f(string, separator, rep)

    @staticmethod
    def get_index_cols(cols, *ix):
        from vools.utils.tools import get_index_cols as _f
        return _f(cols, *ix)

    @staticmethod
    def static_vars(**kwargs):
        from vools.utils.tools import static_vars as _f
        return _f(**kwargs)

    @staticmethod
    def generate_lambda(ex, param_symbols="x"):
        from vools.utils.tools import generate_lambda as _f
        return _f(ex, param_symbols)

    @staticmethod
    def shift(iters, num=1, fill_value=None, cycle=False):
        from vools.utils.tools import shift as _f
        return _f(iters, num, fill_value, cycle)

    @staticmethod
    def get_py_fmt(fmt='yyyyMMdd'):
        from vools.utils.tools import get_py_fmt as _f
        return _f(fmt)

    @staticmethod
    def get_date_seq(nums=15, date_type='day', fmt='%m%d', run_ds=None, duo=True, reverse=True):
        from vools.utils.tools import get_date_seq as _f
        return _f(nums, date_type, fmt, run_ds, duo, reverse)

    @staticmethod
    def offset_date(run_date, offset_days, std=False):
        from vools.utils.tools import offset_date as _f
        return _f(run_date, offset_days, std)

    @staticmethod
    def transferCols(cols=None):
        from vools.utils.tools import transferCols as _f
        return _f(cols)

    @staticmethod
    def generate_random_field_name(word_count=3, max_length=8):
        from vools.utils.tools import generate_random_field_name as _f
        return _f(word_count, max_length)

    @staticmethod
    def getAllModules(search_path=None):
        from vools.utils.tools import getAllModules as _f
        return _f(search_path)

    @staticmethod
    def getAllPackagesWithVersion(returnDF=False):
        from vools.utils.tools import getAllPackagesWithVersion as _f
        return _f(returnDF)

    @staticmethod
    def toOrderedDict(x, fix="col_", ix=0):
        from vools.utils.tools import toOrderedDict as _f
        return _f(x, fix, ix)

    @staticmethod
    def build_text(raw_text_mode="", dct=None, lst=None, sep="\n ,",
                   check_key="item", max_iter_num=999):
        from vools.utils.tools import build_text as _f
        return _f(raw_text_mode, dct, lst, sep, check_key, max_iter_num)

    @staticmethod
    def get_json_keys(field_name):
        from vools.utils.tools import get_json_keys as _f
        return _f(field_name)

    @staticmethod
    def aggregate_json_keys(keys_list):
        from vools.utils.tools import aggregate_json_keys as _f
        return _f(keys_list)

    @staticmethod
    def calculate_runtime(func):
        from vools.utils.tools import calculate_runtime as _f
        return _f(func)

    @staticmethod
    def excel_column_to_number(col):
        from vools.utils.tools import excel_column_to_number as _f
        return _f(col)

    @staticmethod
    def excel_number_to_column(num):
        from vools.utils.tools import excel_number_to_column as _f
        return _f(num)

    @staticmethod
    def union_ordered_collection(original_list):
        from vools.utils.tools import union_ordered_collection as _f
        return _f(original_list)

    @staticmethod
    def _split(string, sep, rep='★'):
        """内部分割（legacy ``vicTools._split``）。"""
        from vools.utils.tools import _split as _f
        return _f(string, sep, rep)

    @staticmethod
    def transfer(func=None, w=None):
        """legacy ``vicTools.transfer`` 装饰器（返回值自动包装成 vic* 类型）。

        新结构里这个职责由核心库的 ``vools.decorators.rself`` 承担，
        此处保留同名入口以兼容 legacy 调用；行为委托给 rself。
        """
        from vools.decorators.rself import rself
        if func is None:
            return lambda f: rself(f)
        return rself(func)

    # ── pyspark 相关：转发到 pyk 各模块 ──

    @staticmethod
    def get_df(df_or_sql):
        """把多种来源统一成 pyspark DataFrame（legacy ``vicTools.get_df``）。

        支持 DataFrame / SQL 字符串 / vicSql / vicTableInfo / vicDataFrame /
        vicList / vicText。
        """
        from pyspark.sql import DataFrame

        if isinstance(df_or_sql, DataFrame):
            return df_or_sql

        from .df import vicDataFrame, vDF
        if isinstance(df_or_sql, vicDataFrame):
            return df_or_sql.df

        from .postgre import vicSql
        if isinstance(df_or_sql, vicSql):
            return df_or_sql.run()

        from .tb import vicTableInfo
        if isinstance(df_or_sql, vicTableInfo):
            return df_or_sql.query()

        # str 子类要在 str 之前判（vicText/vicList 都是 str/list 子类）
        from vools.data.vtext import VText
        from vools.data.vlist import VList
        if isinstance(df_or_sql, (VText, VList)):
            return vDF(df_or_sql)

        if isinstance(df_or_sql, str):
            ti = vicTableInfo(df_or_sql)
            if ti.isExists:
                return ti.query()
            from .core import get_spark
            return get_spark().sql(df_or_sql)

        raise TypeError(
            "typeError :df_or_sql must sql string or DataFrame, got %r"
            % type(df_or_sql).__name__)

    @staticmethod
    def toDF(x, cols=None, useSparkSql=False, usepos=False, pos_name="pos_index"):
        """多种来源转 DataFrame（legacy ``vicTools.toDF``）。"""
        from .df import vDF
        return vDF(x, cols=cols, pos_name=pos_name if usepos else None)

    @staticmethod
    def toDFWithOneColumn(x, col=None, useSparkSql=False, usepos=False,
                          pos_name="pos_index", n=1):
        """单列转 DataFrame（legacy ``vicTools.toDFWithOneColumn``）。"""
        from .df import vDF
        return vDF(x, cols=col, pos_name=pos_name if usepos else None)

    @staticmethod
    def stack(df_or_sql, cols, stack_cols2="stack_flag,stack_value",
              cast_type="", return_df=True):
        """宽表转长表（legacy ``vicTools.stack``）。"""
        from .df import stack as _f
        from .tools import vicTools as _self
        return _f(_self.get_df(df_or_sql), cols, stack_cols2, cast_type, return_df)

    @staticmethod
    def pivot(df_or_sql, pivot_col, value_col, groupNames=None,
              newColsName=None, agg_func=None):
        """单列透视（legacy ``vicTools.pivot``）。"""
        from .df import pivot as _f
        from .tools import vicTools as _self
        return _f(_self.get_df(df_or_sql), pivot_col, value_col,
                  groupNames, newColsName, agg_func)

    @staticmethod
    def pivots(df_or_sql, pivot_col, value_cols, groupNames=None,
               newColsName=None, agg_func=None, pivot_flag="pivot_flag"):
        """多列透视（legacy ``vicTools.pivots``）。"""
        from .df import pivots as _f
        from .tools import vicTools as _self
        return _f(_self.get_df(df_or_sql), pivot_col, value_cols,
                  groupNames, newColsName, agg_func, pivot_flag)

    @staticmethod
    def trans_df(df, whereCond="", groupCols=None, pivotCol="", aggCols=None,
                 selectCols=None, orderCols=None, limit=None):
        """综合转换（legacy ``vicTools.trans_df``）。"""
        from .text import trans_df as _f
        return _f(df, whereCond, groupCols, pivotCol, aggCols,
                  selectCols, orderCols, limit)

    @staticmethod
    def chunk_df(df, n=25, show_result=True):
        """按行数切块（legacy ``vicTools.chunk_df``）。

        注意：pyk 的 ``df.chunk_df`` 第二参数是 chunk_size（行数），
        legacy 的 n 语义一致；show_result 仅用于兼容签名。
        """
        from .df import chunk_df as _f
        return _f(df, n)

    @staticmethod
    def get_insert_sql_for_postgre(df, target_table_in_post, if_print=True):
        """生成 PostgreSQL INSERT SQL（legacy ``vicTools.get_insert_sql_for_postgre``）。"""
        from .postgre import get_insert_sql_for_postgre as _f
        sql = _f(df, target_table_in_post)
        if if_print:
            print(sql)
        return sql

    @staticmethod
    def generate_postgres_sql(df, table_name, if_print=True):
        """生成 PostgreSQL 建表+插入 SQL（legacy ``vicTools.generate_postgres_sql``）。"""
        from .postgre import get_create_table_sql, get_insert_sql
        result = {
            "create": get_create_table_sql(df, table_name),
            "insert": get_insert_sql(df, table_name),
        }
        if if_print:
            print(result["create"])
            print(result["insert"])
        return result
