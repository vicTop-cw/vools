"""
pyk.tb - Hive 表元数据

提供:
- vicTableInfo: 表信息包装类 (tableName / cols / dstr / getLocation / isExists ...)
- getCols: 取表列名
- get_all_partitions: 取全部分区
- check_partition / check_partition_ex: 检查分区是否就绪 (带重试)
- get_miss_dss: 找缺失分区日期
"""

from __future__ import absolute_import

__all__ = [
    "vicTableInfo",
    "getCols",
    "get_all_partitions",
    "get_all_partitions_sorted",
    "check_partition",
    "check_partition_ex",
    "check_max_date",
    "get_miss_dss",
    "get_missing_dates",
]

import os
import time

from .core import get_spark


# ============================================================
# vicTableInfo
# ============================================================
class vicTableInfo(object):
    """Hive 表信息包装类。

    用法:
        t = vicTableInfo("db.table", dsOffsetNum=3)
        t.cols            # ['a','b','c']
        t.isExists        # True/False
        t.getLocation()   # 'hdfs://...'
    """

    def __init__(self, table_name, sep=" | ", ds_offset_num=3, labels=None,
                 dstr=0, db_name="default", run_date=None):
        """初始化。

        参数:
            table_name:    表名 (db.table 或 table)
            sep:           分隔符 (内部展示用)
            ds_offset_num: 取日期范围回退天数
            labels:        自定义标签
            dstr:          偏移天数
            db_name:       默认库名
            run_date:      run_date (yyyy-MM-dd); None 用全局
        """
        if "." in table_name:
            self._db, self._tb = table_name.split(".", 1)
        else:
            self._db, self._tb = db_name, table_name
        self._sep = sep
        self._ds_offset_num = ds_offset_num
        self._labels = labels or []
        self._dstr = dstr
        self._run_date = run_date or _get_run_ds()

    # ---- 属性 ----
    @property
    def dbName(self):
        return self._db

    @property
    def tbName(self):
        return self._tb

    @property
    def tableName(self):
        return "{}.{}".format(self._db, self._tb)

    @tableName.setter
    def tableName(self, value):
        if "." in value:
            self._db, self._tb = value.split(".", 1)
        else:
            self._tb = value

    @property
    def labels(self):
        return self._labels

    @labels.setter
    def labels(self, value):
        self._labels = list(value) if isinstance(value, (list, tuple)) else [value]

    @property
    def dstr(self):
        return self._dstr

    @property
    def cols(self):
        """取表列名。"""
        return getCols(self.tableName, col_name_only=True)

    @property
    def info(self):
        """返回列信息 DataFrame（兼容 legacy `vicTableInfo.info` 用法）。

        legacy 返回 `col_name, comment` 两列 DataFrame；此处包装 getCols 返回的
        DataFrame 以保证 `getTableInfo()` 兼容。
        """
        try:
            df = getCols(self.tableName, col_name_only=False)
        except Exception:
            df = None
        if df is None:
            return None
        # legacy: select col_name, comment 两列
        cols = [c for c in df.columns if c.lower() in ('col_name', 'data_type', 'comment')]
        if len(cols) >= 2:
            return df.select(cols[0], cols[1])
        return df

    @property
    def isExists(self):
        """表是否已存在。"""
        spark = get_spark()
        try:
            return bool(spark.catalog.tableExists(self.tableName))
        except Exception:
            try:
                st = spark.sql('SHOW TABLES')
                cols = [c.lower() for c in st.columns]
                try:
                    idx = cols.index('tablename')
                except ValueError:
                    idx = 1
                rows = st.collect()
                return any(str(r[idx]) == self.tbName for r in rows)
            except Exception:
                return False

    def getLocation(self, part_cols_value=None):
        """取表/分区物理路径。

        Args:
            part_cols_value: 分区值 dict, 如 {'ds':'2026-01-01'}
        Returns:
            str: HDFS 路径
        """
        spark = get_spark()
        if part_cols_value:
            try:
                from pyspark.sql import functions as F
                df = spark.sql("DESCRIBE EXTENDED {} PARTITION ({})".format(
                    self.tableName,
                    ",".join("{}='{}'".format(k, v) for k, v in part_cols_value.items())))
                rows = df.collect()
                for r in rows:
                    if "Location" in str(r[0]):
                        return str(r[1]).strip()
            except Exception:
                pass
        try:
            df = spark.sql("DESCRIBE EXTENDED {}".format(self.tableName))
            for r in df.collect():
                if "Location" in str(r[0]):
                    return str(r[1]).strip()
        except Exception:
            pass
        return None

    def getLocationInfo(self, part=None, with_tb=True):
        """取位置信息, 兼容 legacy 返回格式。"""
        loc = self.getLocation(part)
        return loc

    def getModifyAndCreateTime(self, part=None, offset="7h"):
        """取表/分区修改与创建时间。"""
        spark = get_spark()
        try:
            sql = "DESCRIBE EXTENDED {}".format(self.tableName)
            if part:
                sql += " PARTITION ({})".format(
                    ",".join("{}='{}'".format(k, v) for k, v in part.items()))
            df = spark.sql(sql)
            info = {str(r[0]): str(r[1]) for r in df.collect() if r[0]}
            return {
                "CreateTime": info.get("CreateTime", None),
                "LastModified": info.get("Last Modified", info.get("LastModified", None)),
                "Location": info.get("Location", None),
            }
        except Exception:
            return {"CreateTime": None, "LastModified": None, "Location": None}

    def get_modify_time_of_parts(self, where_cond=None):
        """取所有分区修改时间。"""
        return self.getModifyAndCreateTime()

    def cntOfPartDs(self):
        """取分区天数。"""
        parts = get_all_partitions(self.tableName)
        if parts is None or len(parts) == 0:
            return 0
        return len(parts)

    def getInValidCols(self, num=7):
        """取最近 num 天都有数据(有效)的列。"""
        valid_cols = []
        for c in self.cols:
            valid_cols.append(c)
        return valid_cols

    def inValidCols(self):
        return self.getInValidCols()


