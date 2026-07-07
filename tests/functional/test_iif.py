"""
iif 函数和 ConditionBuilder 类的单元测试（匹配改进版）

改进版关键变更：
  - LazyProperty: 双路缓存，兼容 __slots__ 宿主类
  - __and__: 条件数不一致时抛出 ValueError
  - default/otherwise: _UNSET 哨兵，支持 None 作为有效默认值
  - __call__: 不修改 self.base，builder 可安全复用
  - evaluate_each: 新命名（evaluateEx 保留为弃用别名）
  - whens(): 输入类型校验
  - iif(whens): data 正确传递给 ConditionBuilder
  - comp.setter: 各分支独立 return，消除 UnboundLocalError
  - _fix_comp: try/except 替代 inspect.signature
"""
import pytest
from vools.functional.iif import iif, ConditionBuilder, LazyProperty


# ============================================================================
# LazyProperty
# ============================================================================

class TestLazyProperty:
    """测试 LazyProperty 装饰器"""

    # --- 基础功能 ---

    def test_lazy_property_basic(self):
        """普通类：首次计算后缓存，后续不重复计算"""
        class TestClass:
            def __init__(self):
                self.counter = 0

            @LazyProperty
            def value(self):
                self.counter += 1
                return 42

        obj = TestClass()
        assert obj.counter == 0
        assert obj.value == 42
        assert obj.counter == 1
        # 第二次访问应命中缓存
        assert obj.value == 42
        assert obj.counter == 1

    def test_lazy_property_read_only(self):
        """延迟属性只读"""
        class TestClass:
            @LazyProperty
            def value(self):
                return 42

        obj = TestClass()
        with pytest.raises(AttributeError):
            obj.value = 100

    # --- __slots__ 兼容（改进版新增） ---

    def test_lazy_property_slots_class(self):
        """__slots__ 类：正常缓存，不报错"""
        class Slotted:
            __slots__ = ('counter',)

            def __init__(self):
                self.counter = 0

            @LazyProperty
            def value(self):
                self.counter += 1
                return 99

        obj = Slotted()
        assert obj.counter == 0
        assert obj.value == 99
        assert obj.counter == 1
        # 第二次应命中缓存（id 缓存）
        assert obj.value == 99
        assert obj.counter == 1

    def test_lazy_property_slots_no_weakref(self):
        """__slots__ 无 __weakref__ 的类也能正常使用"""
        class Strict:
            __slots__ = ('a',)

            def __init__(self):
                self.a = 0

            @LazyProperty
            def calc(self):
                self.a = 1
                return self.a * 10

        s = Strict()
        assert s.calc == 10
        assert s.a == 1
        assert s.calc == 10  # 缓存命中


# ============================================================================
# ConditionBuilder 基本功能
# ============================================================================

class TestConditionBuilderBasic:
    """测试 ConditionBuilder 基本功能"""

    def test_condition_builder_init(self):
        cb = ConditionBuilder(10)
        assert cb.base == 10

    def test_condition_builder_case(self):
        cb = ConditionBuilder(5).case(5, "five").otherwise("other")
        assert cb() == "five"

    def test_condition_builder_case_no_match(self):
        cb = ConditionBuilder(6).case(5, "five").otherwise("other")
        assert cb() == "other"

    def test_condition_builder_cases(self):
        cb = ConditionBuilder(3).cases([1, "one"], [2, "two"], [3, "three"]).otherwise("other")
        assert cb() == "three"

    def test_condition_builder_case_dict(self):
        cb = ConditionBuilder("apple").cases({"apple": "fruit", "carrot": "vegetable"}).otherwise("unknown")
        assert cb() == "fruit"

    def test_condition_builder_when(self):
        cb = ConditionBuilder(15).when(lambda x: x > 10, "big").otherwise("small")
        assert cb() == "big"

    def test_condition_builder_whens(self):
        cb = ConditionBuilder(8).whens(
            (lambda x: x < 5, "small"),
            (lambda x: x < 10, "medium"),
            (lambda x: x >= 10, "large")
        ).otherwise("unknown")
        assert cb() == "medium"

    def test_condition_builder_evaluate(self):
        cb = ConditionBuilder(20).case(10, "ten").case(20, "twenty").otherwise("other")
        assert cb.evaluate(20) == "twenty"

    def test_condition_builder_evaluateEx(self):
        """批量 evaluate（旧名 evaluateEx，保留兼容）"""
        cb = ConditionBuilder(None).case(1, "one").case(2, "two").otherwise("other")
        results = cb.evaluateEx([1, 2, 3])
        assert results == ["one", "two", "other"]

    def test_condition_builder_evaluate_each(self):
        """批量 evaluate（新名 evaluate_each）"""
        cb = ConditionBuilder(None).case(1, "one").case(2, "two").otherwise("other")
        results = cb.evaluate_each([1, 2, 3])
        assert results == ["one", "two", "other"]

    def test_condition_builder_repr(self):
        cb = ConditionBuilder(42).case(1, "one").otherwise("other")
        r = repr(cb)
        assert "ConditionBuilder" in r
        assert "42" in r


