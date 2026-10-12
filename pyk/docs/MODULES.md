# pyk 模块 API 概览

> 文档即实现：本文件与源码同步演进。任何文档与代码不符均为 BUG。

所有模块均在 `vools.pyk` 命名空间下。

---

## core

`vools.pyk.core` — Spark 基础工具。

### 函数

| 名称 | 签名 | 说明 |
|---|---|---|
| `ensure_env` | `(python=None, java_home=None, clear_spark_home=True)` | 确保 PySpark 可用的运行环境变量 |
| `get_spark` | `(app_name="pyk_spark", master=None, enable_hive=True, bind_address="127.0.0.1", **conf)` | 获取 / 创建全局 SparkSession（单例） |
| `get_run_ds` | `(run_ds=None)` | 获取全局 `run_ds`（`pyk.core` 内部变量） |
| `set_run_ds` | `(run_ds)` | 设置全局 `run_ds` |
| `show_` | `(*obj, flag_list=None, sep=...)` | 逐项 show；`flag_list` 指定哪些项要打印 schema |
| `get_hdfs_file_metadata` | `(file_path)` | 获取 HDFS 文件元数据（大小、mtime、owner…） |
| `get_hdfs_folder_stats` | `(folder_path)` | 获取 HDFS 目录统计（文件数、总大小…） |
| `my_spark` | `(spk)` | 返回 SparkSession（等价 `get_spark`） |
| `my_run_ds` | `(run_ds=None)` | 返回 run_ds |
| `waiter` | `(...)` | 等待辅助（轮询 / 条件） |
| `serializable` | `(cls)` | 让类可被 Spark 序列化（装饰器） |
| `vic_execute` | `(max_workers=3, use_process=False)` | 并行执行装饰器 |
| `check_max_date` | `(sql, timeOut=90, reTryInterval=45, timeWait=10)` | 等待 Hive 表 max(dt) 达到预期 |
| `check_partition` | `(tbNames, run_date=None, timeOut=90, reTryInterval=45, timeWait=5)` | 等待分区就绪 |
| `check_partition_ex` | `(tbNames, run_date=None, ...)` | `check_partition` 增强版（支持 `_checker1/_checker2`） |

---

## df

`vools.pyk.df` — DataFrame 扩展。

### vicDataFrame 类

| 方法 | 说明 |
|---|---|
| `__init__(src)` | 包装一个 `DataFrame` 或 `str`（SQL） |
| `.df` | 返回底层 DataFrame |
| `.columns` | 列名列表 |
| `.to_list()` | 转 list（每行 dict） |
| `.run(func=print)` | 执行 func(每行) |
| `__add__(other)` / `__sub__` / `__and__` / `__or__` | 集合运算 |
| `.unique_by(partition_by, order_by=None)` | 分组去重（每组保留一行） |
| `.show_ex(n=100)` | 更友好的 show（含 schema、行数统计） |
| `.select_ex(*cols, **kcols)` | 支持 `a=b` 形式的选择 |
| `.grouping_sets(group_cols, sets_expr, *agg_expr, **kwargs)` | GROUPING SETS |
| `.order_cols(key=None, reverse=False)` | 排序 |
| `.toList()` / `.showEx()` / `.selectEx()` / `.groupingSets()` | 驼峰别名 |

---

## text

`vools.pyk.text` — `vicText` 的 pyspark 相关扩展。

### 功能

| 功能 | 说明 |
|---|---|
| `toDF` | 把 `vicText`（文本表抽象）转换为 `DataFrame` |
| 转 DataFrame | 支持从 `vicText` / 字符串 / 列表快速构建 DataFrame |

`vicText` 是 vools 核心提供的文本表抽象，pyk.text 为其补齐 Spark 侧能力。

---

## tb

`vools.pyk.tb` — Hive 表元数据。

### vicTableInfo

| 方法 | 说明 |
|---|---|
| `getCols` | 获取列名列表 |
| `get_partitions` | 获取分区信息 |
| 其他元数据 | 表 owner、location、表类型… |

### 函数

| 名称 | 说明 |
|---|---|
| `getCols(table)` | 取表列 |
| `get_partitions(table)` | 取分区 |

---

## compare

`vools.pyk.compare` — DataFrame 比对。

### vicCompare

| 方法 | 说明 |
|---|---|
| `compare(df_a, df_b, keys=...)` | 按 keys 比对两 DataFrame，返回差异集 |
| `diff_report()` | 输出差异报告（仅 A 有 / 仅 B 有 / 值不同） |

---

## postgre

`vools.pyk.postgre` — PostgreSQL 辅助。

### vicPostgreSupport

| 功能 | 说明 |
|---|---|
| `get_connection()` | 获取 pg 连接 |
| `execute(sql, params)` | 执行 SQL |
| `query(sql)` | 查询 |
| 事务辅助 | 事务上下文 / 自动 commit-rollback |

