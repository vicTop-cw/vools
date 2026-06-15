# Polars API 与 vools-reactive 集成分析

## 一、Polars 核心架构

### 1.1 三大核心类型

| 类型 | 描述 | 特点 |
|------|------|------|
| **Expr** | 表达式 | 惰性求值，链式调用，支持向量化操作 |
| **DataFrame** | 数据框 | 二维表格，列式存储，多列操作 |
| **Series** | 系列 | 单列数据，向量化计算 |

### 1.2 Polars 表达式分类

```
Polars Expr API
├── 计算/数学 (Computation)
├── 聚合 (Aggregation)  
├── 字符串操作 (String)
├── 时间序列 (Temporal)
├── 列表操作 (List)
├── 结构操作 (Struct)
├── 条件表达式 (Conditional)
├── 排序 (Sorting)
├── 窗口函数 (Window)
└── 滚动窗口 (Rolling)
```

---

## 二、Polars Expr 完整方法列表

### 2.1 计算与数学操作

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `abs` | 绝对值 | `ops.map(abs)` | ✅ 可组合 |
| `sqrt` | 平方根 | `ops.map(math.sqrt)` | ✅ 可组合 |
| `exp` | 指数函数 | `ops.map(math.exp)` | ✅ 可组合 |
| `log`, `log10`, `log1p` | 对数函数 | `ops.map(math.log)` | ✅ 可组合 |
| `sin`, `cos`, `tan` | 三角函数 | `ops.map(math.sin)` | ✅ 可组合 |
| `arcsin`, `arccos`, `arctan` | 反三角函数 | - | 🔄 需新增 |
| `sinh`, `cosh`, `tanh` | 双曲函数 | - | 🔄 需新增 |
| `cbrt` | 立方根 | - | 🔄 需新增 |
| `ceil` | 向上取整 | - | 🔄 需新增 |
| `floor` | 向下取整 | - | 🔄 需新增 |
| `round` | 四舍五入 | - | 🔄 需新增 |
| `trunc` | 截断 | - | 🔄 需新增 |
| `pow` | 幂运算 | `ops.map(lambda x: x**n)` | ✅ 可组合 |
| `clip` | 值域限制 | - | 🔄 需新增 |
| `sign` | 符号函数 | - | 🔄 需新增 |

### 2.2 累计计算（Cumulative）

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `cum_sum` | 累计求和 | `ops.scan(add, 0)` | ✅ 等价 |
| `cum_prod` | 累计乘积 | `ops.scan(mul, 1)` | ✅ 可组合 |
| `cum_max` | 累计最大值 | `ops.scan(max)` | ✅ 可组合 |
| `cum_min` | 累计最小值 | `ops.scan(min)` | ✅ 可组合 |
| `cum_count` | 累计计数 | `ops.scan(lambda acc, _: acc + 1, 0)` | ✅ 可组合 |
| `cumulative_eval` | 滑动窗口累计 | - | 🔄 需新增 |

### 2.3 聚合操作（Aggregation）

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `sum` | 求和 | `ops.sum` | ✅ 已实现 |
| `mean` | 平均值 | `ops.average` | ✅ 已实现 |
| `median` | 中位数 | - | 🔄 需新增 |
| `std` | 标准差 | - | 🔄 需新增 |
| `var` | 方差 | - | 🔄 需新增 |
| `min` | 最小值 | `ops.minimum` | ✅ 已实现 |
| `max` | 最大值 | `ops.maximum` | ✅ 已实现 |
| `count` | 计数 | `ops.count` | ✅ 已实现 |
| `n_unique` | 唯一值数量 | `ops.distinct` + count | ✅ 可组合 |
| `first` | 首个值 | `ops.first` | ✅ 已实现 |
| `last` | 最后值 | `ops.last` | ✅ 已实现 |
| `agg_groups` | 聚合组索引 | - | 🔄 需新增 |

