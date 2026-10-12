# vools-pyk

> `vools` 的 PySpark / PostgreSQL 集成子包（**独立分发**）。
> 文档即实现：本包的全部 API、Schema、生命周期均由本仓库文档承载。

`vools-pyk` 是 `vools` 核心库（零 pyspark 依赖、轻量）与 **大数据生态** 的桥接层。
它把 Spark、Hive、PostgreSQL 相关的能力收拢到 `vools.pyk` 命名空间下，**独立发布**，
让核心库保持纯净，同时大数据场景的用户开箱即用。

---

## 安装

### 通过 vools 的 extras 安装（推荐）

```bash
pip install "vools[pyk]"
```

### 直接安装独立包

```bash
pip install vools-pyk
```

### 开发安装（含 pytest）

```bash
pip install "vools-pyk[dev]"
```

### 依赖

| 包 | 最低版本 |
|---|---|
| `vools` | >= 0.7.8 |
| `pyspark` | >= 2.4.3 |
| `pandas` | >= 0.24 |
| `numpy` | >= 1.16 |

支持 Python 3.6 – 3.13。

---

## 快速开始

```python
import vools.pyk as pyk

# 1. 获取 SparkSession（单例，重复调用复用）
spark = pyk.get_spark(app_name="my_pipeline")

# 2. 安装 monkey-patch（把 pyk 的扩展挂到原生 DataFrame/SparkSession）
pyk.install_patch()

# 3. 读数据 + 使用 pyk.df 扩展
df = spark.read.parquet("hdfs:///warehouse/tbl")
df.show_ex(20)          # 更友好的 show
df.unique_by("date").show_ex()
```

---

## 模块一览

| 模块 | 路径 | 用途 |
|---|---|---|
| [core](docs/MODULES.md#core) | `vools.pyk.core` | SparkSession 管理、run_ds、show_*、HDFS 文件元数据、分区检查 |
| [df](docs/MODULES.md#df) | `vools.pyk.df` | `vicDataFrame` 及 DataFrame monkey-patch 扩展 |
| [text](docs/MODULES.md#text) | `vools.pyk.text` | `vicText` 的 pyspark 相关扩展（toDF 等） |
| [tb](docs/MODULES.md#tb) | `vools.pyk.tb` | Hive 表元数据（`vicTableInfo`、getCols、get_partitions） |
| [compare](docs/MODULES.md#compare) | `vools.pyk.compare` | DataFrame 比对（`vicCompare`） |
| [postgre](docs/MODULES.md#postgre) | `vools.pyk.postgre` | PostgreSQL 辅助（`vicPostgreSupport`） |
| [cond](docs/MODULES.md#cond) | `vools.pyk.cond` | 条件表达式 / `CASE WHEN` 构造器（`ConditionBuilder`） |
| [configs](docs/MODULES.md#configs) | `vools.pyk.configs` | 配置管理、密钥加解密、PostgreSQL 凭据 |
| [patch](docs/MODULES.md#patch) | `vools.pyk.patch` | monkey-patch 安装（DataFrame/SparkSession 扩展） |
| [look_upon](docs/LOOKUPON.md) | `vools.pyk.look_upon` | **LookUpon** 任务调度（PostgreSQL 队列，DAG / 跨表依赖 / 重试） |
| [tools](docs/MODULES.md#tools) | `vools.pyk.tools` | `vicTools` 聚合类（一站式工具入口） |

---

## 重要设计

### 独立分发

`vools` 核心库**不依赖 pyspark**。`vools-pyk` 通过 PyPI 独立包分发，
安装后以 `vools.pyk` namespace 包形式合并进 `vools` 的命名空间。

```python
from vools import pyk          # 推荐
import vools.pyk as pyk        # 等价
```

### 懒加载

顶层 `vools.pyk` **不会**在 import 时拉起 pyspark（生产环境可能未安装 / 启动慢）。
只有显式 `import vools.pyk.core` 之类才触发懒加载。

```python
import vools.pyk
print(vools.pyk.is_available())   # True / False，不拉起 pyspark
```

### 可用性检查

```python
import vools.pyk as pyk
if pyk.is_available():
    spark = pyk.get_spark("app")
```

---

## 完整文档

- [LookUpon 任务调度](docs/LOOKUPON.md) —— PostgreSQL 队列、DAG 依赖、跨表依赖、重试、状态机（32 列 schema）
- [模块 API 概览](docs/MODULES.md) —— 各子模块的函数 / 类 / 常量清单
- [变更日志](docs/CHANGELOG.md) —— 版本演进与新增功能

---

## 许可

Apache 2.0。详见 [LICENSE](LICENSE)。
