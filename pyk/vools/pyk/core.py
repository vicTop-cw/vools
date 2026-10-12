"""
pyk.core - Spark 基础工具

提供:
- get_spark(): 全局 SparkSession 单例
- get_run_ds()/set_run_ds(): 全局 run_date 管理
- show_*(): 打印分隔符/结构
- get_hdfs_file_metadata / get_hdfs_folder_stats: HDFS 元数据
"""

from __future__ import absolute_import, print_function

__all__ = [
    "get_spark",
    "ensure_env",
    "get_run_ds",
    "set_run_ds",
    "show_",
    "get_hdfs_file_metadata",
    "get_hdfs_folder_stats",
    # legacy spark 核心工具
    "my_spark",
    "my_run_ds",
    "waiter",
    "serializable",
    "vic_execute",
    "check_max_date",
    "check_partition",
    "check_partition_ex",
]

import os
import sys

# 生产默认库名走 configs（环境变量/显式覆写），公开库不硬编码
from .configs import default_db as _default_db

# ---- 全局单例 ----
_SPARK = None
_RUN_DS = None


def ensure_env(python=None, java_home=None, clear_spark_home=True):
    """确保 pyspark worker 使用正确的 Python/Java 环境（Windows 本地多 Python 环境必用）。

    参数:
        python:           worker 的 python 解释器路径；None 则自动探测 sys.executable
        java_home:        JDK 路径；None 则不动 JAVA_HOME
        clear_spark_home: True 时移除 SPARK_HOME，避免 pyspark 2.4.3 被本地 3.x 干扰
    """
    if python is None:
        python = sys.executable
    os.environ["PYSPARK_PYTHON"] = python
    os.environ["PYSPARK_DRIVER_PYTHON"] = python
    if java_home:
        os.environ["JAVA_HOME"] = java_home
    if clear_spark_home:
        os.environ.pop("SPARK_HOME", None)

def get_spark(app_name="pyk_spark", master=None, enable_hive=True, bind_address="127.0.0.1", **kwargs):
    """获取或创建全局 SparkSession（单例）。

    参数:
        app_name:      Spark 应用名
        master:        master URL; None 则交 pyspark 默认
        enable_hive:   True 时 enableHiveSupport()
        bind_address:  driver bind/host 地址，默认 127.0.0.1 (Windows 下避免 Python worker 回连超时)
        **kwargs:      额外 SparkConf (key=value)，例如 shuffle_partitions=200
                       同名配置覆盖上面默认，生产集群可显式传
                       driver_host="10.x.x.x" 或直接 kwargs

    Returns:
        SparkSession
    """
    global _SPARK
    if _SPARK is not None:
        return _SPARK
    try:
        from pyspark.sql import SparkSession
    except ImportError as e:
        raise ImportError(
            "pyk 需要 pyspark，当前未安装: {}. 请先 `pip install pyspark` 或配置 SPARK_HOME。".format(e)
        )
    builder = SparkSession.builder.appName(app_name)
    if master:
        builder = builder.master(master)
    # Windows 兼容默认：固定 driver 绑定地址，避免 Python worker 回连 accept 超时
    defaults = {
        "spark.driver.host": bind_address,
        "spark.driver.bindAddress": bind_address,
    }
    for k, v in defaults.items():
        builder = builder.config(k, v)
    for k, v in kwargs.items():
        builder = builder.config(k, v)
    if enable_hive:
        builder = builder.enableHiveSupport()
    _SPARK = builder.getOrCreate()
    return _SPARK


def get_run_ds(run_ds=None):
    """获取 run_date。显式传参优先，否则取全局变量。

    Returns:
        str: run_date (格式 yyyy-MM-dd)
    """
    if run_ds:
        return str(run_ds)
    if _RUN_DS:
        return str(_RUN_DS)
    return _RUN_DS


def set_run_ds(run_ds):
    """设置全局 run_date。

    Args:
        run_ds: run_date 字符串 (yyyy-MM-dd)
    """
    global _RUN_DS
    _RUN_DS = str(run_ds)


# ---- 打印工具 ----

def show_(*obj, flag_list=None, sep="--.-" * 37 + ":\n"):
    """带分隔符的 print，便于日志里定位。

    参数:
        *obj:       要打印的对象
        flag_list:  可选, 打印前标注的标签列表
        sep:        分隔符
    """
    print(sep)
    if flag_list:
        for f in flag_list:
            print("FLAG:", f)
    for o in obj:
        print(o)
    print(sep)


# ---- HDFS 工具 ----

