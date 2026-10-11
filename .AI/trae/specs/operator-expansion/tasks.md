# vools-reactive 算子扩展计划 - The Implementation Plan

> 共 14 个任务，按依赖与复杂度排序。每个任务完成一个独立的算子组。

---

## 依赖结构总览
```
Task 1 (基础框架预备)
 ├─ Task 2 (统计聚合 min/max/avg/median/std/var/quantile/arg_min/arg_max/n_unique/any)
 ├─ Task 3 (滚动窗口 rolling_*)
 ├─ Task 4 (累积变换 cum_*)
 ├─ Task 5 (排序 Top-N: sort/top_k/bottom_k)
 ├─ Task 6 (绑定补全: distinct/element_at/take_while/skip_while/take_last/skip_last)
 ├─ Task 7 (绑定补全: switch_map/combine_latest)
 ├─ Task 8 (绑定补全: catch_error/retry)
 ├─ Task 9 (绑定补全: distinct_until_changed/ignore_elements)
 ├─ Task 10 (绑定补全: publish/share 多播)
 ├─ Task 11 (None/数学工具: drop_none/fill_none/abs/clamp)
 └─ Task 12 (嵌套流展开: explode/flatten)
Task 13 (pipe() 兼容的函数式 API)
Task 14 (综合测试 + 性能回归)
```

---

## [ ] Task 1: 基础设施预备 — 算子实现模式确认
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 阅读当前 `operators.py` 的完整实现，确认操作符注册模式
  - 确认 Observable 的 `pipe()` API 模式
  - 编写算子模板文件，展示如何添加新算子（以 `mean` 为例）
- **Acceptance Criteria Addressed**: G8 / AC-8
- **Test Requirements**:
  - `programmatic` TR-1.1: 新算子模板 `mean` 能通过 `Observable.from_iter([1,2,3]).mean()` 返回 `[2.0]`
  - `programmatic` TR-1.2: 算子同时支持 Observable 链式调用和 pipe API
- **Notes**: 基础架构确认，影响后续所有任务的一致性

---

## [ ] Task 2: 统计聚合算子（G1）
- **Priority**: P0
- **Depends On**: Task 1
- **Description**:
  - `min()`: 扫描时维护最小值，完成时发射
  - `max()`: 对称实现
  - `average()` / `mean()`: 累积 sum 和 n，完成时发射 sum/n
  - `median()`: 缓冲全部值，完成时计算中位数
  - `variance(ddof=0)`: 缓冲全部值计算方差
  - `std(ddof=0)`: 方差的平方根
  - `quantile(q)`: 缓冲排序后线性插值
  - `arg_min() / arg_max()`: 记录首次极值下标
  - `n_unique()`: set 缓冲去重计数
  - `any(predicate)`: 首个满足谓词立即发射 True
- **Acceptance Criteria Addressed**: G1 / AC-1 / AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: `from_iter([5,2,8,1,9,3]).min().collect() == [1]`
  - `programmatic` TR-2.2: `from_iter([1,2,3,4,5]).mean().collect() == [3.0]`
  - `programmatic` TR-2.3: `from_iter([5,3,1,4,2]).median().collect() == [3]`
  - `programmatic` TR-2.4: `from_iter([1,2,1,3,2,4]).n_unique().collect() == [4]`
- **Notes**: 量最大的任务，约 150 行代码

---

## [ ] Task 3: 滚动窗口算子（G2）
- **Priority**: P1
- **Depends On**: Task 1
- **Description**:
  - `rolling_min(window_size)`: deque 维护窗口，每步取 min
  - `rolling_max(window_size)`: 对称实现
  - `rolling_sum(window_size)`: 维护 current_sum，新值加旧值减
  - `rolling_mean(window_size)`: 基于 rolling_sum
- **Acceptance Criteria Addressed**: G2 / AC-3
- **Test Requirements**:
  - `programmatic` TR-3.1: `from_iter([1,2,3,4,5]).rolling_sum(3).collect() == [1, 3, 6, 9, 12]`
  - `programmatic` TR-3.2: `from_iter([5,2,8,1,9]).rolling_min(2).collect() == [5, 2, 2, 1, 1]`
