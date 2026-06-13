# vools-reactive 算子扩展计划 - Verification Checklist

> 共 35 个验证检查点，按任务组组织

---

## Task 1: 基础设施预备

- [ ] C1.1: 确认 Observable 基类支持自定义操作符注册
- [ ] C1.2: 确认 pipe() API 模式可扩展
- [ ] C1.3: 算子模板 `mean` 测试通过

---

## Task 2: 统计聚合算子（G1）

- [ ] C2.1: `min()` 返回流中最小值
- [ ] C2.2: `max()` 返回流中最大值
- [ ] C2.3: `mean()` / `average()` 返回均值
- [ ] C2.4: `median()` 返回中位数，与 statistics.median 一致
- [ ] C2.5: `variance(ddof=0)` 返回方差
- [ ] C2.6: `std(ddof=0)` 返回标准差
- [ ] C2.7: `quantile(q)` 返回分位数
- [ ] C2.8: `arg_min()` 返回最小值下标
- [ ] C2.9: `arg_max()` 返回最大值下标
- [ ] C2.10: `n_unique()` 返回不重复值数量
- [ ] C2.11: `any(predicate)` 首个满足即发射
- [ ] C2.12: 空流调用聚合算子不发射值

---

## Task 3: 滚动窗口算子（G2）

- [ ] C3.1: `rolling_min(window_size)` 正确计算滚动最小值
- [ ] C3.2: `rolling_max(window_size)` 正确计算滚动最大值
- [ ] C3.3: `rolling_sum(window_size)` 正确计算滚动求和
- [ ] C3.4: `rolling_mean(window_size)` 正确计算滚动均值
- [ ] C3.5: window_size=1 时返回原值

---

## Task 4: 累积变换算子（G3）

- [ ] C4.1: `cum_sum()` 正确累积求和
- [ ] C4.2: `cum_min()` 正确累积求最小
- [ ] C4.3: `cum_max()` 正确累积求最大
- [ ] C4.4: `cum_mean()` 正确累积均值
- [ ] C4.5: `cum_prod()` 正确累积乘积

---

## Task 5: 排序 Top-N（G4）

- [ ] C5.1: `sort()` 默认升序排列
- [ ] C5.2: `sort(reverse=True)` 降序排列
- [ ] C5.3: `sort(key_fn=...)` 按键函数排序
- [ ] C5.4: `top_k(k)` 返回最大的 k 个值
- [ ] C5.5: `bottom_k(k)` 返回最小的 k 个值
- [ ] C5.6: k >= 流长度时返回全部值

---

## Task 6: 绑定补全 1（G5）

- [ ] C6.1: `distinct()` 去重
- [ ] C6.2: `element_at(idx)` 取第 idx 个元素
- [ ] C6.3: `take_while(predicate)` 满足时取
- [ ] C6.4: `skip_while(predicate)` 不满足前跳过
- [ ] C6.5: `take_last(n)` 取最后 n 个
- [ ] C6.6: `skip_last(n)` 跳过最后 n 个

---

## Task 7: 绑定补全 2 — 组合算子（G5）

- [ ] C7.1: `switch_map()` 新值到来时取消前一个订阅
- [ ] C7.2: `combine_latest()` 组合两方最新值

---

## Task 8: 绑定补全 3 — 错误处理（G5）

- [ ] C8.1: `catch_error()` 异常时切换到 fallback
- [ ] C8.2: `retry(count)` 失败时重试指定次数

---

## Task 9: 绑定补全 4（G5）

- [ ] C9.1: `distinct_until_changed()` 相邻去重
- [ ] C9.2: `ignore_elements()` 不发射任何值

---

## Task 10: 绑定补全 5 — 多播（G5）

- [ ] C10.1: `share()` 多个订阅者共享源订阅
- [ ] C10.2: `publish()` 手动控制多播

---

## Task 11: None 值处理 & 数学工具（G6）

- [ ] C11.1: `drop_none()` 过滤 None
- [ ] C11.2: `fill_none(default)` 替换 None
- [ ] C11.3: `abs()` 返回绝对值
- [ ] C11.4: `clamp(min, max)` 值域限制

---

## Task 12: 嵌套流展开（G7）

- [ ] C12.1: `explode()` 展开 Iterable（排除 str/bytes）
- [ ] C12.2: `flatten()` 展开 Observable-like

---

## Task 13: pipe() 函数式 API（G8）

- [ ] C13.1: 所有新算子支持 `.pipe(ops.x)` 形式
- [ ] C13.2: pipe 组合结果与链式调用一致

---

## Task 14: 综合测试与性能

- [ ] C14.1: 综合管道测试通过
- [ ] C14.2: 扩展前后性能比 ≤ 1.1
- [ ] C14.3: 所有现有测试通过
- [ ] C14.4: 代码风格与现有一致（human-judgment）

---

## 质量保证总览

| 算子组 | 算子数量 | 检查点数量 |
|--------|---------|-----------|
| 统计聚合 (G1) | 11 | 12 |
| 滚动窗口 (G2) | 4 | 5 |
| 累积变换 (G3) | 5 | 5 |
| 排序 Top-N (G4) | 3 | 6 |
| 绑定补全 (G5) | 14 | 14 |
| None/数学 (G6) | 4 | 4 |
| 嵌套展开 (G7) | 2 | 2 |
| **总计** | **43** | **50** |