def get_hdfs_file_metadata(file_path):
    """获取 HDFS 单文件的元数据。

    依赖 pyspark 的 JavaGateway；无 spark 上下文时返回 None。

    Args:
        file_path: HDFS 路径, 如 'hdfs://nn/path/file.parquet'

    Returns:
        dict 或 None: {path, size, modificationTime}
    """
    try:
        spark = get_spark()
        jvm = spark._jvm
        hdfs = jvm.org.apache.hadoop.fs.FileSystem
        conf = spark._jsc.hadoopConfiguration()
        fs = hdfs.get(conf)
        path = jvm.org.apache.hadoop.fs.Path(file_path)
        if not fs.exists(path):
            return None
        fs_stat = fs.getFileStatus(path)
        return {
            "path": file_path,
            "size": int(fs_stat.getLen()),
            "modificationTime": int(fs_stat.getModificationTime()),
        }
    except Exception:
        return None


def get_hdfs_folder_stats(folder_path):
    """获取 HDFS 文件夹下所有文件大小总和及数量。

    Args:
        folder_path: HDFS 文件夹路径

    Returns:
        dict: {file_count, total_size}
    """
    try:
        spark = get_spark()
        jvm = spark._jvm
        conf = spark._jsc.hadoopConfiguration()
        fs = jvm.org.apache.hadoop.fs.FileSystem.get(conf)
        path = jvm.org.apache.hadoop.fs.Path(folder_path)
        if not fs.exists(path):
            return {"file_count": 0, "total_size": 0}
        status = fs.listStatus(path)
        count = len(status)
        total = sum(int(s.getLen()) for s in status)
        return {"file_count": count, "total_size": total}
    except Exception:
        return {"file_count": 0, "total_size": 0}


# ============================================================
# 以下为 legacy vools.py (L759-L1026) spark 核心工具迁移
# 保持 legacy 函数名与 docstring；pyspark 一律函数内 import
# ============================================================

# ---- legacy 全局变量 ----
vicspark = None
vicrun_ds = None
spark = None        # 别名: 指向 vicspark
sc = None
hadoop_conf = None


def my_spark(spk):
    """legacy 兼容: 设置全局 vicspark。

    等价于 ``spark = spk``; 后续 ``check_*`` / ``get_hdfs_*`` 会使用它。
    """
    global vicspark, spark, sc, hadoop_conf
    if spk:
        vicspark = spk
        spark = spk
        try:
            sc = spk.sparkContext
            hadoop_conf = sc._jsc.hadoopConfiguration()
        except Exception:
            sc = None
            hadoop_conf = None


def my_run_ds(run_ds=None):
    """legacy 兼容: 设置全局 vicrun_ds。

    参数:
        run_ds: 形如 '20261010' 或 '2026-10-10'
    """
    global vicrun_ds
    if run_ds:
        from ..datetime.vdate_class import VDate
        vicrun_ds = VDate(run_ds, fmt='%Y%m%d')


def waiter(
    checker, retry_time, max_try_times,
    backoff_factor=1.0
):
    """支持指数退避的重试"""
    import time
    if max_try_times < 1:
        raise ValueError("max_try_times must be at least 1")

    for attempt in range(1, max_try_times + 1):
        if checker():
            return
        else:
            delay = retry_time * (backoff_factor ** (attempt - 1))
            print("Attempt {}: waiting for {} seconds".format(attempt, delay))
            time.sleep(delay)

    raise TimeoutError("Timeout after {} attempts".format(max_try_times))


def get_hdfs_file_metadata(file_path):
    """获取 HDFS 文件的修改时间和创建时间 (legacy 版)

    :param file_path: 文件路径
    :return: (修改时间, 创建时间)
    """
    import datetime as _dt
    global sc, hadoop_conf
    if sc is None or hadoop_conf is None:
        raise RuntimeError("请先调用 my_spark(spark) 设置 Spark 上下文")
    fs = sc._jvm.org.apache.hadoop.fs.FileSystem.get(hadoop_conf)
    path = sc._jvm.org.apache.hadoop.fs.Path(file_path)
    file_status = fs.getFileStatus(path)
    # 获取文件的修改时间
    modification_time = file_status.getModificationTime()
    # 获取文件的创建时间（HDFS 中没有明确的创建时间，通常取修改时间）
    creation_time = file_status.getAccessTime()
    # 转换为人类可读格式
    mod_time = _dt.datetime.utcfromtimestamp(modification_time / 1000).strftime('%Y-%m-%d %H:%M:%S')
    create_time = _dt.datetime.utcfromtimestamp(creation_time / 1000).strftime('%Y-%m-%d %H:%M:%S')
    return mod_time, create_time


