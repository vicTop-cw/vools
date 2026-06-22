"""
RuleEngine 模块使用示例

本示例展示 ruleengine 模块的典型用法，包括：
1. 使用 @rule 装饰器定义规则
2. 使用 RuleEngine 管理规则
3. 规则的条件匹配和动作执行
4. 规则的优先级控制
5. 使用 RuleSet 进行规则组合
6. 从 JSON 文件加载规则

每个示例都是独立可运行的，并包含清晰的注释说明。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import tempfile
from typing import Dict, Any

from vools.functional import Result
from vools.task.rules import Rule, RuleSet, RuleEngine, rule, RuleStatus


# ============================================================
# 示例 1: 使用 @rule 装饰器定义简单规则
# ============================================================

def example_1_basic_rule():
    """示例 1: 使用 @rule 装饰器定义和执行规则"""
    print("=" * 60)
    print("示例 1: 使用 @rule 装饰器定义规则")
    print("=" * 60)

    # 使用无参装饰器定义规则
    # 函数本身既作为 condition，也作为 action
    @rule
    def check_positive(ctx: dict) -> Result:
        """检查数值是否为正数"""
        value = ctx.get("value", 0)
        return Result.success(value > 0)

    # 使用带参装饰器定义规则
    # 指定规则名称、优先级和元数据
    @rule(name="double_check", priority=10, metadata={"tag": "important"})
    def double_value(ctx: dict) -> Result:
        """将数值翻倍"""
        value = ctx.get("value", 0)
        return Result.success(value * 2)

    # 执行规则评估
    context = {"value": 15}

    print(f"\n规则名称: {check_positive.name}")
    print(f"规则优先级: {check_positive.priority}")

    # 评估规则
    result = check_positive.evaluate(context)
    print(f"check_positive 评估结果: {result}")
    print(f"  - 是否成功: {result.is_success}")
    print(f"  - 返回值: {result.unwrap()}")

    # 评估另一个规则
    result2 = double_value.evaluate(context)
    print(f"\ndouble_value 评估结果: {result2}")
    print(f"  - 返回值: {result2.unwrap()}")

    # 测试条件不通过的情况
    context_neg = {"value": -5}
    result3 = check_positive.evaluate(context_neg)
    print(f"\n负值的评估结果: {result3}")
    print(f"  - 返回值 (条件不通过时为 None): {result3.unwrap()}")

    print("\n示例 1 完成\n")


# ============================================================
# 示例 2: 使用 RuleEngine 管理多个规则
# ============================================================

def example_2_rule_engine():
    """示例 2: 使用 RuleEngine 管理规则"""
    print("=" * 60)
    print("示例 2: 使用 RuleEngine 管理规则")
    print("=" * 60)

    # 创建规则引擎（使用线程模式，适合 IO 密集型任务）
    engine = RuleEngine(mode="thread", max_workers=4)
    print(f"\n已创建规则引擎: mode={engine._mode}, max_workers={engine._max_workers}")

    # 定义几个规则
    @rule(name="check_stock", priority=5)
    def check_stock(ctx: dict) -> Result:
        """检查库存是否充足"""
        stock = ctx.get("stock", 0)
        return Result.success(stock > 0)

    @rule(name="check_balance", priority=3)
    def check_balance(ctx: dict) -> Result:
        """检查余额是否充足"""
        balance = ctx.get("balance", 0)
        price = ctx.get("price", 0)
        return Result.success(balance >= price)

    @rule(name="deduct_stock", priority=2)
    def deduct_stock(ctx: dict) -> Result:
        """扣减库存"""
        stock = ctx.get("stock", 0)
        return Result.success(stock - 1)

    # 添加规则到引擎
    engine.add_rule(check_stock)
    engine.add_rule(check_balance)
    engine.add_rule(deduct_stock)
    print(f"已添加 {len(engine.rules)} 个规则")

    # 查看已注册的规则
    print("\n已注册的规则:")
    for r in engine.rules:
        print(f"  - {r.name} (优先级: {r.priority})")

    # 执行规则评估
    context = {"stock": 10, "balance": 100, "price": 20}
    print(f"\n执行上下文: {context}")
    print("开始评估...")

    result = engine.evaluate(context)
    print(f"\n评估结果: {result}")
    print(f"  - 是否成功: {result.is_success}")
    if result.is_success:
        for rule_name, rule_result in result.unwrap():
            print(f"  - {rule_name}: {rule_result}")

    # 测试规则删除
    print("\n删除规则 'check_balance'...")
    removed = engine.remove_rule("check_balance")
    print(f"  - 删除成功: {removed}")
    print(f"  - 剩余规则数: {len(engine.rules)}")

    print("\n示例 2 完成\n")


# ============================================================
# 示例 3: 规则优先级控制
# ============================================================

def example_3_priority():
    """示例 3: 规则优先级控制"""
    print("=" * 60)
    print("示例 3: 规则优先级控制")
    print("=" * 60)

    engine = RuleEngine(mode="thread", max_workers=2)

    # 定义跟踪执行顺序的列表
    execution_log = []

    # 创建不同优先级的规则
    @rule(name="low_priority", priority=1)
    def low_rule(ctx: dict) -> Result:
        execution_log.append("low_priority")
        return Result.success("low done")

    @rule(name="high_priority", priority=10)
    def high_rule(ctx: dict) -> Result:
        execution_log.append("high_priority")
        return Result.success("high done")

    @rule(name="medium_priority", priority=5)
    def medium_rule(ctx: dict) -> Result:
        execution_log.append("medium_priority")
        return Result.success("medium done")

    # 按名称顺序添加规则（但实际执行按优先级）
    engine.add_rules(low_rule, high_rule, medium_rule)

    print(f"\n已添加 3 个规则，优先级分别为: 1, 10, 5")
    print("实际执行顺序应按优先级降序排列")

    # 执行评估
    execution_log.clear()
    result = engine.evaluate({"key": "val"})

    print(f"\n实际执行顺序:")
    for i, log in enumerate(execution_log, 1):
        print(f"  {i}. {log}")

    print(f"\n评估结果:")
    if result.is_success:
        for rule_name, rule_result in result.unwrap():
            print(f"  - {rule_name}: {rule_result.unwrap()}")

    print("\n示例 3 完成\n")


# ============================================================
# 示例 4: 使用 RuleSet 进行规则组合
# ============================================================

def example_4_ruleset_combination():
    """示例 4: 使用 RuleSet 进行规则组合"""
    print("=" * 60)
    print("示例 4: 使用 RuleSet 进行规则组合")
    print("=" * 60)

    # 创建几个基础规则
    rule_a = Rule("rule_a",
                   lambda ctx: Result.success(ctx.get("a", 0) > 0),
                   lambda ctx: Result.success("A passed"))
    rule_b = Rule("rule_b",
                   lambda ctx: Result.success(ctx.get("b", 0) > 0),
                   lambda ctx: Result.success("B passed"))
    rule_c = Rule("rule_c",
                   lambda ctx: Result.success(ctx.get("c", 0) > 0),
                   lambda ctx: Result.success("C passed"))

    # 创建规则集合
    rs1 = RuleSet([rule_a, rule_b])
    rs2 = RuleSet([rule_c])

    print(f"\n创建了两个规则集合:")
    print(f"  - rs1: {len(rs1)} 个规则")
    print(f"  - rs2: {len(rs2)} 个规则")

    # OR 组合：任一规则条件通过即返回
    print("\nOR 组合 (rs1 | rs2):")
    or_combo = rs1 | rs2

    context_all_true = {"a": 1, "b": 2, "c": 3}
    result = or_combo.evaluate(context_all_true)
    print(f"  所有条件为 True: {result.is_success}")

    context_all_false = {"a": 0, "b": 0, "c": 0}
    result = or_combo.evaluate(context_all_false)
    print(f"  所有条件为 False: {result.is_success}, 返回值: {result.unwrap()}")

    # AND 组合：所有规则条件都通过才执行
    print("\nAND 组合 (rs1 & rs2):")
    and_combo = rs1 & rs2

    result = and_combo.evaluate(context_all_true)
    print(f"  所有条件为 True: {result.is_success}")

    # 顺序组合：按优先级顺序执行所有规则
    print("\n顺序组合 (rs1 + rs2):")
    seq_combo = rs1 + rs2

    result = seq_combo.evaluate(context_all_true)
    print(f"  顺序执行结果: {result.is_success}")
    if result.is_success:
        print(f"  执行了 {len(result.unwrap())} 个规则")

    print("\n示例 4 完成\n")


# ============================================================
# 示例 5: 使用 condition 参数分离条件和动作
# ============================================================

def example_5_condition_action_separation():
    """示例 5: 使用 condition 参数分离条件和动作"""
    print("=" * 60)
    print("示例 5: 分离条件和动作")
    print("=" * 60)

    # 定义条件函数
    def has_sufficient_stock(ctx: dict) -> Result:
        """检查库存是否充足"""
        return Result.success(ctx.get("stock", 0) >= ctx.get("quantity", 1))

    def is_vip_customer(ctx: dict) -> Result:
        """检查是否为 VIP 客户"""
        return Result.success(ctx.get("customer_type") == "VIP")

    # 使用 condition 参数：condition 控制是否执行，action 定义执行内容
    @rule(name="reserve_stock", condition=has_sufficient_stock, priority=5)
    def reserve_stock_action(ctx: dict) -> Result:
        """预留库存"""
        stock = ctx.get("stock", 0)
        quantity = ctx.get("quantity", 1)
        new_stock = stock - quantity
        return Result.success({"status": "reserved", "remaining_stock": new_stock})

    @rule(name="apply_vip_discount", condition=is_vip_customer, priority=3)
    def vip_discount_action(ctx: dict) -> Result:
        """应用 VIP 折扣"""
        price = ctx.get("price", 0)
        discounted = price * 0.8  # 20% 折扣
        return Result.success({"status": "vip_discount", "new_price": discounted})

    # 测试场景 1: VIP 客户，库存充足
    print("\n场景 1: VIP 客户，库存充足")
    context1 = {
        "stock": 100,
        "quantity": 2,
        "customer_type": "VIP",
        "price": 100
    }

    engine = RuleEngine()
    engine.add_rules(reserve_stock_action, vip_discount_action)

    result = engine.evaluate(context1)
    if result.is_success:
        print("  规则执行结果:")
        for name, res in result.unwrap():
            print(f"    - {name}: {res.unwrap()}")

    # 测试场景 2: 普通客户，库存充足
    print("\n场景 2: 普通客户，库存充足")
    context2 = {
        "stock": 100,
        "quantity": 2,
        "customer_type": "regular",
        "price": 100
    }

    result = engine.evaluate(context2)
    if result.is_success:
        print("  规则执行结果:")
        for name, res in result.unwrap():
            if res.unwrap() is not None:
                print(f"    - {name}: {res.unwrap()}")
            else:
                print(f"    - {name}: 条件不通过，未执行")

    print("\n示例 5 完成\n")


# ============================================================
# 示例 6: 从 JSON 文件加载规则
# ============================================================

def example_6_load_from_json():
    """示例 6: 从 JSON 文件加载规则"""
    print("=" * 60)
    print("示例 6: 从 JSON 文件加载规则")
    print("=" * 60)

    # 首先，创建一个包含规则函数的模块
    import types
    import sys

    # 动态创建模块
    test_module = types.ModuleType("example_rules")
    def check_value(ctx: dict) -> Result:
        """检查值是否大于阈值"""
        return Result.success(ctx.get("value", 0) > ctx.get("threshold", 0))
    def process_value(ctx: dict) -> Result:
        """处理值：将其翻倍"""
        return Result.success(ctx.get("value", 0) * 2)
    test_module.check_value = check_value
    test_module.process_value = process_value
    sys.modules["example_rules"] = test_module

    # 创建 JSON 配置文件
    json_config = {
        "mode": "thread",
        "max_workers": 2,
        "rules": [
            {
                "name": "value_check",
                "condition": "example_rules:check_value",
                "action": "example_rules:process_value",
                "priority": 5,
                "metadata": {"source": "json", "version": "1.0"}
            }
        ]
    }

    # 写入临时 JSON 文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(json_config, f, indent=2)
        json_file = f.name

    print(f"\n已创建 JSON 配置文件: {json_file}")
    print("配置内容:")
    print(json.dumps(json_config, indent=2))

    try:
        # 从 JSON 文件加载规则
        print("\n正在从 JSON 加载规则...")
        engine = RuleEngine.from_json(json_file)

        print(f"  已加载 {len(engine.rules)} 个规则")
        print(f"  引擎模式: {engine._mode}")
        print(f"  最大工作线程: {engine._max_workers}")

        # 查看加载的规则
        for r in engine.rules:
            print(f"  规则: {r.name}, 优先级: {r.priority}, 元数据: {r.metadata}")

        # 执行评估
        context = {"value": 10, "threshold": 5}
        print(f"\n执行上下文: {context}")
        result = engine.evaluate(context)

        if result.is_success:
            print("评估成功:")
            for name, res in result.unwrap():
                print(f"  - {name}: {res.unwrap()}")
        else:
            print(f"评估失败: {result.unwrap_or(None)}")

    finally:
        # 清理临时文件
        import os
        os.unlink(json_file)
        del sys.modules["example_rules"]

    print("\n示例 6 完成\n")


# ============================================================
# 示例 7: 错误处理
# ============================================================

def example_7_error_handling():
    """示例 7: 错误处理"""
    print("=" * 60)
    print("示例 7: 错误处理")
    print("=" * 60)

    # 定义会失败的规则
    @rule(name="failing_rule")
    def failing_rule(ctx: dict) -> Result:
        """总会失败的规则"""
        return Result.failure(Exception("规则执行失败"))

    # 定义条件通过但动作失败的规则
    def always_true(ctx: dict) -> Result:
        return Result.success(True)

    def failing_action(ctx: dict) -> Result:
        return Result.failure(Exception("动作执行失败"))

    problematic_rule = Rule("problematic", always_true, failing_action)

    engine = RuleEngine()
    engine.add_rules(failing_rule, problematic_rule)

    print("\n测试场景 1: 条件检查失败")
    result = engine.evaluate({"key": "val"})
    print(f"  评估结果: {result}")
    print(f"  是否成功: {result.is_success}")
    if result.is_failure:
        print(f"  错误信息: {result.unwrap_or(None)}")

    print("\n示例 7 完成\n")


# ============================================================
# 主函数：运行所有示例
# ============================================================

def main():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print("RuleEngine 模块使用示例")
    print("=" * 60)

    # 运行所有示例
    example_1_basic_rule()
    example_2_rule_engine()
    example_3_priority()
    example_4_ruleset_combination()
    example_5_condition_action_separation()
    example_6_load_from_json()
    example_7_error_handling()

    print("=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
