"""
vools.spark - Spark 集成子包

提供 Spark UDF 注册、Spark SQL 连接等功能。
子模块：
    udf        — 日期 / JSON / 数组 Spark UDF 与统一注册入口
    config     — Spark 配置管理（pyk 兼容层）

用法：
    from vools.spark import register_all_udfs
    spark = ...  # SparkSession
    register_all_udfs(spark)
"""

__all__ = [
    "udf",
    "register_all_udfs",
]


def register_all_udfs(spark):
    """一次性注册所有内置 UDF 到 SparkSession。

    包含：日期 UDF（vDate / days_gap / weeks_gap / months_gap /
    get_recently_days / get_recently_weeks / get_recently_months /
    get_dates / get_week / get_month）、JSON UDF（extract_json_keys）、
    数组 UDF（array_sum）。

    参数:
        spark: pyspark.sql.SparkSession 实例
    """
    from .udf import register_all_udfs as _register
    _register(spark)
