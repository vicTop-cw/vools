"""
Rule 数据模型 - 不可变、可组合的纯函数式规则定义

核心设计：
- Rule: frozen dataclass，condition 和 action 都是纯函数
- RuleSet: 规则的集合，支持 | (或) 和 + (顺序) 组合
- 所有函数返回 Result 类型，确保函数式错误处理
"""

__all__ = ['Rule', 'RuleSet']

from typing import Callable, Any, Dict, Optional, List
from ...core.dataclass_compat import dataclass, field
from ...core.base import VoolsBase
from ...functional import Result


@dataclass(frozen=True)
class Rule(VoolsBase):
    """
    不可变规则数据类

    condition 和 action 均为返回 Result 的纯函数，
    通过 frozen=True 保证规则定义不可修改。

    Args:
        name: 规则名称（唯一标识）
        condition: 条件函数，接收 context dict，返回 Result[bool, Exception]
        action: 动作函数，接收 context dict，返回 Result[Any, Exception]
        priority: 优先级（越大越先执行）
        metadata: 附加元数据字典
    """
    name: str
    condition: Callable[[Dict[str, Any]], Result] = field(compare=False)
    action: Callable[[Dict[str, Any]], Result] = field(compare=False)
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """BUG-434: 构造校验（frozen dataclass 无法在字段上校验）。

        原实现接受任意值：``Rule(name='', ...)``、``condition=123``、
        ``action=123``、``priority='x'/-1``、``metadata='x'`` 全部被接受，
        直到 ``evaluate`` 调用 ``self.condition(context)`` 时才抛 TypeError。
        """
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                f"Rule 的 name 需要非空字符串，收到 "
                f"{type(self.name).__name__}: {self.name!r}")
        for label, fn in (("condition", self.condition), ("action", self.action)):
            if not callable(fn):
                raise TypeError(
                    f"Rule 的 {label} 必须可调用，收到 "
                    f"{type(fn).__name__}: {fn!r}")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError(
                f"Rule 的 priority 需要整数，收到 "
                f"{type(self.priority).__name__}: {self.priority!r}")
        if self.priority < 0:
            raise ValueError(f"Rule 的 priority 不能为负，收到 {self.priority}")
        if not isinstance(self.metadata, dict):
            raise TypeError(
                f"Rule 的 metadata 需要 dict，收到 "
                f"{type(self.metadata).__name__}: {self.metadata!r}")

    def evaluate(self, context: Dict[str, Any]) -> Result:
        """
        执行规则：先检查 condition，通过后执行 action

        Args:
            context: 执行上下文

        Returns:
            Result: condition 不通过返回 Result.success(None)，
                    condition 通过返回 action 的结果
        """
        cond_result = self.condition(context)
        if cond_result.is_failure:
            return cond_result
        if not cond_result.unwrap():
            return Result.success(None)
        return self.action(context)


class RuleSet(VoolsBase):
    """
    规则集合 - 支持函数式组合

    组合方式：
    - rs1 | rs2: OR 组合，任一规则通过即返回
    - rs1 + rs2: AND 顺序组合，按顺序执行所有规则
    - rs1 & rs2: AND 组合，两条规则都通过才执行
    """

    def __init__(self, rules: Optional[List[Rule]] = None):
        # BUG-434: 原实现 ``list(rules) if rules else []`` 把**任意可迭代**
        # 都当成规则列表：``RuleSet(rules='x')`` 得到 1 条规则（字符串被逐字符
        # 展开），``RuleSet([123])`` 得到 1 条非 Rule 对象，均静默错值。
        if rules is None:
            self._rules = []
            return
        if isinstance(rules, (str, bytes)) or not isinstance(rules, (list, tuple)):
            raise TypeError(
                f"RuleSet 的 rules 需要 Rule 列表或 None，收到 "
                f"{type(rules).__name__}: {rules!r}")
        for r in rules:
            if not isinstance(r, Rule):
                raise TypeError(
                    f"RuleSet 的元素需要 Rule，收到 {type(r).__name__}: {r!r}")
        self._rules = list(rules)

    @property
    def rules(self) -> List[Rule]:
        """获取所有规则的副本（不可变风格）"""
        return list(self._rules)

    def add(self, rule: Rule) -> 'RuleSet':
        """添加规则（返回新集合，不可变风格）"""
        return RuleSet(self._rules + [rule])

    def __or__(self, other: 'RuleSet') -> 'RuleSet':
        """OR 组合：任一规则通过即返回"""
        def or_condition(ctx: Dict[str, Any]) -> Result:
            for rule in self._rules + other._rules:
                r = rule.condition(ctx)
                if r.is_success and r.unwrap():
                    return Result.success(True)
            return Result.success(False)

        def or_action(ctx: Dict[str, Any]) -> Result:
            for rule in self._rules + other._rules:
                r = rule.condition(ctx)
                if r.is_success and r.unwrap():
                    return rule.action(ctx)
            return Result.success(None)

        combined = Rule(
            name=f"({self._rules[0].name} | {other._rules[0].name})" if self._rules and other._rules else "or_combo",
            condition=or_condition,
            action=or_action,
        )
        return RuleSet([combined])

    def __add__(self, other: 'RuleSet') -> 'RuleSet':
        """顺序组合：按 priority 排序后顺序执行所有规则"""
        merged = sorted(
            self._rules + other._rules,
            key=lambda r: -r.priority
        )
        return RuleSet(merged)

    def __and__(self, other: 'RuleSet') -> 'RuleSet':
        """AND 组合：两条规则都通过才执行"""
        def and_condition(ctx: Dict[str, Any]) -> Result:
            for rule_set in (self, other):
                for rule in rule_set._rules:
                    r = rule.condition(ctx)
                    if r.is_failure or not r.unwrap():
                        return r
            return Result.success(True)

        def and_action(ctx: Dict[str, Any]) -> Result:
            results = []
            for rule_set in (self, other):
                for rule in rule_set._rules:
                    r = rule.action(ctx)
                    results.append(r)
            return Result.success(results)

        combined = Rule(
            name=f"({self._rules[0].name} & {other._rules[0].name})" if self._rules and other._rules else "and_combo",
            condition=and_condition,
            action=and_action,
        )
        return RuleSet([combined])

    def evaluate(self, context: Dict[str, Any]) -> Result:
        """
        按优先级顺序执行所有规则

        Args:
            context: 执行上下文

        Returns:
            Result: 所有规则结果的列表
        """
        sorted_rules = sorted(self._rules, key=lambda r: -r.priority)
        results = []
        for rule in sorted_rules:
            result = rule.evaluate(context)
            results.append((rule.name, result))
            if result.is_failure:
                err = result.unwrap_or_else(lambda e: e)
                return Result.failure(
                    Exception(f"Rule '{rule.name}' failed: {err}")
                )
        return Result.success(results)

    def __len__(self) -> int:
        return len(self._rules)


    def __repr__(self) -> str:
        return f"RuleSet({len(self._rules)} rules)"