### 2.4 排序与索引操作

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `sort` | 排序 | - | 🔄 需新增（窗口） |
| `arg_sort` | 排序索引 | - | 🔄 需新增 |
| `arg_max` | 最大值索引 | - | 🔄 需新增 |
| `arg_min` | 最小值索引 | - | 🔄 需新增 |
| `top_k` | Top K 元素 | - | 🔄 需新增 |
| `bottom_k` | Bottom K 元素 | - | 🔄 需新增 |
| `sort_by` | 多列排序 | - | 🔄 需新增 |
| `arg_unique` | 唯一值首次索引 | - | 🔄 需新增 |
| `is_last` | 是否最后出现 | - | 🔄 需新增 |

### 2.5 过滤与选择操作

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `filter` | 条件过滤 | `ops.filter` | ✅ 已实现 |
| `drop_nulls` | 删除空值 | - | 🔄 需新增 |
| `drop_nans` | 删除 NaN | - | 🔄 需新增 |
| `fill_null` | 填充空值 | - | 🔄 需新增 |
| `fill_nan` | 填充 NaN | - | 🔄 需新增 |
| `interpolate` | 插值填充 | - | 🔄 需新增 |
| `is_null`, `is_not_null` | 空值判断 | - | 🔄 需新增 |
| `is_nan`, `is_not_nan` | NaN 判断 | - | 🔄 需新增 |
| `is_in` | 成员判断 | - | 🔄 需新增 |
| `arg_true` | True 索引 | - | 🔄 需新增 |

### 2.6 类型转换操作

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `cast` | 类型转换 | `ops.map(type_cast)` | ✅ 可组合 |
| `to_physical` | 转物理类型 | - | 🔄 需新增 |
| `to_list` | 转列表 | `ops.to_list` | ✅ 已实现 |
| `hash` | 哈希值 | - | 🔄 需新增 |

### 2.7 字符串操作

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `str.contains` | 包含判断 | - | 🔄 需新增 |
| `str.replace` | 替换 | - | 🔄 需新增 |
| `str.replace_all` | 全局替换 | - | 🔄 需新增 |
| `str.to_lowercase` | 转小写 | `ops.lower` | ✅ 已实现 |
| `str.to_uppercase` | 转大写 | `ops.upper` | ✅ 已实现 |
| `str.strip` | 去除空白 | `ops.strip` | ✅ 已实现 |
| `str.split` | 分割 | `ops.split` | ✅ 已实现 |
| `str.concat` | 拼接 | - | 🔄 需新增 |
| `str.lengths` | 长度 | - | 🔄 需新增 |
| `str.slice` | 切片 | - | 🔄 需新增 |
| `str.extract` | 提取 | - | 🔄 需新增 |
| `str.to_integer` | 转整数 | - | 🔄 需新增 |
| `str.to_decimal` | 转小数 | - | 🔄 需新增 |

### 2.8 日期时间操作

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `dt.year`, `dt.month`, `dt.day` | 日期组件 | - | 🔄 需新增 |
| `dt.hour`, `dt.minute`, `dt.second` | 时间组件 | - | 🔄 需新增 |
| `dt.day_of_week` | 星期几 | - | 🔄 需新增 |
| `dt.truncate` | 日期截断 | - | 🔄 需新增 |
| `dt.offset_by` | 日期偏移 | - | 🔄 需新增 |
| `dt.days`, `dt.seconds` | 时间差 | - | 🔄 需新增 |

### 2.9 列表操作

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `list.any`, `list.all` | 列表逻辑 | - | 🔄 需新增 |
| `list.sum`, `list.mean` | 列表统计 | - | 🔄 需新增 |
| `list.min`, `list.max` | 列表极值 | - | 🔄 需新增 |
| `list.lengths` | 列表长度 | - | 🔄 需新增 |
| `list.contains` | 列表包含 | - | 🔄 需新增 |
| `list.join` | 列表拼接 | - | 🔄 需新增 |
| `list.get` | 列表取值 | - | 🔄 需新增 |
| `list.unique` | 列表去重 | `ops.distinct` | ✅ 可组合 |
| `list.explode` | 列表展开 | `ops.flat_map` | ✅ 等价 |