def get_hdfs_folder_stats(folder_path):
    """获取 HDFS 文件夹递归统计信息 (legacy 版)

    参数:
        folder_path: HDFS 文件夹路径
    返回:
        (创建时间, 子目录数, 文件数, "X.XXXXMb") 或 (None,None,None,None)
    """
    import datetime as _dt
    global sc, hadoop_conf
    if sc is None or hadoop_conf is None:
        raise RuntimeError("请先调用 my_spark(spark) 设置 Spark 上下文")
    try:
        fs = sc._jvm.org.apache.hadoop.fs.FileSystem.get(hadoop_conf)
        path = sc._jvm.org.apache.hadoop.fs.Path(folder_path)
        if not fs.exists(path):
            return (None, None, None, None)
        status = fs.getFileStatus(path)
        creation_time = status.getModificationTime()
        creation_time = _dt.datetime.utcfromtimestamp(creation_time / 1000).strftime('%Y-%m-%d %H:%M:%S.') + str(creation_time)[-3:]

        file_count = 0
        dir_count = 0
        total_size = 0

        def traverse_directory(pth):
            nonlocal file_count, dir_count, total_size
            st = fs.getFileStatus(pth)
            if st.isDirectory():
                dir_count += 1
                file_status_list = fs.listStatus(pth)
                for file_status in file_status_list:
                    traverse_directory(file_status.getPath())
            else:
                file_count += 1
                total_size += st.getLen()

        traverse_directory(path)
        return (creation_time, dir_count, file_count, "{:.4f}Mb".format(total_size / 1024 / 1024))
    except Exception as e:
        print("Error: {}".format(e))
        return None


def serializable(cls):
    """legacy 兼容: 给类挂 pickle 序列化/反序列化静态方法。"""
    import pickle
    cls._serialize = staticmethod(lambda obj: pickle.dumps(obj))
    cls._deserialize = staticmethod(lambda obj: pickle.loads(obj))
    return cls


def vic_execute(max_workers=3, use_process=False):
    """legacy 兼容: 把函数包装成线程池/进程池并行执行装饰器。

    参数:
        max_workers: 最大并发数
        use_process: True 用 ProcessPoolExecutor, False 用 ThreadPoolExecutor
    """
    from functools import wraps
    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
    from collections.abc import Iterable

    def decorator(func):
        @wraps(func)
        def wrapper(iterable):
            its = iterable if isinstance(iterable, Iterable) else [iterable]
            pool = ProcessPoolExecutor if use_process else ThreadPoolExecutor
            with pool(max_workers=max_workers) as executor:
                results = [future for future in executor.map(func, its)]
            return results
        return wrapper
    return decorator


def check_max_date(sql, timeOut=90, reTryInterval=45, timeWait=10):
    """legacy 兼容: 轮询 SQL 首个日期字段是否 >= vicrun_ds。

    参数:
        sql:           要执行的 SQL (第一列须为日期)
        timeOut:       超时（分钟）
        reTryInterval: 重试间隔（秒）
        timeWait:      首次等待（分钟）
    """
    import time
    from datetime import datetime, timedelta
    global vicspark, vicrun_ds
    from ..datetime.vdate_class import VDate

    dt = vicspark.sql(sql).first()[0]
    dt = str(dt)[:10]
    lmd = (lambda x: x >= vicrun_ds) if len(dt) == 8 else (
        lambda x: x >= str(VDate(vicrun_ds, fmt='yyyy-MM-dd'))
    )
    timeOut = timeOut * 60
    timeWait = timeWait * 60 if timeWait else 0
    today = datetime.now() - timedelta(days=1)
    timeout_time = datetime.now() + timedelta(seconds=timeOut)

    while datetime.now() < timeout_time:
        if lmd(dt):
            print('max date is Ok:', dt, "run_date:", vicrun_ds)
            return
        dt = str(vicspark.sql(sql).first()[0])[:10]
        time.sleep(reTryInterval)

    raise TimeoutError(
        "Query sql : '{}' the max date not >= {} , after {} seconds".format(sql, vicrun_ds, timeOut)
    )


