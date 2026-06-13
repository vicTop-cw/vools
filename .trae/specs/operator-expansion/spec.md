# vools-reactive 算子扩展计划 - Product Requirement Document

## Overview
- **Summary**: 基于 rx-rust 的算子扩展计划，在 vools-reactive 中扩展 35+ 个算子，填补统计聚合、滚动窗口、累积变换、排序 Top-N、None 值处理等能力缺口，同时补全现有 Observable API 的一致性。所有扩展遵循 `ops.map/filter/reduce` 等已有算子的模式，保证可组合性与链式调用支持。
- **Purpose**: vools-reactive 当前约 30 个操作符，覆盖基本变换/过滤/聚合/时间能力，但在实际数据分析场景下仍需手写大量样板代码。扩展后可直接满足 85%+ 的单流/有限序列数据处理需求。
- **Target Users**: 使用 vools-reactive 做流处理 / 事件驱动 / 有限序列数据分析的 Python 开发者；对响应式编程 + 数据处理一体化有需求的工程团队。

## Goals
1. **G1 统计聚合补全** — 补齐 `min/max/average/median/std/variance/quantile/arg_min/arg_max/n_unique/any` 共 11 个统计聚合算子
2. **G2 滚动窗口** — 新增 `rolling_min/rolling_max/rolling_sum/rolling_mean` 4 个滚动聚合算子
3. **G3 累积变换** — 新增 `cum_sum/cum_min/cum_max/cum_mean/cum_prod` 5 个累积算子
4. **G4 排序 Top-N** — 新增 `sort/top_k/bottom_k` 3 个有限流排序算子
5. **G5 绑定补全** — 补全 `distinct/element_at/take_while/skip_while/take_last/skip_last/switch_map/combine_latest/catch_error/retry/retry_when/distinct_until_changed/ignore_elements/publish/share` 共 14 个算子
6. **G6 None / 数学工具** — 新增 `drop_none/fill_none/abs/clamp` 4 个工具算子
7. **G7 嵌套流展开** — 新增 `explode/flatten` 2 个嵌套流展开算子
8. **G8 API 统一** — 所有新增算子支持 Observable 链式调用和 pipe API，与现有风格保持一致

## Non-Goals (Out of Scope)
- **NG1**: 不实现 DataFrame 列式操作（`select / with_columns / drop / rename / melt / pivot / transpose`），vools-reactive 是流式响应式框架
- **NG2**: 不实现 Join 系列（`left_join / right_join / outer_join / anti_join / semi_join`），需要 KV Observable 基础架构
- **NG3**: 不实现 HyperLogLog 近似统计、SQL 窗口函数等高级功能，留待后续迭代
- **NG4**: 不修改核心 Observable 架构设计，只在其上新增算子
- **NG5**: 不引入第三方依赖（如 numpy/scipy），所有统计用纯 Python 实现

## Background & Context
### 当前架构
```
Observable (公共 API)
  ├─ ops 模块: 操作符函数（map/filter/reduce/scan/...）
  └─ Observable.pipe(): 管道组合 API
```
- 现有约 30 个操作符，覆盖变换/过滤/聚合/组合/时间
- 扩展空间：统计聚合、滚动窗口、累积变换、排序等

## Functional Requirements

### FR-1: 统计聚合补全（G1）
新增方法：
- `min()` — 发射流中最小值，空流不发射
- `max()` — 发射流中最大值，空流不发射
- `average()` / `mean()` — 发射数值均值
- `median()` — 发射中位数（需缓冲全部值，仅有限流适用）
- `variance(ddof=0)` — 发射方差
- `std(ddof=0)` — 发射标准差
- `quantile(q)` — 发射分位数（q∈[0,1]）
- `arg_min()` — 发射最小值的下标索引
- `arg_max()` — 发射最大值的下标索引
- `n_unique()` — 发射不重复值的数量
- `any(predicate)` — 任一值满足谓词则发射 True

### FR-2: 滚动窗口（G2）
- `rolling_min(window_size)` — 滚动最小值
- `rolling_max(window_size)` — 滚动最大值
- `rolling_sum(window_size)` — 滚动求和
- `rolling_mean(window_size)` — 滚动均值

### FR-3: 累积变换（G3）
- `cum_sum()` — 累积求和
- `cum_min()` — 累积最小值
- `cum_max()` — 累积最大值
- `cum_mean()` — 累积均值
- `cum_prod()` — 累积乘积

### FR-4: 排序 Top-N（G4）
- `sort(key_fn=None, reverse=False)` — 排序后依次发射
- `top_k(k, key_fn=None)` — 发射前 k 个最大值
- `bottom_k(k, key_fn=None)` — 发射最小的 k 个值