### 2.10 窗口与分组操作

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `over` | 窗口表达式 | - | 🔄 需新增 |
| `rolling_*` | 滚动窗口 | `ops.window` | ✅ 可扩展 |
| `ewm_mean` | 指数加权移动平均 | - | 🔄 需新增 |
| `ewm_std` | 指数加权标准差 | - | 🔄 需新增 |
| `ewm_var` | 指数加权方差 | - | 🔄 需新增 |

### 2.11 统计与分布操作

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `entropy` | 熵 | - | 🔄 需新增 |
| `skew` | 偏度 | - | 🔄 需新增 |
| `kurtosis` | 峰度 | - | 🔄 需新增 |
| `dot` | 点积 | - | 🔄 需新增 |
| `mode` | 众数 | - | 🔄 需新增 |
| `quantile` | 分位数 | - | 🔄 需新增 |
| `product` | 乘积 | `ops.reduce(lambda a, b: a * b)` | ✅ 可组合 |
| `corr` | 相关系数 | - | 🔄 需新增 |
| `cov` | 协方差 | - | 🔄 需新增 |

### 2.12 结构操作（Struct）

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `struct.field` | 结构体字段 | - | 🔄 需新增 |
| `struct.rename` | 重命名字段 | - | 🔄 需新增 |
| `struct.unnest` | 展开结构体 | - | 🔄 需新增 |

### 2.13 其他操作

| Polars 方法 | 功能 | vools-reactive 对应 | 匹配度 |
|-------------|------|-------------------|--------|
| `alias` | 别名 | `ops.map` with naming | ✅ 可组合 |
| `exclude` | 排除列 | - | 🔄 需新增 |
| `keep_name` | 保留名称 | - | 🔄 需新增 |
| `name.prefix` | 名称前缀 | - | 🔄 需新增 |
| `name.suffix` | 名称后缀 | - | 🔄 需新增 |
| `inspect` | 调试检查 | `ops.tap` | ✅ 已实现 |
| `hash` | 哈希 | - | 🔄 需新增 |
| `null_count` | 空值计数 | - | 🔄 需新增 |

---

## 三、Polars 函数（Functions）

### 3.1 水平聚合函数

| Polars 函数 | 功能 | vools-reactive 对应 |
|-------------|------|-------------------|
| `sum_horizontal` | 水平求和 | - |
| `max_horizontal` | 水平最大值 | - |
| `min_horizontal` | 水平最小值 | - |
| `mean_horizontal` | 水平平均值 | - |
| `any_horizontal` | 水平任意 | - |
| `all_horizontal` | 水平全部 | - |

### 3.2 条件函数

| Polars 函数 | 功能 | vools-reactive 对应 |
|-------------|------|-------------------|
| `when`/`then`/`otherwise` | 条件表达式 | `ops.iif` | ✅ 可扩展 |
| `coalesce` | 取第一个非空 | - | 🔄 需新增 |

### 3.3 数组/列表函数

| Polars 函数 | 功能 | vools-reactive 对应 |
|-------------|------|-------------------|
| `concat_list` | 拼接为列表 | - |
| `list` | 创建列表 | `ops.to_list` |
| `struct` | 创建结构体 | - |

### 3.4 其他重要函数

| Polars 函数 | 功能 | vools-reactive 对应 |
|-------------|------|-------------------|
| `col` | 列引用 | - |
| `lit` | 字面量 | `Observable.just` |
| `fold` | 折叠 | `ops.reduce` |
| `map` | 映射 | `ops.map` |
| `cum_reduce` | 累计折叠 | `ops.scan` |
| `cov` | 协方差 | - |
| `corr` | 相关系数 | - |