def check_partition(tbNames, run_date=None, timeOut=90, reTryInterval=45, timeWait=5):
    """legacy 兼容: 轮询 Hive 表分区是否就绪 (ds=run_date)。

    参数:
        tbNames:       表名列表或逗号分隔字符串
        run_date:      目标日期; None 用 vicrun_ds
        timeOut:       超时（分钟）
        reTryInterval: 重试间隔（秒）
        timeWait:      首次等待（分钟）
    """
    import copy, time
    from datetime import datetime, timedelta
    global vicspark, vicrun_ds

    if run_date is None:
        run_date = copy.deepcopy(vicrun_ds)
    timeOut = timeOut * 60
    timeWait = timeWait * 60 if timeWait else 0
    today = datetime.now() - timedelta(days=1)
    run_date = "ds={}".format(run_date)
    timeout_time = datetime.now() + timedelta(seconds=timeOut)

    if isinstance(tbNames, str):
        tbNames = [tbNames] if ", " in tbNames else tbNames.split(",")
    else:
        tbNames = list(set(tbNames))
    tbNames = [c if "." in c else "{}.{}".format(_default_db(), c) for c in tbNames]

    exists_tbNames = []
    cnt = len(tbNames)
    p = timeWait > 0 and today.strftime('%Y%m%d') >= run_date and int(today.hour) < 13
    while datetime.now() < timeout_time:
        for tbName in tbNames:
            try:
                df = vicspark.sql("show partitions {}".format(tbName))
            except Exception as e:
                print("Table '{}' is not Partition table !".format(tbName))
                exists_tbNames.append(tbName)
                break
            df = df.where(df["partition"].contains(run_date))
            if df.count() > 0:
                print("Table '{}' Partition '{}' exists !".format(tbName, run_date))
                exists_tbNames.append(tbName)
            else:
                break
        if len(exists_tbNames) == cnt or len(tbNames) == 0:
            if p:
                time.sleep(timeWait)
                print("waited {} seconds".format(timeWait))
            return
        elif len(exists_tbNames) == 0:
            pass
        else:
            tbNames = [x for x in tbNames if x not in exists_tbNames]
        time.sleep(reTryInterval)

    raise TimeoutError(
        "Partition '{}' not found in table '{}' after {} seconds".format(run_date, tbNames, timeOut)
    )


def check_partition_ex(tbNames, run_date=None, timeOut=90, reTryInterval=45, timeWait=5, date_col="ds"):
    """legacy 兼容: 支持自定义分区列名的分区就绪检查 (指数退避)。

    参数:
        tbNames:       表名列表或逗号分隔字符串
        run_date:      目标日期; None 用 vicrun_ds
        timeOut:       超时（分钟）
        reTryInterval: 重试间隔（秒）
        timeWait:      首次等待（分钟）
        date_col:      分区列名，默认 'ds'
    """
    import copy, time
    from datetime import datetime, timedelta
    global vicspark, vicrun_ds
    from ..datetime.vdate_class import VDate
    from .tb import getCols

    if run_date is None:
        run_date = copy.deepcopy(vicrun_ds)
    run_date = str(VDate(run_date))[:10]
    fmt = '%Y-%m-%d' if '-' in run_date else '%Y%m%d'
    now = datetime.now()
    today, yesterday = now.strftime(fmt), (now - timedelta(days=1)).strftime(fmt)
    tbNames = [str(i).strip() for i in set(tbNames) if str(i).strip()]

    if run_date < yesterday:
        print(
            "all tbName need not cheker cause yesterday <{}> greater than run_date  <{}> ".format(
                yesterday, run_date
            )
        )
        return [[i, True] for i in tbNames]

    def _checker1(tbName):
        nonlocal date_col, run_date
        ps = getCols(tbName=tbName, partition_cols_only=True, col_name_only=True, return_df=False)
        if len(ps) == 0 or date_col not in ps:
            return True
        ck = "%{0}={1}%".format(date_col, run_date)
        return vicspark.sql("show partitions {}".format(tbName)).where(
            "partition like '{}'".format(ck)
        ).count() > 0

    ok_tbs = [[i, False] for i in tbNames]

    def _checker2():
        nonlocal ok_tbs
        for i, tp in enumerate(ok_tbs):
            ok_tbs[i][1] = tp[1] or _checker1(tp[0])
        return all(x[1] for x in ok_tbs)

    if reTryInterval <= 0:
        reTryInterval = 1
    mx_times = int(timeOut * 60 / reTryInterval + 1)
    print(mx_times)
    try:
        waiter(_checker2, reTryInterval, mx_times)
        if timeWait:
            time.sleep(timeWait * 60)
    except Exception as e:
        raise e
    finally:
        print(*ok_tbs, sep="\n")