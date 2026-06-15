# Spark RDD 算子与 vools-reactive 集成分析

## 一、Spark RDD 算子体系概览

### 1.1 转换算子（Transformations）

| 分类 | Spark RDD 算子 | 功能描述 |
|------|----------------|----------|
| **基础转换** | `map`, `filter`, `flatMap`, `mapPartitions`, `mapPartitionsWithIndex` | 数据转换和过滤 |
| **采样** | `sample`, `takeSample` | 随机采样 |
| **集合操作** | `union`, `intersection`, `distinct`, `subtract`, `cartesian` | 集合运算 |
| **键值操作** | `groupByKey`, `reduceByKey`, `aggregateByKey`, `sortByKey`, `foldByKey`, `combineByKey`, `mapValues`, `flatMapValues`, `keyBy` | 键值对聚合 |
| **连接操作** | `join`, `leftOuterJoin`, `rightOuterJoin`, `fullOuterJoin`, `cogroup` | 数据集连接 |
| **排序** | `sortBy`, `sortByKey` | 排序 |
| **分区操作** | `coalesce`, `repartition`, `partitionBy`, `glom` | 分区管理 |
| **拉链操作** | `zip`, `zipWithIndex`, `zipWithUniqueId` | 元素配对 |
| **缓存** | `cache`, `persist`, `checkpoint` | 持久化 |

### 1.2 行动算子（Actions）

| 分类 | Spark RDD 算子 | 功能描述 |
|------|----------------|----------|
| **聚合** | `reduce`, `aggregate`, `fold` | 聚合计算 |
| **收集** | `collect`, `take`, `takeOrdered`, `first` | 获取数据 |
| **计数** | `count`, `countByKey`, `countByValue` | 计数 |
| **统计** | `min`, `max`, `sum`, `mean`, `variance`, `stdev` | 统计计算 |
| **遍历** | `foreach`, `foreachPartition` | 遍历执行 |
| **查找** | `lookup` | 按键查找 |
| **输出** | `saveAsTextFile`, `saveAsSequenceFile`, `saveAsObjectFile` | 数据持久化 |

---

## 二、vools-reactive 现有操作符

### 2.1 已实现的操作符

```python
# 基础操作符
map, filter, flat_map, concat_map, switch_map
concat, merge, zip, combine_latest, with_latest_from

# 选择操作
take, skip, take_while, skip_while, take_until, skip_until
first, last, element_at, take_last, skip_last

# 去重
distinct, distinct_until_changed

# 时间相关
debounce, throttle_first, throttle_latest, timeout, timestamp, time_interval

# 错误处理
catch, retry, on_error_return, on_error_resume_next, retry_when, retry_with_backoff

# 聚合操作
reduce, scan, count, sum, average, minimum, maximum, all, any, contains

# 转换操作
to_list, to_map, to_set, buffer, window

# 工具操作
tap, delay, start_with, end_with, ignore_elements, sample

# 高级操作
observe_on, subscribe_on, flat_map_latest, switch, amb

# 背压处理
backpressure_buffer, backpressure_drop, backpressure_error, backpressure_latest

# 创新功能
circuit_breaker, debounce_evolution, cache, parallel
```

---

## 三、Spark RDD 算子与 vools-reactive 映射分析

### 3.1 可直接映射的算子（已有对应实现）

| Spark RDD 算子 | vools-reactive 操作符 | 匹配度 | 说明 |
|----------------|----------------------|--------|------|
| `map` | `ops.map` | ✅ 完全匹配 | 一对一映射 |
| `filter` | `ops.filter` | ✅ 完全匹配 | 过滤元素 |
| `flatMap` | `ops.flat_map` | ✅ 完全匹配 | 扁平映射 |
| `reduce` | `ops.reduce` | ✅ 完全匹配 | 聚合归约 |
| `count` | `ops.count` | ✅ 完全匹配 | 计数 |
| `sum` | `ops.sum` | ✅ 完全匹配 | 求和 |
| `first` | `ops.first` | ✅ 完全匹配 | 首个元素 |
| `last` | `ops.last` | ✅ 完全匹配 | 最后元素 |
| `take` | `ops.take` | ✅ 完全匹配 | 取前N个 |
| `skip` | `ops.skip` | ✅ 完全匹配 | 跳过前N个 |
| `distinct` | `ops.distinct` | ✅ 完全匹配 | 去重 |
| `union` | `ops.concat` | ✅ 等价 | 合并多个流 |
| `zip` | `ops.zip` | ✅ 完全匹配 | 拉链操作 |
| `sample` | `ops.sample` | ✅ 完全匹配 | 采样 |
| `cache` | `ops.cache` | ✅ 完全匹配 | 缓存 |

### 3.2 需要扩展实现的算子（有部分匹配但不完整）

| Spark RDD 算子 | 现有基础 | 缺失功能 | 推荐方案 |
|----------------|----------|----------|----------|
| `mapPartitions` | `ops.map` | 分区级处理 | 新增 `map_partitions` |
| `mapPartitionsWithIndex` | `ops.map` | 分区索引访问 | 新增 `map_partitions_with_index` |
| `groupByKey` | `ops.reduce`, `scan` | 按键分组聚合 | 新增 `group_by_key` |
| `reduceByKey` | `ops.reduce` | 按键归约 | 新增 `reduce_by_key` |
| `aggregateByKey` | `ops.reduce`, `scan` | 自定义聚合 | 新增 `aggregate_by_key` |
| `sortByKey` | `ops.window` | 流式排序 | 新增 `sort_by_key`（窗口内排序） |
| `sortBy` | `ops.window` | 自定义排序 | 新增 `sort_by` |
| `join` | `ops.combine_latest` | 键值连接语义 | 新增 `join` 系列操作符 |
| `cogroup` | `ops.combine_latest` | 多流分组 | 新增 `cogroup` |
| `intersection` | `ops.distinct` | 交集计算 | 新增 `intersection` |
| `subtract` | `ops.filter` | 差集计算 | 新增 `subtract` |
| `cartesian` | - | 笛卡尔积 | 新增 `cartesian` |
| `coalesce` | - | 分区合并 | 新增 `coalesce`（背压场景） |
| `repartition` | - | 重新分区 | 新增 `repartition`（并行场景） |
| `glom` | - | 分区转换为数组 | 新增 `glom` |
| `zipWithIndex` | `ops.scan` | 索引配对 | 新增 `zip_with_index` |
| `zipWithUniqueId` | `ops.scan` | 唯一ID配对 | 新增 `zip_with_unique_id` |