---

## 四、vools-reactive 已有能力 vs Polars

### 4.1 完全覆盖

| 功能 | Polars | vools-reactive |
|------|--------|----------------|
| 基础映射 | `map` | `ops.map` ✅ |
| 过滤 | `filter` | `ops.filter` ✅ |
| 扁平映射 | `explode` | `ops.flat_map` ✅ |
| 累计求和 | `cum_sum` | `ops.scan` ✅ |
| 聚合求和 | `sum` | `ops.sum` ✅ |
| 聚合平均 | `mean` | `ops.average` ✅ |
| 计数 | `count` | `ops.count` ✅ |
| 最小值 | `min` | `ops.minimum` ✅ |
| 最大值 | `max` | `ops.maximum` ✅ |
| 首个/最后 | `first`/`last` | `ops.first`/`ops.last` ✅ |
| 取前N | `head` | `ops.take` ✅ |
| 跳过N | `tail` | `ops.skip` ✅ |
| 去重 | `unique` | `ops.distinct` ✅ |
| 合并流 | `concat` | `ops.concat` ✅ |
| 采样 | `sample` | `ops.sample` ✅ |
| 缓存 | `cache` | `ops.cache` ✅ |

### 4.2 部分覆盖（需扩展）

| 功能 | Polars | vools-reactive | 差距 |
|------|--------|----------------|------|
| 窗口函数 | `rolling_*`, `over` | `ops.window` | 语义不同 |
| 字符串操作 | `str.*` | `ops.lower`, `ops.upper` | 仅基础 |
| 数学函数 | 三角/对数等 | 需组合 `map` | 仅基础 |
| 排序 | `sort`, `top_k` | - | 完全缺失 |
| 分组聚合 | `group_by` | `group_by_key`（待实现） | 部分缺失 |

### 4.3 完全缺失（需新增）

| 功能类别 | Polars | vools-reactive | 说明 |
|----------|--------|----------------|------|
| **时间序列** | `dt.*` | - | 日期组件、偏移、截断 |
| **列表操作** | `list.*` | - | 列表展开、聚合、搜索 |
| **统计函数** | `std`, `var`, `median` | - | 统计计算 |
| **字符串增强** | `str.*` | 基础支持 | 模式匹配、提取、替换 |
| **类型转换** | `cast` | - | 数据类型转换 |
| **空值处理** | `fill_null`, `drop_nulls` | - | 空值填充/删除 |
| **结构操作** | `struct.*` | - | 结构体操作 |
| **协方差/相关系数** | `cov`, `corr` | - | 统计指标 |
| **滚动窗口增强** | `rolling_*` | `window` | 滚动统计 |
| **水平聚合** | `*_horizontal` | - | 多列水平聚合 |

---

## 五、集成优先级建议

### P0 - 高优先级

| 算子 | 理由 |
|------|------|
| **字符串操作增强** | `str.contains`, `str.replace`, `str.extract` 等 |
| **排序操作** | `sort`, `top_k`, `bottom_k`, `arg_sort` |
| **空值处理** | `fill_null`, `drop_nulls`, `is_null` |
| **分组聚合** | `group_by` (窗口内分组) |
| **数学函数补充** | `floor`, `ceil`, `round`, `sqrt`, `log` 等 |

### P1 - 中优先级

| 算子 | 理由 |
|------|------|
| **类型转换** | `cast` 支持多种数据类型 |
| **时间序列** | `dt.year`, `dt.month`, `dt.truncate` |
| **统计函数** | `std`, `var`, `median`, `quantile` |
| **滚动窗口增强** | `rolling_sum`, `rolling_mean` 等 |
| **列表操作** | `list.*` 系列操作 |

### P2 - 低优先级

