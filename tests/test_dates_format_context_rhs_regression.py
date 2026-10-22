# -*- coding: utf-8 -*-
"""回归测试：上下文更新串的赋值 RHS 支持表达式（BUG-299）。

`EnhancedDateFormatter._evaluate_context_update` 的赋值分支原只走
`_parse_value`（字面量解析），RHS 引用已有变量的表达式被**原样存成字符串**：
- `{x<-1;y<-x+1;y}` -> `'x+1'`（应 2）
- `{x<-1;y<-x+1;y*2}` -> `'x+1x+1'`（字符串重复，静默错值）
- `{x<-1;y<-x+1;x+y}` -> 整串回退原文
而 BUG-239 注释声称保持「同串内先赋值后引用可见」语义——该语义对赋值链不成立。

修复：`_parse_value` 返回字符串时再尝试 `safe_eval_expression(var_value,
vars=staged)`，失败保留原值；带引号字符串字面量求值结果与原值一致，不受影响。
"""

import pytest

from vools.datetime.dates_format import EnhancedDateFormatter as E


class TestAssignmentRhsExpressions:
    @pytest.mark.parametrize('template,expected', [
        ('{x<-1;y<-x+1;y}', '2'),
        ('{x<-1;y<-x*2;y}', '2'),
        ('{x<-5;y<-x-1;y}', '4'),
        ('{x<-5;y<-x;y}', '5'),
        ('{a<-2;b<-a*a;b}', '4'),
        ('{x<-1;y<-x + 1;y}', '2'),
    ])
    def test_rhs_referencing_variable(self, template, expected):
        # 修复前：返回 'x+1' / 'x*2' / 'x-1' / 'x' / 'a*a' 等未求值文本
        assert E(template).format() == expected

    def test_string_multiplication_no_longer_degenerates(self):
        # 修复前 'x+1x+1'（y 为字符串 'x+1' 时 y*2 触发字符串重复）
        assert E('{x<-1;y<-x+1;y*2}').format() == '4'

    def test_final_expression_combines(self):
        # 修复前整串回退原文（1 + 'x+1' TypeError 被 catch）
        assert E('{x<-1;y<-x+1;x+y}').format() == '3'


class TestLiteralsUnaffected:
    def test_pure_numbers(self):
        assert E('{x<-10;y<-20;x+y}').format() == '30'

    def test_docstring_example(self):
        assert E('{name <- "张三" ; age <- 30 ; age + 10}').format() == '40'

    def test_quoted_string_not_evaluated(self):
        # 带引号的字符串字面量必须保持原文，不被当作表达式
        assert E('{s <- "1+1" ; s}').format() == '1+1'

    def test_undefined_name_kept(self):
        assert E('{s <- abc ; s}').format() == 'abc'

    def test_list_literal(self):
        assert E('{items <- [1,2,3] ; len(items)}').format() == '3'

    def test_date_placeholder_still_works(self):
        assert E('{run_date-1}', default_run_date='2026-02-26').format() == '20260225'