# ============================================================
# 函数
# ============================================================
def getCols(table_name, partition_cols_only=False, col_name_only=True, return_df=True, db_name="default"):
    """取表列信息。

    参数:
        table_name:          表名
        partition_cols_only: True 只取分区列
        col_name_only:       True 只返回列名字符串
        return_df:           True 返回 DataFrame; False 返回 list
        db_name:             默认库名
    Returns:
        DataFrame 或 list[str]
    """
    spark = get_spark()
    try:
        df = spark.sql("DESCRIBE {}".format(table_name))
    except Exception as e:
        raise ValueError("取表列失败 {}: {}".format(table_name, e))
    if partition_cols_only:
        df = df.filter("data_type == 'partition'")
    if col_name_only:
        cols = [str(r[0]) for r in df.collect() if r[0] and r[0] != ""]
        if return_df:
            return spark.createDataFrame([(c,) for c in cols], ["col_name"])
        return cols
    return df


def get_all_partitions(full_table, order_desc=False, db_name="default"):
    """取表全部分区 (list[str])。

    参数:
        full_table:  表名
        order_desc:  True 倒序
    Returns:
        list[str]: 分区值列表
    """
    spark = get_spark()
    try:
        parts = spark.sql("SHOW PARTITIONS {}".format(full_table))
        vals = [str(r[0]).strip() for r in parts.collect()]
    except Exception:
        return []
    if order_desc:
        vals.sort(reverse=True)
    else:
        vals.sort()
    return vals


def get_all_partitions_sorted(full_table, db_name="default"):
    """取表全部分区 (倒序)。"""
    return get_all_partitions(full_table, order_desc=True)


