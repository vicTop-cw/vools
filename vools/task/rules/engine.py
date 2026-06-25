"""
RuleEngine - 规则引擎（装饰器 + JSON 双模式）

支持两种配置方式：
1. @rule 装饰器：面向代码的声明式规则定义
2. from_json()：面向配置的规则加载

执行模式：
- thread: 使用 ThreadPoolExecutor（默认，适合 IO 密集型）
- process: 使用 ProcessPoolExecutor（适合 CPU 密集型）

函数式风格：
- 所有规则返回 Result 类型
- evaluate 返回 Result 链式处理
"""

__all__ = ['RuleEngine', 'rule', 'RuleStatus']

import json
import importlib
from typing import Callable, Any, Dict, Optional, List, Union
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from functools import wraps

from ...functional import Result, safe
from .rule import Rule, RuleSet


class RuleStatus(Enum):
    """规则执行状态"""
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


def rule(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    condition: Optional[Callable[[Dict[str, Any]], Result]] = None,
    priority: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> Union[Callable, Rule]:
    """
    装饰器：将普通函数标记为 Rule

    支持两种用法：
    1. 无参装饰器: @rule
       >>> @rule
       ... def my_rule(ctx): ...

    2. 带参装饰器: @rule(name="xxx", priority=5)
       >>> @rule(name="check", priority=5)
       ... def my_rule(ctx): ...

    Args:
        func: 被装饰的函数
        name: 规则名称（默认使用函数名）
        condition: 条件函数（默认使用 func 本身作为 condition，
                   同时自动生成一个恒通过的 action）
        priority: 优先级
        metadata: 附加元数据

    Returns:
        如果 func 为 None，返回装饰器；否则返回 Rule 实例
    """
    def decorator(f: Callable) -> Rule:
        rule_name = name or f.__name__
        rule_metadata = metadata or {}

        # 如果传入了 condition，则 f 当作 action
        if condition is not None:
            return Rule(
                name=rule_name,
                condition=condition,
                action=safe(f) if not callable(getattr(f, '__wrapped__', None)) else f,
                priority=priority,
                metadata=rule_metadata,
            )

        # 否则 f 同时作为 condition 和 action（返回非 False 即通过）
        def auto_condition(ctx: Dict[str, Any]) -> Result:
            try:
                result = f(ctx)
                if isinstance(result, Result):
                    return result.map(lambda v: bool(v))
                return Result.success(bool(result))
            except Exception as e:
                return Result.failure(e)

        def auto_action(ctx: Dict[str, Any]) -> Result:
            try:
                result = f(ctx)
                if isinstance(result, Result):
                    return result
                return Result.success(result)
            except Exception as e:
                return Result.failure(e)

        return Rule(
            name=rule_name,
            condition=auto_condition,
            action=auto_action,
            priority=priority,
            metadata=rule_metadata,
        )

    if func is not None:
        return decorator(func)
    return decorator


class RuleEngine:
    """
    规则引擎 - 执行上下文匹配的规则

    支持 thread/process 两种并发模式，
    提供同步 evaluate 和异步 evaluate_async 两个入口。

    Args:
        mode: 执行模式，"thread" 或 "process"
        max_workers: 最大并发数

    Example:
        >>> engine = RuleEngine(mode="thread", max_workers=4)
        >>> engine.add_rule(my_rule)
        >>> result = engine.evaluate({"user": "admin", "action": "delete"})
    """

    def __init__(
        self,
        mode: str = "thread",
        max_workers: int = 4,
    ):
        self._rules: List[Rule] = []
        self._mode = mode
        self._max_workers = max_workers

    @property
    def rules(self) -> List[Rule]:
        """获取所有已注册规则的副本"""
        return list(self._rules)

    def add_rule(self, r: Rule) -> None:
        """添加单个规则"""
        self._rules.append(r)

    def add_rules(self, *rules: Rule) -> None:
        """批量添加规则"""
        self._rules.extend(rules)

    def remove_rule(self, name: str) -> bool:
        """按名称移除规则"""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) < before

    def get_rule(self, name: str) -> Optional[Rule]:
        """按名称获取规则"""
        for r in self._rules:
            if r.name == name:
                return r
        return None

    def _create_executor(self):
        """根据 mode 创建执行器"""
        if self._mode == "process":
            return ProcessPoolExecutor(max_workers=self._max_workers)
        return ThreadPoolExecutor(max_workers=self._max_workers)

    def evaluate(self, context: Dict[str, Any]) -> Result:
        """
        同步执行所有规则

        按 priority 排序后，使用线程/进程池并发执行。
        每个规则的 condition 和 action 都在池中执行。

        Args:
            context: 执行上下文

        Returns:
            Result: 成功时返回 [(rule_name, Result), ...] 列表
                    失败时返回第一个失败的 Result
        """
        sorted_rules = sorted(self._rules, key=lambda r: -r.priority)
        results: List = []

        with self._create_executor() as executor:
            futures = {}
            for rule_obj in sorted_rules:
                future = executor.submit(rule_obj.evaluate, context)
                futures[future] = rule_obj.name

            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = Result.failure(e)
                results.append((name, result))

        # 按原顺序返回
        ordered = []
        for rule_obj in sorted_rules:
            for name, result in results:
                if name == rule_obj.name:
                    ordered.append((name, result))
                    if result.is_failure:
                        return Result.failure(
                            Exception(f"Rule '{name}' failed: {result.unwrap_or(None)}")
                        )
                    break

        return Result.success(ordered)

    async def evaluate_async(self, context: Dict[str, Any]) -> Result:
        """
        异步执行所有规则
        
        使用 asyncio 包装 ThreadPoolExecutor，
        非阻塞方式执行所有规则。
        
        Args:
            context: 执行上下文
        
        Returns:
            Result: 同 evaluate()
        """
        import asyncio
        loop = asyncio.get_event_loop()

        sorted_rules = sorted(self._rules, key=lambda r: -r.priority)
        results: List = []

        with self._create_executor() as executor:
            # 创建 Future 到名称的映射
            future_to_name = {}
            for rule_obj in sorted_rules:
                future = loop.run_in_executor(executor, rule_obj.evaluate, context)
                future_to_name[future] = rule_obj.name

            # 等待所有 Future 完成
            done, _ = await asyncio.wait(list(future_to_name.keys()))

            # 收集结果
            for future in done:
                name = future_to_name[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = Result.failure(e)
                results.append((name, result))

        ordered = []
        for rule_obj in sorted_rules:
            for name, result in results:
                if name == rule_obj.name:
                    ordered.append((name, result))
                    if result.is_failure:
                        return Result.failure(
                            Exception(f"Rule '{name}' failed: {result.unwrap_or(None)}")
                        )
                    break

        return Result.success(ordered)



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
    
    @classmethod
    def from_json(
        cls,
        json_path: str,
        *,
        mode: Optional[str] = None,
        max_workers: Optional[int] = None,
    ) -> 'RuleEngine':
        """
        从 JSON 文件加载规则

        JSON 格式:
        {
            "mode": "thread",
            "max_workers": 4,
            "rules": [
                {
                    "name": "check_stock",
                    "condition": "my_module:has_stock",
                    "action": "my_module:reserve_stock",
                    "priority": 5,
                    "retry": 2
                }
            ]
        }

        condition 和 action 使用 "module:function" 路径格式，
        通过 importlib 动态加载（同 TaskQueue._deserialize_func）。

        Args:
            json_path: JSON 配置文件路径
            mode: 覆盖 JSON 中的 mode
            max_workers: 覆盖 JSON 中的 max_workers

        Returns:
            RuleEngine 实例
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        engine = cls(
            mode=mode or data.get("mode", "thread"),
            max_workers=max_workers or data.get("max_workers", 4),
        )

        for rule_def in data.get("rules", []):
            name = rule_def["name"]
            priority = rule_def.get("priority", 0)
            metadata = rule_def.get("metadata", {})

            # 反序列化 condition
            condition = _deserialize_rule_func(rule_def["condition"])

            # 反序列化 action（如果提供）
            if "action" in rule_def:
                action = _deserialize_rule_func(rule_def["action"])
            else:
                # 如果没提供 action，condition 的值直接作为 action 的结果
                action = condition

            r = Rule(
                name=name,
                condition=condition,
                action=action,
                priority=priority,
                metadata=metadata,
            )
            engine.add_rule(r)

        return engine


def _deserialize_rule_func(func_ref: str) -> Callable[[Dict[str, Any]], Result]:
    """
    反序列化 "module:function" 路径为可调用函数

    Args:
        func_ref: "module:function" 格式的字符串

    Returns:
        包装为返回 Result 的函数
    """
    if ':' not in func_ref:
        raise ValueError(
            f"Invalid function reference '{func_ref}'. "
            f"Expected format: 'module:function'"
        )

    module_path, func_name = func_ref.split(':', 1)
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)
    func = getattr(func, '__wrapped__', func)

    # 包装为返回 Result 的纯函数
    def wrapper(ctx: Dict[str, Any]) -> Result:
        try:
            result = func(ctx)
            if isinstance(result, Result):
                return result
            return Result.success(result)
        except Exception as e:
            return Result.failure(e)

    return wrapper
