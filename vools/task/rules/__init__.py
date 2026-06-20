"""
规则引擎模块 - 支持装饰器和JSON两种配置风格

核心组件：
- Rule: 不可变规则数据类，纯函数式定义
- RuleSet: 规则集合，支持管道组合（| 操作符）
- RuleEngine: 规则引擎，支持异步进程/线程执行
- DagScheduler: DAG 拓扑调度器，依赖感知的任务编排

两种配置风格：
1. 装饰器风格: @rule(name="xxx") 装饰普通函数
2. JSON风格: RuleEngine.from_json("rules.json")

示例:
    >>> from vools import Result
    >>> from vools.task.rules import rule, RuleEngine

    >>> @rule(name="check_stock", priority=5)
    ... def stock_rule(ctx: dict) -> Result:
    ...     return Result.success(ctx.get("stock", 0) > 0)

    >>> engine = RuleEngine(mode="thread", max_workers=4)
    >>> engine.add_rule(stock_rule)
    >>> result = engine.evaluate({"stock": 10})
"""

from .rule import Rule, RuleSet
from .engine import RuleEngine, rule, RuleStatus
from .dag import DagScheduler

__all__ = [
    'Rule',
    'RuleSet',
    'RuleEngine',
    'rule',
    'RuleStatus',
    'DagScheduler',
]
