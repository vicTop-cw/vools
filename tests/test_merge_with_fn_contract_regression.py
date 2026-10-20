# -*- coding: utf-8 -*-
"""回归测试：merge_with 每键统一经 fn（BUG-218）。

原实现对只出现在一个字典里的键（len(values)==1）旁路合并函数、原样透传
——违背 docstring「fn 接收多个值返回合并结果」（fn 为唯一合并通道）与
toolz 同名函数每键必调语义，产出类型不一致的混合结果且无告警。

修复：删除单值旁路，所有键统一 `fn(*values)`（TypeError 回退 `fn(values)`
的兼容策略保留）。
"""

from vools.curried.collection import merge_with


class TestEveryKeyGoesThroughFn:
    """BUG-218 核心：fn 是每键唯一合并通道。"""

    def test_single_value_keys_call_fn(self):
        seen = []

        def counting_fn(*vals):
            seen.append(vals)
            return sum(vals)

        result = merge_with(counting_fn)({'a': 1}, {'b': 2})
        assert len(seen) == 2                       # 原实现：fn 零调用
        assert result == {'a': 1, 'b': 2}

    def test_transformer_applies_to_all_keys(self):
        # toolz 迁移直觉：merge_with(str) 之类变换应覆盖全部键
        result = merge_with(lambda v: v * 2)({'a': 1}, {'a': 3, 'b': 2})
        assert result['b'] == 4                     # 原实现：b 旁路为 2

    def test_max_combinator_single_value(self):
        # max(1) TypeError → 回退 max([1])==1，兼容路径覆盖单值键
        result = merge_with(max)({'a': 1}, {'b': 2})
        assert result == {'a': 1, 'b': 2}

    def test_sum_combinator_single_value(self):
        result = merge_with(sum)({'a': 1}, {'b': 2})
        assert result == {'a': 1, 'b': 2}


class TestMultiValueSemanticsUnchanged:
    """多值键原语义保持（防修复过度）。"""

    def test_docstring_example(self):
        result = merge_with(sum)({'a': 1, 'b': 2}, {'a': 3, 'b': 4}, {'a': 5})
        assert sorted(result.items()) == [('a', 9), ('b', 6)]

    def test_mixed_keys(self):
        result = merge_with(sum)({'a': 1, 'b': 2}, {'a': 3})
        # b 单值经 sum([2])==2，与旁路等值（sum 场景数值不变）
        assert sorted(result.items()) == [('a', 4), ('b', 2)]