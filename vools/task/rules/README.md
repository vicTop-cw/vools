# vools.task.rules — 规则引擎 + DAG 调度

规则引擎（装饰器 + JSON 双模式）与 DAG 拓扑调度器。

## 核心组件

| 名称 | 说明 |
|------|------|
| `Rule` | 不可变规则数据类（frozen dataclass），纯函数式 condition + action |
| `RuleSet` | 规则集合，支持 `\|` (OR) / `+` (顺序) / `&` (AND) 组合 |
| `RuleEngine` | 规则引擎，thread/process 双模式，支持 `evaluate_async()` |
| `rule()` | 装饰器，将函数标记为 Rule |
| `DagScheduler` | DAG 拓扑调度器，依赖感知的任务编排 |

## 示例

```python
from vools import Result
from vools.task.rules import rule, RuleEngine

@rule(name="check", priority=5)
def my_rule(ctx):
    return Result.success(ctx.get("valid", False))

engine = RuleEngine(mode="thread")
engine.add_rule(my_rule)
result = engine.evaluate({"valid": True})
```
