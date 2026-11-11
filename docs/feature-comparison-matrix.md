# vools 功能对比矩阵（31 项）

> **子项目**：vools（函数式编程工具集核心库）
> **文档编号**：#A27
> **最后更新**：2026-11-11
> **来源**：`analysis/FEATURE_EXTENSION_PLAN.md` §1 对比分析 / §7 输出物清单
> **实现状态核实方式**（可复跑）：`python actus/tools/audit/plan_audit_core.py`（根 = 仓库 `vools/`，秒级完成）
> **测试证据**（可复跑）：`tests/functional/` + `tests/curried/` + 11 个相关回归文件 → 实测 **506 passed**

---

## 1. 总体结论

| 指标 | 数值 |
|------|------|
| 计划功能条目 | 31 项 |
| 已实现 | **31 项（100%）** |
| 未实现 | 0 项 |
| 实现状态核实时间 | 2026-11-11（T0r3.2.2 复跑基线延续） |

上期（2026-10-29）标注的「部分/未实现」条目 `conj`、`count_by（对比表）` 已复跑确认**均已落地**
（`vools/curried/collection.py:485 / :153`）。

---

## 2. 对比矩阵（按类别整理）

> 状态图例：✅ 已实现。代码位置为 audit 脚本 AST 定位结果。

### 2.1 错误处理类型（Result / Maybe）

| # | 功能 | 实现状态 | 代码位置 | 来源库 |
|---|------|---------|---------|--------|
| 1 | `Result` / `Success` / `Failure` | ✅ | `vools/functional/result.py:14 / :265 / :272` | returns |
| 2 | `Maybe` / `Some` / `Nothing` | ✅ | `vools/functional/maybe.py:15 / :243` | returns |

### 2.2 集合操作（collection）

| # | 功能 | 实现状态 | 代码位置 | 来源库 |
|---|------|---------|---------|--------|
| 3 | `count_by` | ✅ | `vools/curried/collection.py:153` | funcy/toolz |
| 4 | `flatten` | ✅ | `vools/curried/collection.py:270` | funcy/toolz |
| 5 | `cons` | ✅ | `vools/curried/collection.py:466` | funcy/toolz |
| 6 | `conj` | ✅ | `vools/curried/collection.py:485` | funcy |
| 7 | `interleave` | ✅ | `vools/curried/collection.py:518` | funcy/toolz |
| 8 | `interpose` | ✅ | `vools/curried/collection.py:549` | toolz |
| 9 | `pluck` | ✅ | `vools/curried/collection.py:575` | funcy/toolz |
| 10 | `pluck_attr` | ✅ | `vools/curried/collection.py:594` | funcy |
| 11 | `walk` | ✅ | `vools/curried/collection.py:616` | funcy |
| 12 | `mapcat` | ✅ | `vools/curried/collection.py:635` | funcy |
| 13 | `compact` | ✅ | `vools/curried/collection.py:654` | funcy |
| 14 | `merge` | ✅ | `vools/curried/collection.py:672` | funcy/toolz |
| 15 | `merge_with` | ✅ | `vools/curried/collection.py:692` | funcy |
| 16 | `get_in` | ✅ | `vools/curried/collection.py:726` | funcy/toolz |
| 17 | `set_in` | ✅ | `vools/curried/collection.py:754` | funcy |
| 18 | `update_in` | ✅ | `vools/curried/collection.py:785` | funcy/toolz |
| 19 | `split_at` | ✅ | `vools/curried/collection.py:816` | funcy |
| 20 | `butlast` | ✅ | `vools/curried/collection.py:836` | funcy |
| 21 | `dissoc` | ✅ | `vools/curried/collection.py:857` | toolz |
| 22 | `assoc` | ✅ | `vools/curried/collection.py:876` | toolz |
| 23 | `assoc_in` | ✅ | `vools/curried/collection.py:897` | toolz |
| 24 | `constantly` | ✅ | `vools/curried/collection.py:917` | funcy |

### 2.3 函数组合（composition）

| # | 功能 | 实现状态 | 代码位置 | 来源库 |
|---|------|---------|---------|--------|
| 25 | `compose_left` | ✅ | `vools/curried/composition.py:148` | toolz |
| 26 | `flip` | ✅ | `vools/curried/composition.py:223` | toolz |

### 2.4 错误处理装饰器（decorators/control）

| # | 功能 | 实现状态 | 代码位置 | 来源库 |
|---|------|---------|---------|--------|
| 27 | `excepts` | ✅ | `vools/decorators/control.py:21` | toolz |
| 28 | `silent` | ✅ | `vools/decorators/control.py:74` | funcy |
| 29 | `suppress` | ✅ | `vools/decorators/control.py:116` | funcy |
| 30 | `ignore` | ✅ | `vools/decorators/control.py:172` | funcy |

### 2.5 响应式编程（reactive）

| # | 功能 | 实现状态 | 代码位置 | 来源库 |
|---|------|---------|---------|--------|
| 31 | `Observable` / `Subject` / 操作符链 / 背压 / 调度器 | ✅ | `rx/vools/reactive/core/{observable,subject,schedulers}.py`、`rx/vools/reactive/operators/*.py`（覆盖 Rx 4.0 全部 98 操作符） | Rx 4.0 规范 |

---

## 3. 与各参考库的能力对照（摘要）

> 完整历史对比见 `analysis/FEATURE_EXTENSION_PLAN.md` §1（计划快照）。下表为本计划 31 项功能落地后的状态对照。

| 类别 | vools（现状） | funcy | toolz | returns |
|------|---------------|-------|-------|---------|
| 错误处理类型（Result/Maybe） | ✅ 已实现 | ❌ | ❌ | ✅（参照） |
| 集合操作 | ✅ 全部落地 | ✅（参照） | 部分 | ❌ |
| 序列操作 | ✅ 全部落地 | ✅（参照） | 部分 | ❌ |
| 字典操作 | ✅ 全部落地 | 部分 | ✅（参照） | ❌ |
| 函数组合 | ✅ 已补 `compose_left`/`flip` | 部分 | ✅（参照） | ❌ |
| 错误处理装饰器 | ✅ 全部落地 | 部分 | 部分 | 部分 |
| 响应式编程 | ✅ 98/98 操作符 | ❌ | ❌ | ❌ |

---

## 4. 实现载体文件（§7 对应）

| 输出物 | 状态 | 证据 |
|--------|------|------|
| `vools/functional/result.py` | ✅ 已实现 | 251 行；`tests/functional/` 覆盖 |
| `vools/curried/collection.py`（增强） | ✅ 已实现 | 749 行；`tests/curried/` 覆盖 |
| `vools/curried/iteration.py`（增强） | ✅ 已实现 | 276 行 |
| `vools/curried/composition.py`（增强） | ✅ 已实现 | 204 行 |
| `vools/decorators/control.py`（增强） | ✅ 已实现 | 488 行；`tests/test_decorators_control_validation_regression.py` |
| 单元测试套件 | ✅ 已实现 | 实测 **506 passed** |
| API 文档 | ✅ 已产出 | [docs/actus-api.md](actus-api.md)（覆盖 actus 公共 API 面） |
| 功能对比矩阵更新 | ✅ 已产出 | 本文档 |

---

**文档版本**: v1.0
**创建日期**: 2026-11-11
**最后更新**: 2026-11-11
