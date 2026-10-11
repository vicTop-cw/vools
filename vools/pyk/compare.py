"""
pyk.compare - DataFrame 比对

提供:
- vicCompare: DataFrame 比对包装类 (以 legacy vools.py 的实现为准)
- vic_comp: 快速比对函数 (以 legacy 为准)
- checkOneToOne: 检查一对一关系
- comp / comp_detail: 兼容别名
"""

from __future__ import absolute_import

__all__ = [
    "vicCompare",
    "vic_comp",
    "checkOneToOne",
    "comp",
    "comp_detail",
]

from .core import get_spark
from .df import vDF


# ============================================================
# 简易 lazy property (避免额外依赖 multipledispatch)
# ============================================================
class LazyProperty(object):
    """惰性求值属性装饰器 (首次访问时计算并缓存)。

    用法:
        class A:
            @LazyProperty
            def x(self): return compute_heavy()
    """

    def __init__(self, func):
        self._func = func
        self.__name__ = getattr(func, "__name__", "x")
        self.__doc__ = getattr(func, "__doc__", None)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        value = self._func(obj)
        obj.__dict__[self.__name__] = value
        return value


# ============================================================
# vicCompare (以 legacy vools.py L5544-L5736 为准)
# ============================================================
class vicCompare(object):
    """DataFrame 比对类。

    用法:
        c = vicCompare(df1, df2, key_cols=['id'], mode='strict')
        c.comp_detail().show()          # 逐列比对明细
        c.comp_detail_by_union().show() # 合并两个来源
        vicCompare.vic_hash_comp(tb1, tb2)  # 哈希级快速比对
        vic_comp(tb1, tb2, sep=',')     # 快速比对入口
    """

    def __init__(self, source1, source2, key_cols=None, mode="strict",
                 suffix_a="_A", suffix_b="_B", final_col="vicCompare_flag",
                 diff_cols_col="diff_cols", select_cols=None, key=None):
        """初始化。

        参数:
            source1: 左侧 DataFrame / SQL / 表名 / 表对象
            source2: 右侧 DataFrame / SQL / 表名 / 表对象
            key_cols: 比对主键列 (str / list); None 取两表公共列
            mode: strict / index / intersection / select / count
            suffix_a / suffix_b: 左右后缀
            final_col: 最终比对标记列名
            diff_cols_col: 差异列名列名
            select_cols: mode='select' 时指定比对列
            key:       key_cols 的别名 (兼容 pyk 旧签名)
        """
        # py3.6 不允许非默认参数跟在默认参数后面, 故 key_cols 默认 None;
        # 行为与 legacy 一致: 调用方应显式传 key_cols
        if key is not None:
            key_cols = key
        if key_cols is None:
            common = sorted(set(vDF(source1).columns) & set(vDF(source2).columns))
            if not common:
                raise ValueError("key_cols must be provided when dfA/dfB share no common column")
            key_cols = common
        self.dfA = vDF(source1)
        self.dfB = vDF(source2)
        self.keys_cols = _transfer_cols(key_cols)
        self.mode = mode
        self.suffix_a = suffix_a
        self.suffix_b = suffix_b
        self.final_col = final_col
        self.select_cols = select_cols
        self.diff_cols_col = diff_cols_col
        self.reset_df()

    @LazyProperty
    def comp_cols(self):
        return self.get_comp_cols()

    def reset_df(self):
        """根据比对模式把 dfA/dfB 规范化到可比状态。"""
        cs = self.comp_cols
        from pyspark.sql import functions as F
        if self.mode == "count":
            self.dfA = self.dfA.groupBy(*self.keys_cols).agg(F.count("*").alias("cnt"))
            self.dfB = self.dfB.groupBy(*self.keys_cols).agg(F.count("*").alias("cnt"))
            return
        if self.mode == "index":
            csa = [c for c in self.dfA.columns if c not in self.keys_cols]
            csb = [c for c in self.dfB.columns if c not in self.keys_cols]
            csa = ["{} as {}".format(c, x) for c, x in zip(csa, cs)]
            csb = ["{} as {}".format(c, x) for c, x in zip(csb, cs)]
            self.dfA = self.dfA.selectExpr(*self.keys_cols, *csa)
            self.dfB = self.dfB.selectExpr(*self.keys_cols, *csb)
            return
        self.dfA = self.dfA.select(*self.keys_cols, *cs)
        self.dfB = self.dfB.select(*self.keys_cols, *cs)

    def get_comp_cols(self):
        """解析参与比对的列 (非主键列)。"""
        csa, csb = list(self.dfA.columns), list(self.dfB.columns)
        if not self.keys_cols or not set(self.keys_cols).issubset(csa) or not set(self.keys_cols).issubset(csb):
            raise ValueError(
                "keys_cols must be subset of dfA and dfB, but got {} for dfA and {} for dfB".format(
                    self.keys_cols, csa))
        csa = [c for c in csa if c not in self.keys_cols]
        csb = [c for c in csb if c not in self.keys_cols]
        if self.mode == "count":
            return ["cnt"]
        if self.mode == "strict":
            if csa != csb:
                raise ValueError(
                    "dfA and dfB must have the same columns, but got {} for dfA and {} for dfB".format(csa, csb))
            return csa
        if self.mode == "index":
            if len(csa) != len(csb):
                raise ValueError(
                    "dfA and dfB must have the same number of columns except keys_cols, "
                    "but got {} for dfA and {} for dfB".format(csa, csb))
            return csa
        if self.mode == "intersection":
            cs = list(set(csa) & set(csb))
            if not cs:
                raise ValueError(
                    "dfA and dfB must have at least one common column, but got {} for dfA and {} for dfB".format(
                        csa, csb))
            return cs
        if self.mode == "select":
            if self.select_cols:
                cs = _transfer_cols(self.select_cols)
                if not set(cs).issubset(csa) or not set(cs).issubset(csb):
                    raise ValueError(
                        "select_cols must be subset of dfA and dfB, but got {} for dfA and {} for dfB".format(
                            cs, csa))
                return cs
            raise ValueError("select_cols must be provided when mode is select")
        raise ValueError("mode must be in (strict, index, intersection, select, count), got {!r}".format(self.mode))

    def comp_detail(self, comp_funcs=None, cache=True, suff_comp_flag="_comp_flag"):
        """逐列比对, 返回差异明细 DataFrame。

        参数:
            comp_funcs: 每列自定义比对函数列表; None 用 <=> (null-safe equal)
            cache:      True 时 cache()
            suff_comp_flag: 比对结果 flag 列后缀
        返回:
            DataFrame
        """
        from pyspark.sql import functions as F
        from pyspark.sql.functions import expr

        self.suffix_comp_flag = suff_comp_flag
        df1 = self.dfA.alias("a")
        df2 = self.dfB.alias("b")
        ks = self.keys_cols
        cs = self.comp_cols
        a = ["a.{} as {}{}".format(c, c, self.suffix_a) for c in cs]
        b = ["b.{} as {}{}".format(c, c, self.suffix_b) for c in cs]

        df_1 = df1.join(df2, on=ks, how="outer").selectExpr(*ks, *a, *b)

        if not comp_funcs:
            comp_funcs = [
                expr("case when {}{} <=> {}{} then 1 else 0 end as {}{}".format(
                    c, self.suffix_a, c, self.suffix_b, c, suff_comp_flag))
                for c in cs
            ]
        else:
            comp_funcs = [
                F.when(comp_func(F.col("{}{}".format(c, self.suffix_a)),
                                 F.col("{}{}".format(c, self.suffix_b))), 1).otherwise(0).alias("{}{}".format(c, suff_comp_flag))
                for c, comp_func in zip(cs, comp_funcs)
            ]
        comp_final_col = " and ".join(["{}{} = 1".format(c, suff_comp_flag) for c in cs])
        fs_cols = " || ' ' || ".join(
            "case when {}{} = 1 then '' else replace('{}{}','{}','') end".format(
                c, suff_comp_flag, c, suff_comp_flag, suff_comp_flag)
            for c in cs
        )
        cps = []
        for i in range(len(cs)):
            cps.append(cs[i] + self.suffix_a)
            cps.append(cs[i] + self.suffix_b)
            cps.append(comp_funcs[i])
        df_2 = df_1.select(*ks, *cps).withColumn(self.final_col, expr(comp_final_col)).withColumn(
            self.diff_cols_col, expr("replace(trim({}),' ',',')".format(fs_cols)))
        return df_2.cache() if cache else df_2.cache()

    def comp_detail_by_union(self, comp_funcs=None, flag_col="source_flag", no_comp_flag=False):
        """与 comp_detail 相同, 但把结果按来源 union 成一列格式。

        返回:
            DataFrame
        """
        df = self.comp_detail(comp_funcs)
        ks = self.keys_cols
        cs = self.comp_cols
        dc, fc = self.diff_cols_col, self.final_col
        fa, fb = self.suffix_a, self.suffix_b
        cs1 = ["{}{}".format(c, fa) for c in cs]
        cs2 = ["{}{}".format(c, fb) for c in cs]
        cs_all = df.columns
        if no_comp_flag:
            cfx = ["{}{}".format(c, self.suffix_comp_flag) for c in cs]
            cs_all = [c for c in cs_all if c not in cfx]
        c1, c2 = len(fa), len(fb)
        csa = ["'{}' as {}".format(fa, flag_col)] + [
            ("{} as {}".format(c, c[:len(c) - c1]) if c in cs1 else c) for c in cs_all if c not in cs2]
        csb = ["'{}' as {}".format(fb, flag_col)] + [
            ("{} as {}".format(c, c[:len(c) - c2]) if c in cs2 else c) for c in cs_all if c not in cs1]
        df1, df2 = df.selectExpr(*csa), df.selectExpr(*csb)
        return df1.unionByName(df2)

    def compare(self, comp_method="hash", **kwargs):
        """比对并返回结果 (兼容旧 pyk 接口)。

        参数:
            comp_method: 只支持 "hash"; 返回 vic_hash_comp 结果
        Returns:
            DataFrame: 哈希比对结果
        """
        if comp_method == "hash":
            return vicCompare.vic_hash_comp(self.dfA, self.dfB, kwargs.get("sep", ","))
        raise ValueError("comp_method must be 'hash', got {!r}".format(comp_method))

    def show(self, n=100, truncate=20):
        """展示比对结果前 n 行, 返回 self。

        参数:
            n:       行数
            truncate: 截断宽度
        Returns:
            self
        """
        df = self.compare()
        df.show(n, truncate=truncate)
        return self

    def __call__(self, *args, **kwargs):
        """调用即比对。"""
        return self.compare(*args, **kwargs)

    def run(self, func=print, *args, **kwargs):
        """执行副作用操作, 返回 self。"""
        func(self.compare(), *args, **kwargs)
        return self


    @staticmethod
    def vic_hash_comp(df_or_sql_or_tbName1, df_or_sql_or_tbName2, sep=",", return_df=True):
        """快速哈希级比对两个 DataFrame/表。

        参数:
            df_or_sql_or_tbName1: 左源
            df_or_sql_or_tbName2: 右源
            sep: 列名分隔符 (用于展示)
            return_df: True 返回 DataFrame; False 返回 list[tuple]
        返回:
            DataFrame / list[tuple]
        """
        from .text import _transfer as _transfer_fn
        df1 = _transfer_fn(df_or_sql_or_tbName1)
        df2 = _transfer_fn(df_or_sql_or_tbName2)
        cs1 = [str(c).lower() for c in df1.columns]
        cs2 = [str(c).lower() for c in df2.columns]
        cols_same = (cs1 == cs2)
        cols_len_same = (len(cs1) == len(cs2))
        cols1_cols2 = sep.join(sorted(list(set(cs1) - set(cs2))))
        cols2_cols1 = sep.join(sorted(list(set(cs2) - set(cs1))))

        if cols_same:
            cols_relation = "same"
        elif cols_len_same:
            if not cols1_cols2 and not cols2_cols1:
                cols_relation = "same but order diff"
            else:
                cols_relation = "same cols size but  diff"
        else:
            cols_relation = "diff"
        df1 = df1.selectExpr(*["cast({} as string) as {}".format(c, c) for c in cs1])
        df2 = df2.selectExpr(*["cast({} as string) as {}".format(c, c) for c in cs2])
        tf1 = df1.selectExpr("hash(*) as h1").distinct().cache()
        tf2 = df2.selectExpr("hash(*) as h2").distinct().cache()
        cnt1, cnt2 = tf1.count(), tf2.count()
        ss = """
            case when h1 is not null and h2 is not null then 'A1B1'
            when h1 is not null and h2 is  null then 'A1B0'
            when h1 is   null and h2 is not null then 'A0B1'
            else 'A0B0' end as h
        """
        rf = tf1.join(tf2, tf1["h1"] == tf2["h2"], "full_outer").selectExpr(ss).groupBy("h").count().cache()
        t11 = rf.where("h = 'A1B1'").select("count").collect()
        t10 = rf.where("h = 'A1B0'").select("count").collect()
        t01 = rf.where("h = 'A0B1'").select("count").collect()
        t11 = t11[0][0] if len(t11) > 0 else 0
        t10 = t10[0][0] if len(t10) > 0 else 0
        t01 = t01[0][0] if len(t01) > 0 else 0
        if t01 == 0 and t10 == 0:
            data_relation = 'same' if t11 > 0 else "Both Empty!"
        elif t10 == 0 and t01 > 0:
            data_relation = "B include A" if t11 > 0 else 'B has Data but  A is  Empty!'
        elif t10 > 0 and t01 == 0:
            data_relation = "A include B" if t11 > 0 else 'A has Data but  B is  Empty!'
        elif t10 > 0 and t01 > 0:
            data_relation = "intersection" if t11 > 0 else 'different'
        rs = [
            ('cols_same', str(cols_same)),
            ('cols_len_same', str(cols_len_same)),
            ('cols_relation', str(cols_relation)),
            ('colsA_colsB', str(cols1_cols2)),
            ('colsB_colsA', str(cols2_cols1)),
            ('cnt_A', str(cnt1)),
            ('cnt_B', str(cnt2)),
            ('A1B1', str(t11)),
            ('A1B0', str(t10)),
            ('A0B1', str(t01)),
            ('data_relation', str(data_relation)),
        ]
        if return_df:
            from pyspark.sql import Row
            spark = get_spark()
            return spark.createDataFrame([Row(field_name=k, field_value=v) for k, v in rs])
        return rs


