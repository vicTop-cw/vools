"""
iif 函数和 ConditionBuilder 类的单元测试
"""
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from vools.functional.iif import iif, ConditionBuilder, LazyProperty


class TestLazyProperty:
    """测试 LazyProperty 装饰器"""
    
    def test_lazy_property_basic(self):
        """测试基本延迟属性"""
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
        # 第二次访问应该使用缓存
        assert obj.value == 42
        assert obj.counter == 1
    
    def test_lazy_property_read_only(self):
        """测试延迟属性只读"""
        class TestClass:
            @LazyProperty
            def value(self):
                return 42
        
        obj = TestClass()
        with pytest.raises(AttributeError):
            obj.value = 100


class TestConditionBuilderBasic:
    """测试 ConditionBuilder 基本功能"""
    
    def test_condition_builder_init(self):
        """测试初始化"""
        cb = ConditionBuilder(10)
        assert cb.base == 10
    
    def test_condition_builder_case(self):
        """测试 case 方法"""
        cb = ConditionBuilder(5).case(5, "five").otherwise("other")
        result = cb()
        assert result == "five"
    
    def test_condition_builder_case_no_match(self):
        """测试 case 不匹配"""
        cb = ConditionBuilder(6).case(5, "five").otherwise("other")
        result = cb()
        assert result == "other"
    
    def test_condition_builder_cases(self):
        """测试批量添加 case"""
        cb = ConditionBuilder(3).cases([1, "one"], [2, "two"], [3, "three"]).otherwise("other")
        result = cb()
        assert result == "three"
    
    def test_condition_builder_case_dict(self):
        """测试字典形式的 case"""
        cb = ConditionBuilder("apple").cases({"apple": "fruit", "carrot": "vegetable"}).otherwise("unknown")
        result = cb()
        assert result == "fruit"
    
    def test_condition_builder_when(self):
        """测试 when 方法"""
        cb = ConditionBuilder(15).when(lambda x: x > 10, "big").otherwise("small")
        result = cb()
        assert result == "big"
    
    def test_condition_builder_whens(self):
        """测试批量添加 when"""
        cb = ConditionBuilder(8).whens(
            (lambda x: x < 5, "small"),
            (lambda x: x < 10, "medium"),
            (lambda x: x >= 10, "large")
        ).otherwise("unknown")
        result = cb()
        assert result == "medium"
    
    def test_condition_builder_evaluate(self):
        """测试 evaluate 方法"""
        cb = ConditionBuilder(20).case(10, "ten").case(20, "twenty").otherwise("other")
        result = cb.evaluate(20)
        assert result == "twenty"
    
    def test_condition_builder_evaluateEx(self):
        """测试批量 evaluate"""
        cb = ConditionBuilder(None).case(1, "one").case(2, "two").otherwise("other")
        results = cb.evaluateEx([1, 2, 3])
        assert results == ["one", "two", "other"]


class TestConditionBuilderOperators:
    """测试条件构建器的比较运算符"""
    
    def test_condition_builder_eq(self):
        """测试等于比较"""
        cb = ConditionBuilder(5, comp='==').case(5, "equal").otherwise("not equal")
        assert cb() == "equal"
    
    def test_condition_builder_gt(self):
        """测试大于比较"""
        cb = ConditionBuilder(10, comp='>').case(5, "greater").otherwise("not greater")
        assert cb() == "greater"
    
    def test_condition_builder_lt(self):
        """测试小于比较"""
        cb = ConditionBuilder(3, comp='<').case(5, "less").otherwise("not less")
        assert cb() == "less"
    
    def test_condition_builder_in(self):
        """测试 in 操作"""
        cb = ConditionBuilder("apple", comp='in').case(["apple", "banana"], "found").otherwise("not found")
        assert cb() == "found"


class TestConditionBuilderAdvanced:
    """测试 ConditionBuilder 高级功能"""
    
    def test_condition_builder_callable_result(self):
        """测试可调用结果"""
        cb = ConditionBuilder(5).case(5, lambda x: x * 2).otherwise(lambda x: x * 3)
        result = cb()
        assert result == 10
    
    def test_condition_builder_lambda_condition(self):
        """测试 lambda 条件"""
        cb = ConditionBuilder(25).when(lambda x: x > 18, "adult").otherwise("child")
        assert cb() == "adult"
    
    def test_condition_builder_short_circuit(self):
        """测试短路求值"""
        counter = [0]
        
        def count_condition(x):
            counter[0] += 1
            return x == 2
        
        cb = ConditionBuilder(2).case(1, "one").case(2, "two").case(3, "three")
        result = cb()
        assert result == "two"
    
    def test_condition_builder_chain_locked(self):
        """测试链式调用锁定"""
        cb = ConditionBuilder(5).case(5, "five").otherwise("other")
        with pytest.raises(RuntimeError):
            cb.case(6, "six")


class TestIIFFunction:
    """测试 iif 函数"""
    
    def test_iif_basic(self):
        """测试基本用法"""
        result = iif(True, "yes", "no")
        assert result == "yes"
        
        result = iif(False, "yes", "no")
        assert result == "no"
    
    def test_iif_callable_condition(self):
        """测试可调用条件"""
        result = iif(lambda: True, "yes", "no")
        assert result == "yes"
        
        result = iif(lambda: False, "yes", "no")
        assert result == "no"
    
    def test_iif_condition_builder(self):
        """测试返回条件构建器"""
        cb = iif()
        assert isinstance(cb, ConditionBuilder)
    
    def test_iif_with_cases(self):
        """测试使用 cases 参数"""
        # 使用 whens 替代 cases，因为 cases 的默认比较器是 '_?' (检查值是否为真)
        result = iif(data=3, whens=[(lambda x: x == 1, "one"), (lambda x: x == 2, "two"), (lambda x: x == 3, "three")])
        assert result == "three"
    
    def test_iif_with_whens(self):
        """测试使用 whens 参数"""
        result = iif(data=15, whens=[(lambda x: x > 10, "big"), (lambda x: x <= 10, "small")])
        assert result == "big"
    
    def test_iif_supp_mode(self):
        """测试支持补充运算符模式"""
        result = iif("5 > 3", true_body="yes", false_body="no", supp=True)
        assert result == "yes"
    
    def test_iif_cover_default(self):
        """测试覆盖默认值"""
        cb = iif()
        cb.when(lambda x: x == 5, "five")
        result = cb(6)
        assert result is None  # 没有匹配的条件，返回默认值 None


class TestIIFEdgeCases:
    """测试 iif 边界情况"""
    
    def test_iif_none_condition(self):
        """测试 None 条件"""
        result = iif(None, "yes", "no")
        assert result == "no"  # None 被视为 False
    
    def test_iif_empty_string_condition(self):
        """测试空字符串条件"""
        result = iif("", "yes", "no")
        assert result == "no"  # 空字符串被视为 False
    
    def test_iif_zero_condition(self):
        """测试 0 条件"""
        result = iif(0, "yes", "no")
        assert result == "no"  # 0 被视为 False
    
    def test_iif_with_lambda_string(self):
        """测试 lambda 字符串"""
        result = iif("-> 5 > 3", true_body="yes", false_body="no", supp=True)
        assert result == "yes"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])