- **Notes**: 使用 `collections.deque`

---

## [ ] Task 4: 累积变换算子（G3）
- **Priority**: P1
- **Depends On**: Task 1
- **Description**:
  - `cum_sum()`: scan 快捷方式
  - `cum_min()`: 累积最小值
  - `cum_max()`: 累积最大值
  - `cum_mean()`: 维护 (sum, count) 对
  - `cum_prod()`: 累积乘积
- **Acceptance Criteria Addressed**: G3 / AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: `from_iter([1,2,3,4]).cum_sum().collect() == [1, 3, 6, 10]`
  - `programmatic` TR-4.2: `from_iter([3,1,4,1,5]).cum_min().collect() == [3, 1, 1, 1, 1]`
- **Notes**: 轻量级，多为 scan 的封装

---

## [ ] Task 5: 排序 Top-N（G4）
- **Priority**: P1
- **Depends On**: Task 1
- **Description**:
  - `sort(key_fn=None, reverse=False)`: 缓冲全部值后排序发射
  - `top_k(k, key_fn=None)`: heapq 维护大小为 k 的最小堆
  - `bottom_k(k, key_fn=None)`: 对称实现
- **Acceptance Criteria Addressed**: G4 / AC-5
- **Test Requirements**:
  - `programmatic` TR-5.1: `from_iter([5,2,8,1,9,3]).sort().collect() == [1, 2, 3, 5, 8, 9]`
  - `programmatic` TR-5.2: `from_iter([5,2,8,1,9,3]).top_k(2).collect() == [9, 8]`
- **Notes**: 使用 Python `heapq` 模块

---

## [ ] Task 6: 绑定补全 1 — 简单过滤/选择算子（G5）
- **Priority**: P1
- **Depends On**: Task 1
- **Description**:
  - `distinct()`: set 记忆去重
  - `element_at(idx)`: 计数匹配发射
  - `take_while(predicate)`: 满足谓词时取
  - `skip_while(predicate)`: 不满足前跳过
  - `take_last(n)`: deque 缓冲最后 n 个
  - `skip_last(n)`: 延迟发射跳过最后 n 个
- **Acceptance Criteria Addressed**: G5
- **Test Requirements**:
  - `programmatic` TR-6.1: `from_iter([1,2,1,2,3,3,1]).distinct().collect() == [1, 2, 3]`
  - `programmatic` TR-6.2: `from_iter([1,2,3,4,5]).take_while(lambda x: x < 3).collect() == [1, 2]`
- **Notes**: 6 个算子，约 100 行代码

---

## [ ] Task 7: 绑定补全 2 — 组合算子（G5）
- **Priority**: P2
- **Depends On**: Task 1
- **Description**:
  - `switch_map(mapper)`: 新值到来时取消前一个内层订阅
  - `combine_latest(other, combiner)`: 组合两方最新值
- **Acceptance Criteria Addressed**: G5
- **Test Requirements**:
  - `programmatic` TR-7.1: `from_iter([1, 10]).switch_map(lambda x: range(x, x+2)).collect() == [10, 11]`
- **Notes**: 复杂度较高，需管理订阅生命周期

---

## [ ] Task 8: 绑定补全 3 — 错误处理算子（G5）
- **Priority**: P2
- **Depends On**: Task 1
- **Description**:
  - `catch_error(handler)`: 异常时切换到 fallback
  - `retry(count)`: 失败时重试
- **Acceptance Criteria Addressed**: G5
- **Test Requirements**:
  - `programmatic` TR-8.1: `map(lambda x: 10/(x-2)).catch_error(lambda e: of('handled')).collect()` 正确处理
- **Notes**: 重要功能，使流可以优雅处理异常

---