### FR-5: 绑定补全（G5）
- `distinct()` — 去重
- `element_at(idx)` — 发射第 idx 个值
- `take_while(predicate)` — 满足谓词时取
- `skip_while(predicate)` — 不满足谓词前跳过
- `take_last(n)` — 取最后 n 个值
- `skip_last(n)` — 跳过最后 n 个值
- `switch_map(mapper)` — 切换到新的内层 Observable
- `combine_latest(other, combiner)` — 组合两方最新值
- `catch_error(handler)` — 异常处理
- `retry(count)` — 重试
- `retry_when(trigger_factory)` — 自定义重试策略
- `distinct_until_changed()` — 仅当值与上一个不同时发射
- `ignore_elements()` — 不发射任何值
- `publish()` / `share()` — 多播

### FR-6: None 值处理 & 数学工具（G6）
- `drop_none()` — 过滤 None
- `fill_none(default_value)` — 替换 None
- `abs()` — 绝对值
- `clamp(min_val, max_val)` — 值域限制

### FR-7: 嵌套流展开（G7）
- `explode()` — 展开 Iterable
- `flatten()` — 展开 Observable-like

### FR-8: API 统一（G8）
- 所有新算子支持 Observable 链式调用
- 所有新算子支持 pipe API
- 所有方法有中文 docstring

## Non-Functional Requirements
- **NFR-1**: 所有算子性能不应比手写等价链慢 10% 以上
- **NFR-2**: 所有新算子必须与现有 pipe API 兼容
- **NFR-3**: 异常必须路由到 on_error 回调
- **NFR-4**: 需缓冲全部值的算子需在 docstring 标注内存注意事项
- **NFR-5**: 零依赖，仅使用标准库

## Constraints
- 技术：修改仅限 `vools/reactive/operators.py` 与新测试文件
- 兼容性：所有新增方法不破坏现有 API
- 依赖：Python 3.8+ 标准库
- 平台：纯 Python 实现，跨平台通用

## Acceptance Criteria
### AC-1: 统计聚合算子行为正确
- **Given**: 有限长度数值 Observable
- **When**: 调用 `.min()` / `.max()` / `.average()`
- **Then**: 订阅者收到正确统计值；空流不发射
- **Verification**: `programmatic`

### AC-2: median/quantile 正确计算
- **Given**: 有限数值 Observable
- **When**: 调用 `.median()` 或 `.quantile(0.75)`
- **Then**: 返回值与 `statistics.median` 一致
- **Verification**: `programmatic`

### AC-3: 滚动窗口算子输出正确
- **Given**: Observable `[1, 2, 3, 4, 5]` 调用 `.rolling_sum(3)`
- **When**: 订阅后接收
- **Then**: 发射 `[1, 3, 6, 9, 12]`
- **Verification**: `programmatic`

### AC-4: 累积算子正确性
- **Given**: Observable `[1, 2, 3, 4]`
- **When**: 调用 `.cum_sum()` / `.cum_max()` / `.cum_prod()`
- **Then**: 分别发射 `[1, 3, 6, 10]` / `[1, 2, 3, 4]` / `[1, 2, 6, 24]`
- **Verification**: `programmatic`

### AC-5: sort/top_k/bottom_k 正确排序
- **Given**: Observable `[5, 2, 8, 1, 9, 3]`
- **When**: 调用 `.sort()` / `.top_k(2)` / `.bottom_k(2)`
- **Then**: 分别发射 `[1, 2, 3, 5, 8, 9]` / `[9, 8]` / `[1, 2]`
- **Verification**: `programmatic`

### AC-6: None 值处理正确
- **Given**: `Observable.of(1, None, 2, -3, None, 4)`
- **When**: 调用 `.drop_none()` / `.fill_none(0)` / `.abs()` / `.clamp(0, 3)`
- **Then**: 分别发射 `[1, 2, -3, 4]` / `[1, 0, 2, -3, 0, 4]` / `[1, 2, 3, 4]` / `[1, 2, 3, 3]`
- **Verification**: `programmatic`

### AC-7: 链式组合性 & pipe 兼容
- **Given**: 任意新算子组合
- **When**: 通过 `.pipe()` 传递
- **Then**: 组合结果与直接链式调用相同
- **Verification**: `programmatic`

### AC-8: 代码风格一致性
- **Given**: 新增算子代码
- **When**: 评审者阅读
- **Then**: 命名、docstring 风格与现有一致
- **Verification**: `human-judgment`

## Open Questions
- [ ] Q1: 是否需要在模块顶层暴露所有新算子的函数形式？
- [ ] Q2: retry_when 是否简化为 retry(count, delay_seconds)？
