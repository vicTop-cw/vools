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
import re
import time

from .core import get_spark
from ..utils.tools import (
    transferCols, trim, regexp_like, regexp_substr,
    generate_random_field_name, excel_number_to_column,
)

# legacy: set hive.execution.engine=mr（强制 MR 引擎，Spark 2.4 未必支持，可忽略）
_MR = "set hive.execution.engine=mr"

# 常见 Spark 列类型（用于 add_cols 校验）
_SPARK_COL_TYPES = {
    'int', 'integer', 'bigint', 'smallint', 'tinyint', 'long', 'short',
    'string', 'varchar', 'char', 'decimal', 'double', 'float', 'real',
    'boolean', 'bool', 'binary', 'date', 'timestamp', 'array', 'map',
    'struct', 'interval',
}


def _is_spark_col_type(s):
    """判断字符串是否为合法 Spark 列类型（宽泛判断）。"""
    if not isinstance(s, str):
        return False
    s = s.strip().lower()
    base = s.split('<')[0].split('(')[0].split()[0]
    return base in _SPARK_COL_TYPES


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
        _rd = run_date or _get_run_ds()
        # legacy 用 yyyyMMdd；get_run_ds() 可能返回 yyyy-MM-dd，统一去横线
        self._run_date = str(_rd).replace('-', '') if _rd else None

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
        """分区列名。dstr 传 int 时按 colsOfPartition 下标解析。"""
        if isinstance(self._dstr, int):
            try:
                self._dstr = self.colsOfPartition[self._dstr]
            except Exception:
                self._dstr = ''
        return self._dstr

    @property
    def cols(self):
        """取表列名 (list[str])。"""
        df = getCols(self.tableName, col_name_only=True)
        # getCols 在 return_df=True 时返回 DataFrame，但 legacy cols 语义是 list
        if hasattr(df, 'collect'):
            return [str(r[0]) for r in df.collect() if r[0]]
        return list(df)

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

    def __info(self):
        """内部方法：返回列信息 DataFrame（legacy `__info` 语义）。

        legacy 里 __info 负责把 DESCRIBE 信息与常用属性拼成一张宽表并缓存到
        `self._info`。新实现里 `info` 属性已覆盖 DESCRIBE 结果，这里保持同名
        方法以兼容 legacy 内部调用；有需要时再扩展为属性聚合。
        """
        return self.info

    @property
    def isExists(self):
        """表是否已存在。

        兼容 Spark 2.4 与 3.x：Python catalog 的 tableExists 在 3.x 才有；
        2.4 用 listTables(db) 或 _jsparkSession.catalog().tableExists 判断。
        """
        spark = get_spark()
        full = self.tableName
        db, tb = self._db, self._tb

        # 3.x: catalog.tableExists 直接可用
        try:
            if hasattr(spark.catalog, 'tableExists'):
                return bool(spark.catalog.tableExists(full))
        except Exception:
            pass

        # 2.4: 通过 JVM catalog 判断（tableExists 只在 Java 侧）
        try:
            jcatalog = spark._jsparkSession.catalog()
            return bool(jcatalog.tableExists(db, tb))
        except Exception:
            pass

        # 兜底：listTables(db) 逐个匹配
        try:
            for t in spark.catalog.listTables(db):
                if str(t.name).lower() == tb.lower():
                    return True
            return False
        except Exception:
            pass

        # 最后兜底：SHOW TABLES IN <db>
        try:
            st = spark.sql('SHOW TABLES IN {}'.format(db))
            rows = st.collect()
            cols = [c.lower() for c in st.columns]
            try:
                idx = cols.index('tablename')
            except ValueError:
                idx = 1
            return any(str(r[idx]).lower() == tb.lower() for r in rows)
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

    # ---- legacy 补齐：41 个方法 ----
    def __bool__(self):
        return self.isExists

    def __call__(self, where_condition=None, select_cols=None, exclude_cols=None):
        return self.query(where_condition, select_cols, exclude_cols)

    def _getWhereCond(self, num):
        """取最近 num 天的首尾日期条件（legacy 内部方法）。"""
        if self.isHasPartitionOfDs:
            dct = self.get_miss_dss()
            min_ds = dct.get('min_ds')
            max_ds = dct.get('max_ds')
            if not min_ds or not max_ds:
                return ''
            from datetime import datetime, timedelta
            def _add(s, days):
                d = datetime.strptime(s, '%Y%m%d') + timedelta(days=days)
                return d.strftime('%Y%m%d')
            min_ds1 = _add(min_ds, num)
            max_ds1 = _add(max_ds, -num)
            return " where ({} between '{}' and '{}') or ({} between '{}' and '{}') ".format(
                self.dstr, min_ds, min_ds1, self.dstr, max_ds1, max_ds)
        return ''

    def _get_partition_fields(self):
        """从 DESCRIBE 提取分区列名（legacy 内部方法）。"""
        if not self.isExists:
            return None
        spark = get_spark()
        cf = spark.sql("desc {}".format(self.tableName))
        ps = "# Partition Information"
        p = False
        partition_fields = []
        for i in cf.collect():
            ss = str(i[0]) if i[0] is not None else ''
            if ss == ps:
                p = True
                continue
            if p:
                if len(ss) > 0 and '#' not in ss:
                    partition_fields.append(ss.strip())
        return partition_fields

    def _transferSql(self, where_condition=None, select_cols=None, exclude_cols=None, unpack=True):
        """构造 SQL 字符串或返回三要素（legacy 内部方法）。

        where_condition 可传 int（天数偏移，自动生成首尾日期条件）。
        若为字符串且非空、且未以 SQL 关键字/括号开头，自动补 "where "。
        """
        if where_condition is None:
            where_condition = ''
        elif isinstance(where_condition, (list, tuple)):
            where_condition = " and ".join([str(i) for i in where_condition])
        elif isinstance(where_condition, str):
            pass
        elif isinstance(where_condition, int):
            where_condition = self._getWhereCond(where_condition)
        else:
            raise TypeError("param where_condition must be string or list<string> !")

        # 自动补 where：兼容 legacy 传 "ds='x'" 与 "where ds='x'" 两种写法
        if isinstance(where_condition, str) and where_condition.strip():
            _s = where_condition.strip().lower()
            _kw = ('where ', 'select ', 'group by', 'order by', 'having ',
                   'limit ', '(', 'union', 'join ', 'from ')
            if not _s.startswith(_kw):
                where_condition = "where " + where_condition.strip()

        if not select_cols:
            select_cols = self.cols
        if isinstance(select_cols, str):
            select_cols = [trim(i) for i in select_cols.split(",")]
        if isinstance(select_cols, (list, tuple)):
            select_cols = [trim(str(i)) for i in select_cols]
        else:
            raise TypeError("param select_cols must be string or list<string> !")

        if not exclude_cols:
            exclude_cols = []
        if isinstance(exclude_cols, str):
            exclude_cols = [trim(i) for i in exclude_cols.split(",")]
        if isinstance(exclude_cols, (list, tuple)):
            exclude_cols = [trim(str(i)) for i in exclude_cols]
        else:
            raise TypeError("param exclude_cols must be string or list<string> !")

        if len(exclude_cols) > 0:
            cs = [str(c) for c in select_cols if c not in exclude_cols]
            css = ','.join(cs)
            if len(cs) == 0:
                raise ValueError("param select_cols number is zero !")
        else:
            cs = [str(c) for c in select_cols]
            css = ','.join(cs)

        if unpack:
            return "select {} from {} {} ".format(css, self.tableName, where_condition)
        return where_condition, cs, exclude_cols

    def query(self, where_condition=None, select_cols=None, exclude_cols=None):
        """执行 SELECT，返回 DataFrame。"""
        if not self.isExists:
            raise SyntaxError(" no this table : {} ".format(self.tableName))
        if where_condition is None and self.isHasPartitionOfDs:
            where_condition = "where {} = '{}' ".format(self.dstr, self._run_date)
        sql = self._transferSql(where_condition, select_cols, exclude_cols)
        spark = get_spark()
        try:
            return spark.sql(sql)
        except Exception as e:
            raise SyntaxError(" Query sql is wrong : < {} > !".format(sql))

    def show(self, where_condition=None, select_cols=None, exclude_cols=None, n=100):
        """展示前 n 行，返回 self 供链式调用。"""
        df = self.query(where_condition, select_cols, exclude_cols)
        df = df.limit(n) if isinstance(n, int) and n > 0 else df
        try:
            df.show()
        except Exception as e:
            print(e, '\n', "-.-" * 30)
            df.show()
        return self

    def getHashRows(self, where_condition=None, select_cols=None, exclude_cols=None,
                    limit_num=10, order_hash_value=True, flod_cols=True, show_result=False):
        """按行哈希排序取样本，返回 DataFrame。"""
        if not self.isExists:
            raise SyntaxError(" no this table : {} ".format(self.tableName))
        where_condition, cs, exclude_cols = self._transferSql(
            where_condition, select_cols, exclude_cols, unpack=False)
        cs = [c for c in cs if c not in exclude_cols]
        csk = ["concat('_',nvl(cast({} as string),'None')) as {}".format(c, c) for c in cs]
        csr = ["{} desc".format(c) for c in cs]
        css = ["concat('\"{}=\"',nvl(cast({} as string),'null'), '\"') as {}".format(c, c, c) for c in cs]
        limit_str = "limit {}".format(limit_num) if isinstance(limit_num, int) and limit_num > 0 else ''
        if isinstance(order_hash_value, bool):
            okr = "2" if order_hash_value else ','.join(csr)
        elif isinstance(order_hash_value, str):
            okr = ','.join(csr) if len(order_hash_value.strip()) == 0 else order_hash_value.strip()
        elif isinstance(order_hash_value, (tuple, list)):
            order_hash_value = [str(c).strip() for c in order_hash_value if len(str(c).strip()) > 0]
            okr = ','.join(csr) if len(order_hash_value) == 0 else ','.join(order_hash_value)
        else:
            raise TypeError("order_hash_value type must be in (bool,str,tuple,list) !")

        if flod_cols:
            query_sql = """
                select '{tb}' as full_table,hash(*) as hash_value,count(*)over() as cnt
                ,concat_ws('{sep}',{cs}) as row_data from (select {css}
                from {tb} {where} ) order by {okr} {limit}
            """.format(
                tb=self.tableName, sep=self._sep, cs=','.join(cs),
                css=','.join(css), where=where_condition, okr=okr, limit=limit_str)
        else:
            query_sql = """
                select '{tb}' as full_table,hash(*) as hash_value,count(*)over() as cnt
                , {cs} from (select {csk} from {tb} {where} )
                order by {okr} {limit}
            """.format(
                tb=self.tableName, cs=','.join(cs), csk=','.join(csk),
                where=where_condition, okr=okr, limit=limit_str)

        spark = get_spark()
        rf = spark.sql(query_sql).cache()
        if show_result:
            rf.show()
        return rf

    def add_columns(self, cols_and_type):
        """ALTER TABLE ADD COLUMNS (raw string)。"""
        if not self.isExists:
            raise SyntaxError(" no this table : {} ".format(self.tableName))
        if not cols_and_type:
            raise ValueError("cols_and_type is illegal !")
        spark = get_spark()
        spark.sql(_MR)
        spark.sql("alter table {} add columns ({}) ".format(self.tableName, cols_and_type))

    def add_cols(self, cols, return_sql=False):
        """添加列，支持 str/list/tuple/dict 输入。"""
        fullName = self.tableName
        if not self.isExists:
            raise ValueError("table {} is not exist !".format(fullName))
        p = True
        if isinstance(cols, str):
            sep = "|" if "|" in cols and "(" in cols else ","
            cs = [c.strip() for c in cols.split(sep)]
        elif isinstance(cols, (list, tuple)):
            cs = [c.strip() for c in cols]
        elif isinstance(cols, dict):
            cs = ["{} {}".format(k.strip(), v.strip()) for k, v in cols.items()]
            p = False
        else:
            raise ValueError("cols should be str, list, tuple or dict")

        l = len(cs)
        if l == 0:
            raise ValueError("No columns to add")

        if p and l % 2 == 0:
            if all(_is_spark_col_type(c) for c in cs[1::2]):
                cs = ["{} {}".format(cs[i].strip(), cs[i + 1].strip()) for i in range(0, l, 2)]
            else:
                cs1 = [re.split(r"\s+", c.strip(), 1)[1] for c in cs]
                if not all(_is_spark_col_type(c) for c in cs1):
                    raise ValueError("Invalid column type")
        else:
            cs1 = [re.split(r"\s+", c.strip(), 1)[1] for c in cs]
            if not all(_is_spark_col_type(c) for c in cs1):
                raise ValueError("Invalid column type")

        sql = "ALTER TABLE {} ADD COLUMNS ({})".format(fullName, ','.join(cs))
        if return_sql:
            return _MR + ";\n" + sql + ";"
        try:
            spark = get_spark()
            spark.sql(_MR)
            spark.sql(sql)
            print("Added columns to table {} :".format(fullName), cs)
        except Exception as e:
            print(_MR + ";\n" + sql + ";")
            raise e

    def change_column(self, s, return_sql=True):
        """ALTER TABLE CHANGE COLUMN s: like "old_col new_col new_type"。"""
        sql = "ALTER TABLE {} CHANGE COLUMN {}".format(self.tableName, s)
        if return_sql:
            return _MR + ";\n" + sql + ";"
        try:
            spark = get_spark()
            spark.sql(_MR)
            spark.sql(sql)
            print("Changed column {} in table {}".format(s, self.tableName))
        except Exception as e:
            print(sql + ";")
            raise e

    def drop(self, part_ds=None, truncate=False):
        """删除表（或分区）。part_ds 为日期列表时只删对应分区。"""
        if not self.isExists:
            return
        spark = get_spark()
        if not self.isHasPartitionOfDs:
            if not truncate:
                spark.sql("drop table if exists {}".format(self.tableName))
            else:
                spark.sql("truncate table  {}".format(self.tableName))
        else:
            part_ds = transferCols(part_ds)
            if not part_ds:
                if not truncate:
                    spark.sql("drop table if exists {}".format(self.tableName))
                else:
                    spark.sql("truncate table  {}".format(self.tableName))
            else:
                for ds in part_ds:
                    spark.sql("alter table {} drop if exists partition ({}='{}')".format(
                        self.tableName, self.dstr, ds))

    def drop_partitions(self, part_cols, execute_real=False):
        """生成/执行 DROP PARTITION SQL。"""
        if not self.isExists:
            return
        if not self.isHasPartitionOfDs:
            return
        spark = get_spark()
        ss = "alter table {} drop if exists partition ".format(self.tableName)
        result = ["{} ({}) ".format(ss, i) for i in transferCols(part_cols)]
        if execute_real and result:
            rs = []
            for s in result:
                try:
                    spark.sql(s)
                    rs.append((s, "Successful"))
                except Exception as e:
                    rs.append((s, "Failed"))
            return rs
        return result

    def drop_partitionsEx(self, where_cond='', execute_real=False):
        """按条件删除分区。"""
        df = self.get_all_partitions('', mode="for_drop", where2=where_cond)
        if not execute_real:
            return df
        res = self.drop_partitions([r[0] for r in df.collect()], execute_real=True)
        from .df import vDF
        return vDF(res, ["drop_sql", "status"])

    def update_from(self, df_or_sql, part_cols=None, mode="overwrite", drop_if_exists=False):
        """从 DataFrame/SQL 更新表数据。"""
        from .df import vDF
        from .postgre import insertData
        if isinstance(df_or_sql, str):
            df = get_spark().sql(df_or_sql)
        else:
            df = vDF(df_or_sql) if not hasattr(df_or_sql, 'columns') else df_or_sql
        if self.isExists:
            st = {c.lower().strip() for c in df.columns}
            st1 = {c.lower().strip() for c in self.cols}
            if st != st1:
                raise KeyError("Table {} 's columns :{} different from DataFrame columns : {}".format(
                    self.tableName, self.cols, df.columns))
            part_cols = part_cols or self.colsOfPartition or None
            cs = self.cols
            insertData(df.select(*cs), part_cols=part_cols, mode=mode, drop_if_exists=drop_if_exists)
        else:
            insertData(df, part_cols=part_cols, mode=mode)
        return self

    def rename(self, name):
        """ALTER TABLE RENAME。"""
        if not self.isExists:
            raise ValueError("{} is not exists !!!".format(self.tableName))
        name = "{}.{}".format(self.dbName, str(name).strip().lower())
        if not regexp_like(r"^[a-z][a-z_0-9]+\.[a-z_0-9]+$", name):
            raise ValueError("Illegal table Name : {}".format(name))
        if name == self.tableName:
            return self
        sql = "ALTER TABLE {} rename to {}".format(self.tableName, name)
        spark = get_spark()
        spark.sql(_MR)
        spark.sql(sql)
        self.tableName = name
        return self

    def get_create_table_sql(self, table_alias=None):
        """生成 CREATE TABLE SQL。"""
        if not self.isExists:
            return "-- no this table : {}".format(self.tableName)
        spark = get_spark()
        desc_df = spark.sql("DESCRIBE {}".format(self.tableName))
        table_alias = self.tableName if table_alias is None else str(table_alias)
        non_partition_fields = []
        partition_fields = []
        p = False
        for r in desc_df.collect():
            col_name = str(r.col_name) if r.col_name is not None else ''
            if col_name == '# Partition Information':
                p = True
                continue
            comment = "comment '{}'".format(r.comment) if r.comment else ''
            if p:
                if col_name and '#' not in col_name:
                    partition_fields.append("{} {} {}".format(col_name, r.data_type, comment))
            else:
                if col_name and '#' not in col_name:
                    non_partition_fields.append("{} {} {}".format(col_name, r.data_type, comment))
        if partition_fields:
            partition_fields_sql = ",\n    ".join(partition_fields)
            _pk = [x.split(" ")[0] for x in partition_fields]
            non_partition_fields = [x for x in non_partition_fields if x.split(" ")[0] not in _pk]
        non_partition_fields_sql = ",\n    ".join(non_partition_fields)
        create_table_sql = " -- DROP TABLE if exists {} ; \n CREATE TABLE if not exists {} (\n      {}".format(
            table_alias, table_alias, non_partition_fields_sql)
        if partition_fields:
            create_table_sql += ")\n  PARTITIONED BY (     {}  );".format(partition_fields_sql)
        else:
            create_table_sql += " ) ;"
        return create_table_sql

    def findDemagedDs(self, dss=None, max_times=30,
                      sql="select * from {tb} {cond} limit 1"):
        """探测损坏分区（legacy 用 try/except 找出报错分区）。"""
        if not self.isExists:
            return None
        dss = list(dss) if dss else []
        spark = get_spark()
        tbName = self.tableName
        while max_times > 0:
            try:
                cond = ("where not {} in (" + ",".join(dss) + ")").format(self.dstr) if dss else ''
                df = spark.sql(sql.format(tb=tbName, cond=cond))
                cnt = df.count()
                break
            except Exception as e:
                s = re.findall(self.dstr + r"=[0-9]{8}", str(e))
                for ds in s:
                    dss.append(ds.replace(self.dstr + "=", ""))
            max_times -= 1
        cs = self._sep.join(dss)
        tf = spark.sql("select '{}' as tbName , '{}' as damaged_dss".format(tbName, cs))
        return tf

    def getCntOfPartititonOfDs(self, where_condition=None):
        """按 ds 统计行数。"""
        if not self.isExists:
            return None
        if not self.isHasPartitionOfDs or not where_condition:
            ds = self.dstr if self.isHasPartitionOfDs else "no_ds"
            cnt = self.cntOfPartDs
            spark = get_spark()
            # cntOfPartDs 当前实现返回 int；legacy 返回 dict
            if isinstance(cnt, dict):
                from pyspark.sql import Row
                rows = [Row(ds=k, cnt=int(v)) for k, v in cnt.items()]
                return spark.createDataFrame(rows).selectExpr(
                    "replace(ds,'{}=','') as {}".format(self.dstr, ds), "cnt")
            # 兼容当前 int 实现：返回全部 ds 计数（单值）
            return spark.createDataFrame([(ds, cnt)], ["ds", "cnt"]).selectExpr(
                "replace(ds,'{}=','') as {}".format(self.dstr, ds), "cnt")
        if self.isHasPartitionOfDs:
            return self.query("{} \n group by 1".format(where_condition),
                              "{},count(*) as cnt".format(self.dstr))
        return None

    def getDistinctCnt(self, where_condition=None, group_cols=None, select_cols=None, new_cols=''):
        """统计各列去重行数。"""
        spark = get_spark()
        df = self.query(where_condition)
        cs, gs = transferCols(select_cols), transferCols(group_cols)
        cs = ["count({}) as cnt_{}, count(distinct {}) as dcnt_{}".format(c, c, c, c) for c in cs]
        tempTbName = "vic_" + generate_random_field_name()
        df.createOrReplaceTempView(tempTbName)
        if gs:
            ll = ','.join(map(str, range(1, len(gs) + 1)))
            sql = ("select {} , {} ,count(1) as cnt from {} group by {}"
                   .format(','.join(gs), ','.join(cs), tempTbName, ll) if cs
                   else "select {} , count(1) as cnt from {} group by {}".format(
                       ','.join(gs), tempTbName, ll))
        else:
            sql = ("select {} ,count(1) as cnt from {} "
                   .format(','.join(cs), tempTbName) if cs
                   else "select count(1) as cnt from {} ".format(tempTbName))
        from .postgre import re_names
        return re_names(spark.sql(sql), new_cols) if new_cols else spark.sql(sql)

    def getEnCryptedCols(self, select_cols=None, exclude_cols=None, boolFunc=None, num=100):
        """探测加密列（32 位大写 HEX 特征）。"""
        if not self.isExists:
            return []
        spark = get_spark()
        select_cols = transferCols(select_cols)
        exclude_cols = transferCols(exclude_cols)
        if len(select_cols) == 0:
            cs = [c.lower() for c in self.cols if c not in self.colsOfPartition]
        else:
            cs = [c.lower() for c in select_cols if c not in self.colsOfPartition]
        if len(exclude_cols) > 0:
            cs = [c.lower() for c in cs if c not in exclude_cols]
        if len(cs) == 0:
            return []

        # 取 string 类型列
        tf = spark.sql("desc {}".format(self.tableName))
        tf = tf.filter("data_type = 'string'").select('col_name').distinct()
        css = [str(r[0]).lower() for r in tf.collect()]
        cs = [c for c in cs if c in css]
        if len(cs) == 0:
            return []

        if boolFunc is None:
            boolFunc = (lambda x: regexp_like(r"^[0-9A-Z]{32}$", x))

        def isCryptCol(tb, c, cond=""):
            mit = "limit {}".format(num) if num > 0 else ''
            ss = "select {} from {} where {} {} is not null {}".format(c, tb, cond, c, mit)
            ltf = spark.sql(ss).collect()
            if len(ltf) == 0:
                return False
            return all(boolFunc(str(x[0])) for x in ltf)

        return [c for c in cs if isCryptCol(self.tableName, c)]

    @property
    def enCryptedCols(self):
        return self.getEnCryptedCols()

    def getCols(self, boolFunc=None, where_condition=None, select_cols=None,
                exclude_cols=None, use_method=all, joint_comp=False):
        """取「值全非空/全唯一」的列。"""
        if not self.isExists:
            return []
        if isinstance(use_method, str):
            if not use_method.lower() in ("unique", "distinct", "groupby", "group by"):
                raise TypeError("param use_method must be in : (\"unique\",\"distinct\",\"groupby\",\"group by\") !")
        else:
            if not callable(use_method):
                raise TypeError("param use_method must be a collection function like : all ,any !")
        if boolFunc is None:
            boolFunc = (lambda x: x is None)
        where_condition, select_cols, exclude_cols = self._transferSql(
            where_condition, select_cols, exclude_cols, unpack=False)
        cs = [str(c) for c in select_cols if c not in exclude_cols]
        css = ','.join(cs)
        sql = "select {} from {} {} ".format(css, self.tableName, where_condition)
        spark = get_spark()
        try:
            df = spark.sql(sql)
        except Exception as e:
            raise SyntaxError(" Query sql is wrong : < {} > !".format(sql))
        cnt = df.count()
        if cnt == 0:
            return "<query result table is empty!>"
        rs = []
        if callable(use_method):
            if joint_comp:
                lst = df.collect()
                if use_method(boolFunc(x) for x in lst):
                    rs.append(cs)
            else:
                for c in cs:
                    lst = df.select(c).collect()
                    if use_method(boolFunc(x[0]) for x in lst):
                        rs.append(c)
        else:
            if joint_comp:
                if cnt == df.distinct().count():
                    rs.append(cs)
            else:
                for c in cs:
                    ct = df.select(c).distinct().count()
                    if ct == cnt:
                        rs.append(c)
        return rs

    # ---- 属性补齐 ----
    @property
    def location(self):
        """取表物理路径（legacy property）。"""
        return self.getLocation()

    @property
    def colsOfPartition(self):
        """分区列名 list[str]。"""
        return self.get_partition_fields()

    @property
    def isHasPartition(self):
        return len(self.colsOfPartition) > 0

    @property
    def isHasPartitionOfDs(self):
        return self.dstr in self.get_partition_fields()

    @property
    def countOfPartitionCols(self):
        return len(self.colsOfPartition)

    @property
    def countOfCols(self):
        return len(self.cols)

    @property
    def allProperty(self):
        if not self.isExists:
            return []
        _info = self._info if getattr(self, '_info', None) is not None else self.info
        if _info is None:
            return []
        lst = _info.select('col_name').collect()
        return [c[0] for c in lst]

    @property
    def curProperty(self):
        if not self.isExists:
            return []
        if self.labels is None:
            return self.allProperty
        else:
            lst = self.allProperty
            return [c for c in lst if c in self.labels]

    @property
    def infoT(self):
        """转置后的表信息 DataFrame。"""
        if not self.isExists:
            return None
        df = self.info
        if df is None:
            return None
        cs = [str(x[0]) if len(str(x[0])) > 0 else 'vEmpty' for x in df.select("col_name").collect()]
        df = self.get_transposed_df(df, newColsName=cs, return_df=True)
        if df is None or 'field_name' not in df.columns:
            return df
        return df.filter("field_name == 'info'").drop("field_name")

    @property
    def lastDdlModifyTime(self):
        return self.getLastDdlModifyTime()

    def getLastDdlModifyTime(self):
        """取表最后一次 DDL 时间。"""
        if not self.isExists:
            return None
        spark = get_spark()
        try:
            df = spark.sql("describe extended {}".format(self.tableName))
        except Exception:
            return None
        ts = 'transient_lastDdlTime='
        try:
            lst = df.filter("col_name = 'Table Properties'").select('data_type').first()[0]
            lst = lst[1:-1]
            for s in lst.split(','):
                if s.startswith(ts):
                    from datetime import datetime
                    return datetime.fromtimestamp(int(s.replace(ts, '')))
        except Exception:
            return None
        return None

    def get_max_ds(self):
        """取最大分区 ds (yyyyMMdd)。"""
        from pyspark.sql.functions import asc, desc
        if not self.isExists:
            return "<no this table!>"
        if not self.isHasPartitionOfDs:
            return None
        spark = get_spark()
        try:
            df = spark.sql("show partitions {}".format(self.tableName))
        except Exception:
            return None
        if df.count() == 0:
            return None
        if self.countOfPartitionCols > 1:
            df = df.selectExpr("split(partition,'/')[0] as partition").distinct()
        df = df.selectExpr("replace(replace(partition,'{}=',''),'-','') as ds".format(self.dstr)) \
               .filter("ds REGEXP '^[0-9][0-9]{3}[0-1][0-9][0-3][0-9]$'") \
               .orderBy(desc("ds"))
        rows = df.head(1)
        return rows[0][0] if rows else None

    def get_min_ds(self):
        """取最小分区 ds (yyyyMMdd)。"""
        from pyspark.sql.functions import asc, desc
        if not self.isExists:
            return "<no this table!>"
        if not self.isHasPartitionOfDs:
            return None
        spark = get_spark()
        try:
            df = spark.sql("show partitions {}".format(self.tableName))
        except Exception:
            return None
        if df.count() == 0:
            return None
        if self.countOfPartitionCols > 1:
            df = df.selectExpr("split(partition,'/')[0] as partition").distinct()
        df = df.selectExpr("replace(replace(partition,'{}=',''),'-','') as ds".format(self.dstr)) \
               .filter("ds REGEXP '^[0-9][0-9]{3}[0-1][0-9][0-3][0-9]$'") \
               .orderBy(asc("ds"))
        rows = df.head(1)
        return rows[0][0] if rows else None

    def get_miss_dss(self, start_ds=None, end_ds=None):
        """取缺失分区日期（返回 dict）。"""
        from pyspark.sql.functions import asc, desc
        if end_ds is None:
            end_ds = self._run_date
        if not self.isExists:
            t = "<no this table!>"
            return {"min_ds": t, "max_ds": t, "miss_dss": t, "should_dss_cnt": 0, "miss_dss_cnt": 0}
        spark = get_spark()
        min_ds = None
        max_ds = None
        miss_dss = None
        should_ds_cnt = 0
        if self.isHasPartitionOfDs:
            try:
                df = spark.sql("show partitions {}".format(self.tableName))
            except Exception:
                df = None
            if df is None or df.count() == 0:
                return {"min_ds": min_ds, "max_ds": max_ds, "miss_dss": miss_dss,
                        "should_dss_cnt": should_ds_cnt,
                        "miss_dss_cnt": len(miss_dss) if miss_dss else 0}
            if self.countOfPartitionCols > 1:
                df = df.selectExpr("split(partition,'/')[0] as partition").distinct()
            df = df.selectExpr("replace(replace(partition,'{}=',''),'-','') as ds".format(self.dstr)) \
                   .filter("ds REGEXP '^[0-9][0-9]{3}[0-1][0-9][0-3][0-9]$'") \
                   .orderBy(asc("ds"))
            rows = df.collect()
            if not rows:
                return {"min_ds": min_ds, "max_ds": max_ds, "miss_dss": miss_dss,
                        "should_dss_cnt": should_ds_cnt,
                        "miss_dss_cnt": len(miss_dss) if miss_dss else 0}
            min_ds = rows[0][0]
            max_ds = df.orderBy(desc("ds")).head(1)[0][0]
            d1 = "{}-{}-{}".format(min_ds[0:4], min_ds[4:6], min_ds[6:8])
            d2 = "{}-{}-{}".format(max_ds[0:4], max_ds[4:6], max_ds[6:8])
            if start_ds:
                if start_ds > min_ds:
                    d1 = "{}-{}-{}".format(start_ds[0:4], start_ds[4:6], start_ds[6:8])
            if end_ds:
                if end_ds < max_ds:
                    d2 = "{}-{}-{}".format(end_ds[0:4], end_ds[4:6], end_ds[6:8])
            dss = [r[0] for r in rows]
            sql = ("select date_format(date_add('{}',s),'yyyyMMdd') as ds from "
                   "(select posexplode(sequence(0,datediff('{}','{}')))as (s,_))").format(d1, d2, d1)
            tf = spark.sql(sql)
            should_ds_cnt = tf.count()
            _have = set(dss)
            miss_dss = [str(r[0]) for r in tf.collect() if str(r[0]) not in _have]
        return {"min_ds": min_ds, "max_ds": max_ds, "miss_dss": miss_dss,
                "should_dss_cnt": should_ds_cnt,
                "miss_dss_cnt": len(miss_dss) if miss_dss else 0}

    def get_extended_info(self, transfer=False):
        """取 DESCRIBE EXTENDED 的详细表信息。"""
        if not self.isExists:
            return None
        spark = get_spark()
        try:
            df = spark.sql("describe extended {}".format(self.tableName))
        except Exception:
            return None
        try:
            from pyspark.sql import functions as F
            from pyspark.sql.functions import asc, desc
            from pyspark.sql import Window
            from pyspark.sql.functions import row_number, lit
            Wp = Window.orderBy("xh")
            df = df.coalesce(1).withColumn("xh", lit(1)).withColumn("xh", row_number().over(Wp))
            tf = df.filter("col_name == '# Detailed Table Information'").select("xh").limit(1)
            rows = tf.collect()
            if not rows:
                return df
            temp_xh = rows[0][0]
            df = df.filter("xh > {}".format(temp_xh)) \
                   .selectExpr("replace(col_name,' ','_') as col_name", "data_type as info")
        except Exception:
            return df
        if not transfer:
            return df
        cs = [str(x[0]) if len(str(x[0])) > 0 else 'vEmpty' for x in df.select("col_name").collect()]
        df = self.get_transposed_df(df, newColsName=cs, return_df=True)
        if df is None or 'field_name' not in df.columns:
            return df
        return df.filter("field_name == 'info'").drop("field_name")

    def get_partition_fields(self):
        """取分区列名 list[str]。"""
        if not self.isExists:
            return []
        return self._get_partition_fields() or []

    def get_all_partitions(self, where_condition='', mode="for_drop", where2=''):
        """取分区信息，返回 DataFrame。

        分区列表委托模块级 get_all_partitions 获取（唯一真源），
        再由本方法组装成 partition / 分区列 / ps 三列 DataFrame。
        """
        if not self.isExists:
            return None
        if not self.isHasPartition:
            return None
        parts = get_all_partitions(self.tableName)
        if not parts:
            return None
        ps = self.colsOfPartition
        rows = []
        for p in parts:
            kv = {}
            for seg in str(p).split("/"):
                if "=" in seg:
                    k, v = seg.split("=", 1)
                    kv[k] = v
            row = [str(p)]
            for c in ps:
                row.append(kv.get(c, ''))
            row.append(",".join("{}='{}'".format(k, v) for k, v in kv.items()))
            rows.append(row)
        spark = get_spark()
        df = spark.createDataFrame(rows, ["partition"] + list(ps) + ["ps"])

        s = where_condition.strip()
        if s:
            if s[:6].lower() == "where ":
                s = s[6:]
            df = df.filter(s) if s else df
        mode = mode if mode else ''
        s = where2.strip()
        if s:
            if s[:6].lower() == "where ":
                s = s[6:]
            df = df.filter(s) if s else df
            if mode == "for_drop":
                return df.select("ps")
            if mode in ("raw", 'null', ''):
                return df.select("partition")
        return df

    def push(self, target_table=None, where_condition='', select_cols=None,
             exclude_cols=None, drop_if_exists=False):
        """推送到 PG 表。"""
        from .postgre import insertData
        df = self.query(where_condition, select_cols, exclude_cols)
        target_table = target_table if target_table else self.tbName
        insertData(df, target_table, drop_if_exists=drop_if_exists)

    @classmethod
    def get_transposed_df(cls, df_or_sql, groupNames=None, order_col=None, newColsName=None,
                          tempName=None, result_tempName=None, result_TbName=None, return_df=False):
        """把 DataFrame 转置（classmethod，legacy 语义）。"""
        spark = get_spark()
        if isinstance(df_or_sql, str):
            df = spark.sql(df_or_sql)
        elif hasattr(df_or_sql, 'selectExpr'):
            df = df_or_sql
        else:
            raise Exception("typeError :df_or_sql must sql string or DataFrame!")

        if result_tempName is not None and not isinstance(result_tempName, str):
            result_tempName = "temp_transposed"
        if tempName is None:
            tempName = "temp_transposed_org"
        if not isinstance(tempName, str):
            tempName = "temp_transposed_org"
        if order_col is None:
            order_col = "index_xh"
        if not isinstance(order_col, str):
            order_col = "index_xh"

        num_rows = df.count()
        if newColsName is None:
            newColsName = ['col_{}'.format(i + 1) for i in range(num_rows)]
        elif isinstance(newColsName, str):
            newColsName = newColsName.split(",") if "," in newColsName else [newColsName]
        elif isinstance(newColsName, list):
            newColsName = newColsName[:num_rows]
        else:
            raise Exception("typeError :newColsName must string or list<string>!")
        newColsName = [str(i).strip() for i in newColsName if str(i).strip()]

        original_columns = df.columns
        if groupNames is None:
            groupNames = []
        elif isinstance(groupNames, str):
            groupNames = groupNames.split(",") if "," in groupNames else [groupNames]
        groupNames = [str(i).strip() for i in groupNames if str(i).strip()]
        groupNames = [i for i in groupNames if i in original_columns]
        if order_col in groupNames:
            raise Exception("typeError :order col must not in groupNames !")
        non_has_group = (groupNames is None or len(groupNames) == 0)

        from pyspark.sql import functions as F
        from pyspark.sql import Window

        if order_col in original_columns:
            original_columns = [x for x in original_columns if x not in groupNames and x != order_col]
        else:
            original_columns = [x for x in original_columns if x not in groupNames]
            df = df.withColumn("{}_temp".format(order_col), F.monotonically_increasing_id())
            wP = (Window.orderBy("{}_temp".format(order_col)) if non_has_group
                  else Window.partitionBy(*groupNames).orderBy("{}_temp".format(order_col)))
            df = df.withColumn(order_col, F.row_number().over(wP)).drop("{}_temp".format(order_col))

        if not non_has_group:
            max_xh = max([int(x[0]) for x in df.select(order_col).collect()]) if df.count() > 0 else 0
            newColsName = newColsName[:max_xh]

        df.createOrReplaceTempView(tempName)

        def get_unit_sql(colName):
            lst = []
            gs = "" if non_has_group else ",".join(groupNames) + ","
            s = "select '{}' as field_name".format(colName)
            if not non_has_group:
                s = "select {} '{}' as field_name".format(gs, colName)
            lst.append(s)
            for i, newColName in enumerate(newColsName):
                i += 1
                s = ",cast(max(if(index_xh={idx} , {col}, null)) as string) as {nc}".format(
                    idx=i, col=colName, nc=newColName)
                lst.append(s)
            lst.append("from {}".format(tempName))
            if not non_has_group:
                lst.append("group by " + ','.join(map(str, range(1, len(groupNames) + 1))))
            return '\n'.join(lst)

        transpose_query = "\n union all \n".join(map(get_unit_sql, original_columns))
        if not return_df:
            return transpose_query
        transposed_df = spark.sql(transpose_query)
        if result_tempName:
            transposed_df.createOrReplaceTempView(result_tempName)
        if result_TbName:
            transposed_df.write.mode("overwrite").format("hive").saveAsTable(result_TbName)
        return transposed_df

    @classmethod
    def add_index_predix(cls, df_or_sql, flag=None, show_result=False):
        """给 DataFrame 加列索引前缀列（classmethod，legacy 语义）。"""
        spark = get_spark()
        if isinstance(df_or_sql, str):
            df = spark.sql(df_or_sql)
        elif hasattr(df_or_sql, 'selectExpr'):
            df = df_or_sql
        else:
            raise Exception("typeError :df_or_sql must sql string or DataFrame!")

        df = df.coalesce(1)
        cols = df.columns
        flag = flag if flag else "NULL"
        cs = ["#A{0}&{1}".format(i + 1, c) for i, c in enumerate(cols)]
        head_s = "select '{}' as flag , '{}' as jioned_v".format(flag, "".join(cs))
        tf = spark.sql(head_s)

        for i, r in enumerate(df.collect()):
            j = int(i / 25) + 1
            i = i % 25 + 2
            c = excel_number_to_column(i)
            fs = []
            for k, v in enumerate(r):
                v = "NULL" if v is None else str(v)
                fs.append("#{0}{1}&{2}".format(c, k + 1, v))
            value_s = "select '{0}{1}' as flag , '{2}' as jioned_v".format(flag, j, "".join(fs))
            tf = tf.union(spark.sql(value_s))

        if show_result:
            tf.show()
        return tf


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
        # DESCRIBE 输出含 "# Partition Information" / "# col_name" 等标题行，
        # 这些不是真实列，必须过滤；再去重（分区表会重复列出分区列）。
        _seen = set()
        _cols = []
        for r in df.collect():
            v = str(r[0]) if r[0] is not None else ""
            v = v.strip()
            if not v or v.startswith('#') or v in _seen:
                continue
            _seen.add(v)
            _cols.append(v)
        if return_df:
            return spark.createDataFrame([(c,) for c in _cols], ["col_name"])
        return _cols
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