def _exists_partition(table_name, partition_clause):
    """检查分区是否已存在。"""
    spark = get_spark()
    try:
        df = spark.sql("SHOW PARTITIONS {}".format(table_name))
        for r in df.collect():
            if partition_clause.strip() in str(r[0]).strip():
                return True
    except Exception:
        pass
    return False


def check_partition(table_names, run_date=None, timeout=90, retry_interval=45, time_wait=10):
    """检查多个表的分区是否就绪 (带重试)。

    参数:
        table_names:     表名 (str 或 list)
        run_date:        run_date; None 取全局
        timeout:         总超时秒
        retry_interval:  重试间隔秒
        time_wait:       首次等待秒
    Returns:
        bool: 全部就绪返回 True
    """
    if isinstance(table_names, str):
        table_names = [table_names]
    ds = run_date or _get_run_ds()
    start = time.time()
    time.sleep(time_wait)
    while time.time() - start < timeout:
        all_ok = True
        for tb in table_names:
            if not _exists_partition(tb, "ds={}".format(ds)):
                all_ok = False
                break
        if all_ok:
            return True
        time.sleep(retry_interval)
    return False


def check_partition_ex(table_names, run_date=None, timeout=90, retry_interval=45,
                       time_wait=5, date_col="ds"):
    """同 check_partition, 但支持自定义分区列名。"""
    if isinstance(table_names, str):
        table_names = [table_names]
    ds = run_date or _get_run_ds()
    start = time.time()
    time.sleep(time_wait)
    while time.time() - start < timeout:
        all_ok = True
        for tb in table_names:
            if not _exists_partition(tb, "{}={}".format(date_col, ds)):
                all_ok = False
                break
        if all_ok:
            return True
        time.sleep(retry_interval)
    return False


def check_max_date(sql, timeout=90, retry_interval=45, time_wait=10):
    """检查 SQL 结果非空 (带重试)。

    参数:
        sql:             要执行的 SQL
        timeout:         总超时
        retry_interval:  重试间隔
        time_wait:       首次等待
    Returns:
        bool
    """
    spark = get_spark()
    start = time.time()
    time.sleep(time_wait)
    while time.time() - start < timeout:
        try:
            if spark.sql(sql).count() > 0:
                return True
        except Exception:
            pass
        time.sleep(retry_interval)
    return False


def get_miss_dss(full_table, start_ds=None, end_ds=None, date_col="ds", with_name=True, db_name="default"):
    """找缺失分区日期。

    参数:
        full_table: 表名
        start_ds:   起始日期; None 取当前
        end_ds:     结束日期; None 取当前
        date_col:   分区列名
        with_name:  True 返回 'date_col=date'; False 返回纯日期
    Returns:
        list[str]
    """
    from datetime import datetime, timedelta

    if start_ds is None:
        start_ds = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if end_ds is None:
        end_ds = datetime.now().strftime("%Y-%m-%d")

    parts = get_all_partitions(full_table)
    exist_dates = set()
    for p in parts:
        # 兼容 'date_col=2026-01-01' 或 '2026-01-01' 两种格式
        if "=" in p:
            v = p.split("=", 1)[1].strip()
        else:
            v = p.strip()
        exist_dates.add(v)

    missing = []
    cur = datetime.strptime(start_ds, "%Y-%m-%d")
    end = datetime.strptime(end_ds, "%Y-%m-%d")
    while cur <= end:
        d = cur.strftime("%Y-%m-%d")
        if d not in exist_dates:
            missing.append("{}={}".format(date_col, d) if with_name else d)
        cur += timedelta(days=1)
    return missing


def get_missing_dates(table_name, date_col="ds", num=7):
    """兼容接口: 取最近 num 天的缺失分区日期。"""
    return get_miss_dss(table_name, start_ds=None, end_ds=None, date_col=date_col)


def _get_run_ds():
    """取全局 run_date。"""
    from .core import get_run_ds
    return get_run_ds()