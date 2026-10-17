# vools.pyk — 大数据/Spark 桥接层

`vools.pyk` 是 vools 的**可选**大数据子包，依赖 `pyspark` + `pandas`。核心
安装下不可用（`vools.pyk.is_available()` 返回 False），按需 `pip install vools-pyk` 启用。

## 核心类 / 函数

| 名称 | 类型 | 说明 |
|---|---|---|
| `get_spark(app_name="vools")` | 工厂函数 | 惰性创建 SparkSession（单例） |
| `is_available()` | 函数 | 检测 pyspark/pandas 是否已安装 |
| `install_patch()` | 函数 | 安装 DataFrame 链式扩展补丁 |
| `ConditionBuilder` (cond) | 类 | legacy 条件构建器：链式 `when/case/otherwise` |
| `vicTools` (tools) | 类 | legacy 聚合工具类（含 pyspark 方法） |

## 使用示例

```python
from vools.pyk import get_spark

spark = get_spark(app_name="demo")
df = spark.createDataFrame([(1, "a"), (2, "b")], ["id", "name"])
df.show()
```

## 规则与约定

- `pyk` 由独立分包 `vools-pyk` 提供，不随 vools 核心分发。
- 核心包通过 `vools/__init__.py` 的 `__getattr__('pyk')` 惰性导入，
  未安装时抛 `AttributeError` 而非 `ModuleNotFoundError`。
- 模块级 `__all__` 显式列出公开符号（版本 + 3 工具函数 + 8 子模块）。