## [ ] Task 9: 绑定补全 4 — 轻量过滤算子（G5）
- **Priority**: P2
- **Depends On**: Task 1
- **Description**:
  - `distinct_until_changed()`: 只记忆上一个值
  - `ignore_elements()`: 不发射任何值
- **Acceptance Criteria Addressed**: G5
- **Test Requirements**:
  - `programmatic` TR-9.1: `from_iter([1,2,1,2,3,3,1]).distinct_until_changed().collect() == [1, 2, 1, 2, 3, 1]`
- **Notes**: 简单任务，约 15 行代码

---

## [ ] Task 10: 绑定补全 5 — publish/share 多播（G5）
- **Priority**: P2
- **Depends On**: Task 1
- **Description**:
  - `share()`: ref_count 管理多播
  - `publish()`: 手动 connect 多播
- **Acceptance Criteria Addressed**: G5
- **Test Requirements**:
  - `programmatic` TR-10.1: share() 后两个订阅者仅触发一次源订阅
- **Notes**: 需维护观察者列表和 ref_count

---

## [ ] Task 11: None 值处理 & 数学工具（G6）
- **Priority**: P1
- **Depends On**: Task 1
- **Description**:
  - `drop_none()`: 过滤 None
  - `fill_none(default_value)`: 替换 None
  - `abs()`: 绝对值
  - `clamp(min_val, max_val)`: 值域限制
- **Acceptance Criteria Addressed**: G6 / AC-6
- **Test Requirements**:
  - `programmatic` TR-11.1: `of(1, None, 2).drop_none().collect() == [1, 2]`
  - `programmatic` TR-11.2: `from_iter([1, -2, 3, -4]).abs().collect() == [1, 2, 3, 4]`
- **Notes**: 可通过现有 map/filter 复用实现

---

## [ ] Task 12: 嵌套流展开（G7）
- **Priority**: P2
- **Depends On**: Task 1
- **Description**:
  - `explode()`: 展开 Iterable（排除 str/bytes）
  - `flatten()`: 与 explode 同语义
- **Acceptance Criteria Addressed**: G7
- **Test Requirements**:
  - `programmatic` TR-12.1: `of([1,2], [3]).explode().collect() == [1, 2, 3]`
- **Notes**: 轻量级实现

---

## [ ] Task 13: pipe() 兼容的函数式 API（G8）
- **Priority**: P2
- **Depends On**: Task 2-12
- **Description**:
  - 在 `ops` 模块中为每个新算子添加函数形式
  - 支持 `.pipe(ops.min, ops.cum_sum)` 风格
- **Acceptance Criteria Addressed**: G8 / AC-7
- **Test Requirements**:
  - `programmatic` TR-13.1: `from_iter([1,2,3]).pipe(ops.min).collect() == [1]`
- **Notes**: 可与其他任务并行

---

## [ ] Task 14: 综合测试与性能回归（G8）
- **Priority**: P0
- **Depends On**: Task 2-13
- **Description**:
  - 综合链式测试
  - 错误处理验证
  - 性能基准对比
  - 运行所有现有测试
- **Acceptance Criteria Addressed**: G8 / AC-7 / AC-8
- **Test Requirements**:
  - `programmatic` TR-14.1: 综合管道测试通过
  - `programmatic` TR-14.2: 扩展前后性能比 ≤ 1.1
- **Notes**: 最终验收任务

---

## 任务优先级排序

| 批次 | 任务 | 预计代码量 | 说明 |
|------|------|-----------|------|
| **第一批（P0）** | Task 1, Task 2, Task 14 | ~250 + 测试 | 基础框架 + 核心聚合 + 验收 |
| **第二批（P1）** | Task 3, Task 4, Task 5, Task 6, Task 11 | ~200 + 测试 | 滚动窗口 + 累积 + 排序 + 绑定1 + None/数学 |
| **第三批（P2）** | Task 7, Task 8, Task 9, Task 10, Task 12, Task 13 | ~350 + 测试 | 组合 + 错误处理 + 多播 + 展开 + pipe API |

**总代码量估算**: ~800 行 Python + ~400 行测试