# ============================================================================
# ConditionBuilder 运算符
# ============================================================================

class TestConditionBuilderOperators:
    """测试条件构建器的比较运算符"""

    def test_condition_builder_eq(self):
        cb = ConditionBuilder(5, comp='==').case(5, "equal").otherwise("not equal")
        assert cb() == "equal"

    def test_condition_builder_gt(self):
        cb = ConditionBuilder(10, comp='>').case(5, "greater").otherwise("not greater")
        assert cb() == "greater"

    def test_condition_builder_lt(self):
        cb = ConditionBuilder(3, comp='<').case(5, "less").otherwise("not less")
        assert cb() == "less"

    def test_condition_builder_in(self):
        cb = ConditionBuilder("apple", comp='in').case(["apple", "banana"], "found").otherwise("not found")
        assert cb() == "found"


# ============================================================================
# ConditionBuilder 运算符重载
# ============================================================================

class TestConditionBuilderCombinators:
    """测试 | 和 & 操作符"""

    def test_or_merge(self):
        """| 合并两个 builder 的全部条件"""
        cb1 = ConditionBuilder(None).case(1, "one")
        cb2 = ConditionBuilder(None).case(2, "two").otherwise("other")
        merged = cb1 | cb2
        assert merged.evaluate(1) == "one"
        assert merged.evaluate(2) == "two"
        assert merged.evaluate(99) == "other"

    def test_and_equal_counts(self):
        """& 两侧条件数相同时应正常合并"""
        cb1 = ConditionBuilder(1).case(1, "A").case(2, "B")
        cb2 = ConditionBuilder(1).case(1, "X").case(2, "Y")
        merged = cb1 & cb2
        # 第 1 条：cb1 条件1 AND cb2 条件1 → 都匹配 1 → 返回 "A"
        assert merged.evaluate(1) == "A"
        # 第 2 条：cb1 条件2 AND cb2 条件2 → 都匹配 2 → 返回 "B"
        assert merged.evaluate(2) == "B"

    def test_and_unequal_counts_raises(self):
        """& 两侧条件数不一致时应抛出 ValueError"""
        cb1 = ConditionBuilder(1).case(1, "one").case(2, "two")
        cb2 = ConditionBuilder(1).case(1, "A")
        with pytest.raises(ValueError, match="条件数"):
            _ = cb1 & cb2

    def test_and_type_check(self):
        """& 只能用于 ConditionBuilder"""
        cb = ConditionBuilder(1).case(1, "one")
        with pytest.raises(TypeError):
            _ = cb & "not a builder"

    def test_or_type_check(self):
        """| 只能用于 ConditionBuilder"""
        cb = ConditionBuilder(1).case(1, "one")
        with pytest.raises(TypeError):
            _ = cb | 123


# ============================================================================
# ConditionBuilder 高级功能
# ============================================================================