---

## cond

`vools.pyk.cond` — 条件表达式 / `CASE WHEN` 构造器。

### ConditionBuilder

用于构建 `CASE WHEN` / 复杂条件：

| 方法 | 说明 |
|---|---|
| `__init__(base_value, comp='==', sht=True, result_type=None, supp=False)` | 初始化 |
| `.comp` | 比较符属性 |
| `.is_iters` | 是否迭代（数组） |
| `.cover_default` | 是否覆盖默认 |
| `.conds` | 当前条件列表 |
| `.result` / `.results` | 结果 / 结果集 |
| `.case(value, result, comp=None)` | 追加一个 CASE 分支 |
| `.cases(*args)` | 批量追加 |
| `.when(value, result, logic=None)` | 追加 WHEN 分支 |
| `.whens(*args)` | 批量追加 WHEN |
| `.otherwise(default)` | ELSE 分支 |

---

## configs

`vools.pyk.configs` — 配置管理、密钥加解密、PostgreSQL 凭据。

### 函数

| 名称 | 说明 |
|---|---|
| `secret_key() -> bytes` | 取密钥（用于加解密） |
| `encrypt_secret(plaintext, way=None) -> str` | 加密明文 |
| `decrypt_secret(ciphertext) -> str` | 解密密文 |
| `pg_credentials() -> (db, user, password)` | 取 PostgreSQL 凭据（环境变量） |
| `share_dir() -> str` | 共享目录（HDFS 或本地） |
| `default_db() -> str` | 默认数据库名 |
| `upon_sql_file() -> str` | LookUpon 初始化 SQL 文件路径 |
| `pg_jar() -> str` | PostgreSQL JDBC jar 路径 |
| `load_config() -> dict` | 加载配置文件（INI / YAML / JSON） |
| `get_spark_conf(app_name=None, **overrides) -> dict` | 生成 SparkConf 字典 |

---

## patch

`vools.pyk.patch` — monkey-patch 安装。

### 函数

| 名称 | 说明 |
|---|---|
| `install_patch()` | 把 pyk 扩展挂到原生 `DataFrame` / `SparkSession` / `Column`；**幂等** |

patch 后：

```python
# 原生 DataFrame 多了这些方法
df.show_ex(50)
df.unique_by("date")
df.grouping_sets(...)
```

---

## tools

`vools.pyk.tools` — `vicTools` 聚合类，一站式工具入口。

将 `core` / `df` / `text` / `tb` / `compare` / `postgre` / `look_upon` 的工具函数
统一聚合到 `vicTools`，通过单实例访问：

```python
from vools.pyk.tools import vicTools
t = vicTools()
t.get_spark("app")
t.getCols("db.tbl")
```

---

## look_upon

`vools.pyk.look_upon` — **LookUpon 任务调度**（PostgreSQL 队列）。

完整文档见 **[LOOKUPON.md](LOOKUPON.md)**（32 列 schema、状态机、DAG / 跨表依赖、
重试、Worker 竞争锁、**CLI 执行通道**等）。

关键符号：

| 名称 | 说明 |
|---|---|
| `LookUpon` | 调度器主类 |
| `cli_execute(payload, timeout_sec, capture)` | **CLI 执行通道**（模块级，Python subprocess 调用外部 CLI） |
| `LANGUAGE_DEFAULT_CMD` | `dict`：语言 → 默认命令前缀（`python` / `scala` / `java` / `shell` / `sql` / `r` / `node` / `go` / `julia` / `ruby` / `perl` / `php` / `dotnet` / `spark-submit` …） |
| `LANGUAGE_EXTENSIONS` | `dict`：语言 → 脚本扩展名 |
| `_detect_language(task_type)` | 把 `task_type` 归一化为语言 key（大小写不敏感，支持别名） |
| `_find_executable(prefix)` | PATH 查找解释器（Windows 自动补 `.exe`/`.bat`/`.cmd`） |

CLI 执行通道**无语言枚举限制**：`task_type` 是 `VARCHAR(32)` 且无 CHECK 约束，
Scala / Java / R / Go / Node / Shell / SQL 等都可自由填。找不到解释器时明确报错，
不静默跳过。

---

## 顶层导出（`vools.pyk`）

| 名称 | 说明 |
|---|---|
| `__version__` | 包版本 |
| `install_patch()` | 安装 monkey-patch |
| `is_available()` | 检查 pyspark 是否可用 |
| `get_spark(app_name, master, **conf)` | 获取全局 SparkSession |
| 子模块 | `core`, `df`, `text`, `tb`, `compare`, `postgre`, `cond`, `patch`, `configs`, `look_upon`, `tools` |
