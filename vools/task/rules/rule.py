"""
Rule 数据模型 - 不可变、可组合的纯函数式规则定义

核心设计：
- Rule: frozen dataclass，condition 和 action 都是纯函数
- RuleSet: 规则的集合，支持 | (或) 和 + (顺序) 组合
- 所有函数返回 Result 类型，确保函数式错误处理
"""

__all__ = ['Rule', 'RuleSet']

from typing import Callable, Any, Dict, Optional, List
from vools.core.dataclass_compat import dataclass, field

from vools.functional import Result


@dataclass(frozen=True)
class Rule:
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


    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
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


class RuleSet:
    """
    规则集合 - 支持函数式组合

    组合方式：
    - rs1 | rs2: OR 组合，任一规则通过即返回
    - rs1 + rs2: AND 顺序组合，按顺序执行所有规则
    - rs1 & rs2: AND 组合，两条规则都通过才执行
    """

    def __init__(self, rules: Optional[List[Rule]] = None):
        self._rules = list(rules) if rules else []

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
                return Result.failure(
                    Exception(f"Rule '{rule.name}' failed: {result.unwrap_or(None)}")
                )
        return Result.success(results)

    def __len__(self) -> int:
        return len(self._rules)


    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
    def __repr__(self) -> str:
        return f"RuleSet({len(self._rules)} rules)"