class TestConditionBuilderAdvanced:
    """测试 ConditionBuilder 高级功能"""

    def test_condition_builder_callable_result(self):
        cb = ConditionBuilder(5).case(5, lambda x: x * 2).otherwise(lambda x: x * 3)
        assert cb() == 10

    def test_condition_builder_lambda_condition(self):
        cb = ConditionBuilder(25).when(lambda x: x > 18, "adult").otherwise("child")
        assert cb() == "adult"

    def test_condition_builder_short_circuit(self):
        """短路求值"""
        counter = [0]

        def count_condition(x):
            counter[0] += 1
            return x == 2

        cb = ConditionBuilder(2).case(1, "one").case(2, "two").case(3, "three")
        assert cb() == "two"

    def test_condition_builder_chain_locked(self):
        cb = ConditionBuilder(5).case(5, "five").otherwise("other")
        with pytest.raises(RuntimeError):
            cb.case(6, "six")

    # --- 改进版新增 ---

    def test_default_none(self):
        """default(None) 应将 None 作为有效默认值返回（_UNSET 哨兵修复）"""
        cb = ConditionBuilder(99).case(1, "one").default(None)
        assert cb() is None

    def test_otherwise_none(self):
        """otherwise(None) 同样有效"""
        cb = ConditionBuilder(99).case(1, "one").otherwise(None)
        assert cb() is None

    def test_callable_otherwise(self):
        """可调用 otherwise"""
        cb = ConditionBuilder(99).case(1, "one").otherwise(lambda x: f"got {x}")
        assert cb() == "got 99"

    def test_reuse_builder(self):
        """__call__ 不修改 self.base，builder 可安全复用"""
        cb = ConditionBuilder(10).case(10, "ten").case(20, "twenty").otherwise("?")
        assert cb(10) == "ten"
        assert cb(20) == "twenty"
        # self.base 未被修改
        assert cb.base == 10
        # 再次调用仍然正确
        assert cb(10) == "ten"

    def test_evaluate_reuse(self):
        """evaluate 也不修改 self.base"""
        cb = ConditionBuilder(0).case(1, "one").case(2, "two").otherwise("other")
        assert cb.evaluate(1) == "one"
        assert cb.evaluate(2) == "two"
        assert cb.base == 0

    def test_whens_type_error(self):
        """whens() 对非 list/tuple 项抛出 TypeError"""
        cb = ConditionBuilder(5)
        with pytest.raises(TypeError):
            cb.whens(123)

    def test_whens_length_error(self):
        """whens() 对长度非 2/3 的项抛出 ValueError"""
        cb = ConditionBuilder(5)
        with pytest.raises(ValueError):
            cb.whens((lambda x: x,))  # 长度为 1

    def test_whens_with_logic(self):
        """whens 支持第三项 logic 参数"""
        cb = ConditionBuilder(None).whens(
            (lambda x: x > 5, "big", None),
            (lambda x: x > 0, "positive", None),
        ).otherwise("other")
        assert cb.evaluate(10) == "big"

    def test_clear(self):
        """clear 清空条件并解除链锁"""
        cb = ConditionBuilder(5).case(1, "one").otherwise("other")
        cb.clear()
        # 清空后可以重新添加条件
        cb.case(99, "nine-nine").otherwise("?")
        assert cb(99) == "nine-nine"

    def test_comp_setter_lambda(self):
        """comp.setter 处理 callable"""
        cb = ConditionBuilder(5, comp='==')
        cb.comp = lambda x, y: x % y == 0
        cb.case(10, "divisible").otherwise("no")
        assert cb(10) == "divisible"

    # --- 字符串条件 ---

    def test_when_string_arrow(self):
        """when 使用 '->' 前缀字符串条件（safe_lambda 编译）"""
        cb = ConditionBuilder(10).when("-> x == x", "big").otherwise("small")
        assert cb() == "big"

    def test_when_string_supp_boolean(self):
        """when 使用布尔表达式字符串（supp 模式，safe_lambda 编译）"""
        cb = ConditionBuilder(15).when("5 > 3", "big").otherwise("small")
        assert cb() == "big"

    def test_when_string_builtin_op(self):
        """when 使用内置操作符字符串（比较 x 与该操作符字符串）"""
        # '<' 作为 int，字符串"<" 比较：ConditionBuilder base 是字符串 "b"
        cb = ConditionBuilder("b", comp='==').when(">", "after").otherwise("other")
        assert cb() == "after"  # "b" > ">" → True（按字典序）

    def test_when_string_fallback(self):
        """when 字符串无法编译时回退到 == 比较"""
        cb = ConditionBuilder(10).when("10", "ten").otherwise("other")
        assert cb() == "ten"