# ============================================================
# 函数 (以 legacy 为准)
# ============================================================
def vic_comp(source1, source2, sep=",", comp_method="hash"):
    """快速比对两个 DataFrame, 返回比对结果 DataFrame。

    参数:
        source1:     左源
        source2:     右源
        sep:         列名分隔符 (hash 比对展示用)
        comp_method: 只支持 "hash"
    Returns:
        DataFrame
    """
    if comp_method == "hash":
        return vicCompare.vic_hash_comp(source1, source2, sep)
    raise ValueError("comp_method must be 'hash', got {!r}".format(comp_method))


def comp(source1, source2, key=None):
    """比对别名。"""
    return vic_comp(source1, source2)


def comp_detail(source1, source2, key=None, show_diff_cols=True):
    """比对并返回差异明细。"""
    c = vicCompare(source1, source2, key)
    return c.comp_detail()


def checkOneToOne(df, col1, col2, blank=False):
    """检查 col1 → col2 是否一对一。

    参数:
        df:    DataFrame
        col1:  主列
        col2:  次列
        blank: True 允许空值
    Returns:
        DataFrame: 违规记录 (col1 对应多个 col2)
    """
    spark = get_spark()
    from pyspark.sql import functions as F

    if not blank:
        df = df.filter(F.col(col1).isNotNull()).filter(F.col(col2).isNotNull())
    grouped = df.groupBy(col1).agg(F.countDistinct(col2).alias("cnt"))
    return grouped.filter(F.col("cnt") > 1)


# ============================================================
# 内部工具
# ============================================================
def _transfer_cols(cols, sep=","):
    """把 str/list/tuple 列名规范成 list[str]。

    参数:
        cols: "a,b,c" 或 ["a","b"] 或 ("a","b")
        sep:  分隔符
    Returns:
        list[str]
    """
    if cols is None:
        return []
    if isinstance(cols, str):
        return [c.strip() for c in cols.split(sep) if c.strip()]
    if isinstance(cols, (list, tuple)):
        return [str(c).strip() for c in cols]
    return [str(cols)]

