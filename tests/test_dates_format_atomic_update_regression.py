# -*- coding: utf-8 -*-
"""回归测试：上下文更新串原子化（BUG-239）。

原 `_evaluate_context_update` 边解析边写 `self.context`，后续步骤失败被
catch-all 吞掉返回原文——**部分赋值残留 + 真实错误静默**。实测
`{x <- 10 ; y <- 20 ; 1/0}` 后 x/y 已生效（脏状态）、输出原文占位符。

修复：副本求值、全部成功才提交（`staged` 保证同串内先赋值后引用可见，
即 `{x <- 10 ; y <- 20 ; x + y} == 30` 语义不变）；失败路径仍返回原文
但不污染上下文。

注：单赋值形式 `{a <- 1}`（无分号）不在文档化语法内（gate 要求 `<-` 且有
`;`），保持返回原文行为，不在本回归范围。
"""

from vools.datetime.dates_format import EnhancedDateFormatter


class TestAtomicUpdate:
    """BUG-239 核心：失败不留下部分赋值。"""

    def test_division_by_zero_no_partial_state(self):
        f = EnhancedDateFormatter("{x <- 10 ; y <- 20 ; 1/0}")
        out = f.format()
        assert out == "{x <- 10 ; y <- 20 ; 1/0}"   # 原文占位符（既有可见行为）
        assert f.get('x') is None                    # 修复前: 10
        assert f.get('y') is None                    # 修复前: 20

    def test_unsafe_expression_no_partial_state(self):
        f = EnhancedDateFormatter("{k <- 5 ; __import__('os')}")
        out = f.format()
        assert out == "{k <- 5 ; __import__('os')}"  # 安全求值拒绝（BUG-101 保持）
        assert f.get('k') is None                    # 修复前: 5


class TestSuccessPathUnchanged:
    """成功路径语义保持（同串内先赋值后引用）。"""

    def test_assignments_then_expression(self):
        f = EnhancedDateFormatter("{x <- 10 ; y <- 20 ; x + y}")
        assert f.format() == "30"
        assert f.get('x') == 10
        assert f.get('y') == 20

    def test_string_values(self):
        f = EnhancedDateFormatter('{name <- "张三" ; age <- 30 ; name}')
        assert f.format() == "张三"
        assert f.get('name') == "张三"

    def test_assignments_only_returns_last(self):
        f = EnhancedDateFormatter("{a <- 1 ; b <- 2}")
        assert f.format() == "2"
        assert (f.get('a'), f.get('b')) == (1, 2)


class TestExistingContextPreserved:
    """成功提交不破坏既有上下文变量。"""

    def test_initial_context_kept(self):
        f = EnhancedDateFormatter("{a <- 1 ; a + 1}")
        assert f.format() == "2"
        assert f.get('a') == 1

    def test_context_param_visible(self):
        f = EnhancedDateFormatter("{base <- 10 ; base * 2}")
        assert f.format() == "20"