| 算子 | 理由 |
|------|------|
| **结构操作** | `struct.*` 系列 |
| **水平聚合** | `sum_horizontal`, `max_horizontal` 等 |
| **协方差/相关系数** | `cov`, `corr` |
| **高级统计** | `skew`, `kurtosis`, `entropy` |

---

## 六、集成架构建议

### 6.1 新增模块结构

```
vools/
└── reactive/
    ├── operators.py           # 核心操作符
    ├── extended_operators.py  # 扩展操作符
    ├── string_ops.py         # 字符串操作（新增）
    ├── temporal_ops.py        # 时间序列操作（新增）
    ├── stats_ops.py          # 统计操作（新增）
    ├── null_ops.py           # 空值处理（新增）
    ├── rolling_ops.py        # 滚动窗口（新增）
    └── polars_compat.py      # Polars 兼容层（新增）
```

### 6.2 示例：`str_contains` 实现

```python
def str_contains(pattern: str, regex: bool = True) -> Callable[[Observable], Observable]:
    """
    检查字符串是否包含指定模式
    
    Example:
        >>> obs = Observable.from_iterable(["hello", "world", "help"])
        >>> obs.pipe(str_contains("ello")).subscribe(print)
        True
        False
        False
    """
    import re
    pattern_fn = re.compile(pattern).search if regex else lambda s: pattern in s
    
    def operator(source: Observable) -> Observable:
        def subscribe(observer: Observer) -> Subscription:
            def on_next(value):
                if isinstance(value, str):
                    observer.on_next(pattern_fn(value) is not None)
                else:
                    observer.on_next(False)
            
            return source.subscribe(on_next=on_next, on_error=observer.on_error, on_completed=observer.on_completed)
        
        return Observable(subscribe)
    
    return operator
```

### 6.3 示例：`rolling_sum` 实现

```python
def rolling_sum(window_size: int) -> Callable[[Observable], Observable]:
    """
    滚动窗口求和
    
    Example:
        >>> obs = Observable.from_iterable([1, 2, 3, 4, 5])
        >>> obs.pipe(rolling_sum(3)).subscribe(print)
        1
        3
        6
        9
        12
    """
    from collections import deque
    
    def operator(source: Observable) -> Observable:
        def subscribe(observer: Observer) -> Subscription:
            window = deque(maxlen=window_size)
            
            def on_next(value):
                window.append(value)
                observer.on_next(sum(window))
            
            return source.subscribe(on_next=on_next, on_error=observer.on_error, on_completed=observer.on_completed)
        
        return Observable(subscribe)
    
    return operator
```

---

## 七、总结

### Polars vs vools-reactive 能力对比

| 维度 | Polars | vools-reactive | 差距 |
|------|--------|----------------|------|
| **数据模型** | DataFrame/列式 | Observable/流式 | 设计不同 |
| **求值策略** | 惰性求值 | 即时推送 | 互补 |
| **表达式系统** | 高度优化 | 函数组合 | 可借鉴 |
| **字符串操作** | 丰富 | 基础 | 需扩展 |
| **时间序列** | 完整 | 缺失 | 需新增 |
| **统计函数** | 完整 | 基础 | 需扩展 |
| **列表操作** | 丰富 | 基础 | 需扩展 |
| **窗口函数** | `over`/`rolling` | `window` | 语义不同 |

### 可复用模式

1. **惰性表达式链**：Polars 的表达式链式调用值得借鉴
2. **窗口函数语义**：`over` 的分组窗口概念可移植
3. **字符串 DSL**：模式匹配表达式可作为 `str_.*` 操作符基础
4. **类型系统**：Polars 的类型转换模式可参考

### 集成价值

通过集成 Polars 的核心能力，vools-reactive 可以：
- 支持更丰富的数据处理场景
- 提供类似 Polars 的表达式风格
- 增强统计分析能力
- 扩展时间序列处理

但需注意：vools-reactive 是流式处理框架，Polars 是批处理框架，两者模型不同，不能简单直接映射，需要根据流式语义重新设计。