### 3.3 需要特殊处理的行动算子

| Spark RDD 算子 | Reactive 等价模式 | 说明 |
|----------------|-------------------|------|
| `collect` | `to_list().subscribe()` | 收集所有元素到列表 |
| `countByKey` | `to_map()` + 计数逻辑 | 按键计数 |
| `countByValue` | `to_map()` + 计数逻辑 | 按值计数 |
| `foreach` | `subscribe(on_next=fn)` | 遍历每个元素 |
| `foreachPartition` | `subscribe` + 批处理 | 按批处理 |
| `lookup` | `filter` + `to_list` | 按条件查找 |
| `min` | `ops.minimum` | 最小值 |
| `max` | `ops.maximum` | 最大值 |
| `mean` | `ops.average` | 平均值 |
| `variance` | - | 方差计算（需新增） |
| `stdev` | - | 标准差（需新增） |
| `aggregate` | `ops.reduce` + `scan` | 自定义聚合 |
| `fold` | `ops.reduce` | 带初始值归约 |
| `takeOrdered` | `sort_by` + `take` | 排序后取前N |
| `saveAsTextFile` | `subscribe` + 文件写入 | 输出到文件 |

---

## 四、推荐集成的算子优先级

### P0 - 高优先级（立即集成）

| 算子 | 理由 |
|------|------|
| `map_partitions` | 支持批量处理，提升性能 |
| `group_by_key` | 键值数据处理基础 |
| `reduce_by_key` | 常用聚合操作 |
| `sort_by` / `sort_by_key` | 流式排序需求常见 |
| `join` | 多数据源关联 |
| `zip_with_index` | 索引追踪 |

### P1 - 中优先级（后续集成）

| 算子 | 理由 |
|------|------|
| `aggregate_by_key` | 复杂聚合场景 |
| `cogroup` | 多流分组 |
| `intersection` | 集合操作 |
| `subtract` | 集合操作 |
| `cartesian` | 笛卡尔积 |
| `variance` / `stdev` | 统计计算 |

### P2 - 低优先级（按需集成）

| 算子 | 理由 |
|------|------|
| `coalesce` / `repartition` | 分区管理，特定场景使用 |
| `glom` | 分区数组转换 |
| `saveAsTextFile` | 输出操作 |
| `countByKey` / `countByValue` | 可通过组合实现 |

---

## 五、集成方案建议

### 5.1 新增操作符实现位置

```
vools/
└── reactive/
    ├── operators.py          # 核心操作符（新增）
    ├── extended_operators.py # 扩展操作符（新增）
    └── spark_compat.py       # Spark 兼容层（建议新增）
```

### 5.2 实现策略

1. **保持响应式语义**：RDD 是批处理模型，Reactive 是流式模型，需要适配语义差异
2. **窗口化处理**：对于需要完整数据集的操作（如排序、聚合），使用窗口操作
3. **背压兼容**：所有新增操作符需考虑背压处理
4. **curry 支持**：保持与 vools curry 系统的集成

### 5.3 示例：`group_by_key` 实现思路

```python
def group_by_key(key_fn: Callable = None) -> Callable[[Observable], Observable]:
    """
    按键分组操作符
    
    Example:
        >>> obs = Observable.from_iterable([("a", 1), ("b", 2), ("a", 3)])
        >>> obs.pipe(ops.group_by_key()).subscribe(print)
        ("a", [1, 3])
        ("b", [2])
    """
    def operator(source: Observable) -> Observable:
        def subscribe(observer: Observer) -> Subscription:
            groups = defaultdict(list)
            
            def on_next(value):
                key = key_fn(value) if key_fn else value[0]
                groups[key].append(value[1] if isinstance(value, tuple) else value)
            
            def on_completed():
                for key, values in groups.items():
                    observer.on_next((key, values))
                observer.on_completed()
            
            return source.subscribe(on_next=on_next, on_completed=on_completed)
        
        return Observable(subscribe)
    
    return operator
```

---

## 六、总结

### 已覆盖的 Spark RDD 功能（约 40%）

- ✅ 基础转换：map, filter, flatMap
- ✅ 基础聚合：reduce, count, sum, min, max, avg
- ✅ 选择操作：take, skip, first, last
- ✅ 集合操作：union/concat, distinct
- ✅ 拉链操作：zip

### 需要补充的关键功能（约 60%）

- 🔄 键值聚合：groupByKey, reduceByKey, aggregateByKey
- 🔄 排序操作：sortBy, sortByKey
- 🔄 连接操作：join, cogroup
- 🔄 集合操作：intersection, subtract, cartesian
- 🔄 分区操作：mapPartitions, coalesce, glom
- 🔄 统计操作：variance, stdev

通过系统地集成这些算子，可以使 vools-reactive 更接近 Spark RDD 的表达能力，同时保持响应式流式处理的优势。