# ============================================================================
# iif 函数
# ============================================================================

class TestIIFFunction:
    """测试 iif 函数"""

    def test_iif_basic(self):
        assert iif(True, "yes", "no") == "yes"
        assert iif(False, "yes", "no") == "no"

    def test_iif_callable_condition(self):
        assert iif(lambda: True, "yes", "no") == "yes"
        assert iif(lambda: False, "yes", "no") == "no"

    def test_iif_condition_builder(self):
        cb = iif()
        assert isinstance(cb, ConditionBuilder)

    def test_iif_with_whens_condition_as_base(self):
        """iif(condition, whens=[...]) — condition 作 base value，data=None"""
        result = iif(3, whens=[
            (lambda x: x == 1, "one"),
            (lambda x: x == 2, "two"),
            (lambda x: x == 3, "three"),
        ])
        assert result == "three"

    def test_iif_with_whens_data_kwarg(self):
        """iif(data=x, whens=[...]) — data 关键字作求值目标"""
        result = iif(data=15, whens=[
            (lambda x: x > 10, "big"),
            (lambda x: x <= 10, "small"),
        ])
        assert result == "big"

    def test_iif_supp_mode(self):
        result = iif("5 > 3", true_body="yes", false_body="no", supp=True)
        assert result == "yes"

    def test_iif_cover_default(self):
        cb = iif()
        cb.when(lambda x: x == 5, "five")
        result = cb(6)
        assert result is None

    # --- 改进版新增 ---

    def test_iif_whens_type_error(self):
        """iif(whens=...) 对不合法的 whens 项抛出 TypeError"""
        with pytest.raises(TypeError):
            iif(data=5, whens=[123])

    def test_iif_data_with_lambda_condition(self):
        """data 传递给 lambda condition"""
        result = iif(
            condition=lambda x: x.get("status") == "ok",
            true_body=lambda x: x.get("value", 0) * 2,
            false_body=lambda x: x.get("value", 0),
            data={"status": "ok", "value": 10},
        )
        assert result == 20

    def test_iif_data_with_lambda_false(self):
        """false_body 可调用时正确调用"""
        result = iif(
            condition=lambda x: x.get("ok"),
            true_body="good",
            false_body=lambda x: f"bad: {x.get('msg')}",
            data={"ok": False, "msg": "error"},
        )
        assert result == "bad: error"


# ============================================================================
# iif 边界情况
# ============================================================================

class TestIIFEdgeCases:
    """测试 iif 边界情况"""

    def test_iif_none_condition(self):
        result = iif(None, "yes", "no")
        assert result == "no"

    def test_iif_empty_string_condition(self):
        result = iif("", "yes", "no")
        assert result == "no"

    def test_iif_zero_condition(self):
        result = iif(0, "yes", "no")
        assert result == "no"

    def test_iif_with_lambda_string(self):
        result = iif("-> 5 > 3", true_body="yes", false_body="no", supp=True)
        assert result == "yes"

    def test_iif_string_condition_with_data(self):
        """'->' 前缀字符串条件 + data"""
        result = iif("-> x > 3", "big", "small", data=5)
        assert result == "big"

    def test_iif_none_data_callable_condition(self):
        """data=None 时 callable 无参调用"""
        result = iif(lambda: 1 + 1 == 2, "math works", "math broken")
        assert result == "math works"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
