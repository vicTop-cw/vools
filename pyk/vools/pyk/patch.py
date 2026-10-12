"""
pyk.patch - 把 pyk 的扩展方法挂到原生 pyspark 类型上

支持挂载目标:
- pyspark.sql.DataFrame
- pyspark.sql.SparkSession
- pyspark.sql.Column (待扩展)

用法:
    from vools.pyk import install_patch
    install_patch()
    df.unique_by(...)  # DataFrame 上现在有了 pyk 的 unique_by
"""

from __future__ import absolute_import

__all__ = ["install_patch", "PATCHED"]

# 记录已 patch 的方法名, 幂等去重用
PATCHED = set()


def install_patch():
    """幂等地把 pyk 扩展方法挂到 pyspark 原生类型。

    Returns:
        None
    """
    try:
        from pyspark.sql import DataFrame, SparkSession
    except ImportError as e:
        raise ImportError("pyk.patch 需要 pyspark: {}".format(e))

    _patch_dataframe(DataFrame)
    _patch_spark_session(SparkSession)
    return None


def _patch_dataframe(cls):
    """挂方法到 DataFrame。"""
    from . import df as _df

    mappings = {
        # (方法名, 函数)
        "unique_by": _df.unique_by,
        "showEx": _df.show_ex,
        "selectEx": _df.select_ex,
        "groupingSets": _df.grouping_sets,
        "orderCols": _df.order_cols,
        "toList": _df.to_list,
        "chunk_df": _df.chunk_df,
        "insert": _df.insert,
        "push": _df.push,
        "to_excel": _df.to_excel,
        "to_parquet": _df.to_parquet,
        "with_flag_field": _df.with_flag_field,
        "get_missing_dates": _df.get_missing_dates,
    }
    for name, func in mappings.items():
        if name not in PATCHED and not hasattr(cls, name):
            setattr(cls, name, func)
            PATCHED.add(name)


def _patch_spark_session(cls):
    """挂方法到 SparkSession。"""
    from . import core as _core

    mappings = {
        "get_run_ds": _core.get_run_ds,
        "show_": _core.show_,
    }
    for name, func in mappings.items():
        if name not in PATCHED and not hasattr(cls, name):
            setattr(cls, name, func)
            PATCHED.add(name)