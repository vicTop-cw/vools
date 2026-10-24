# -*- coding: utf-8 -*-
"""回归测试：render_template 残留指令 + 文本函数 None 输入（BUG-465）。

修复前 ``render_template`` 是正则迷你引擎且**零校验**：

    render_template('{% if %}', {})        # -> '{% if %}'   ← 原样留在输出（静默垃圾）
    render_template('{% if x %}body', {x:1})  # -> 原样（未闭合）

使用者在"渲染结果"里看到原始指令却没有任何报错。修复后渲染完若仍残留
``{{变量}}`` / ``{% if|else|endif|for|endfor %}`` 指令即抛 ValueError。

同时 ``extract_frontmatter`` / ``count_words`` 对 None 输入原来抛
``'NoneType' object has no attribute 'split'``（看不出参数），现为带参数名的
TypeError。
"""

import pytest

import vools.md as md


class TestRenderTemplateLeftoverDirectives:
    @pytest.mark.parametrize("template,ctx", [
        ("{% if %}", {}),
        ("{% if x %}body", {"x": 1}),
        ("{% for i in xs %}{{ i }}", {"xs": [1]}),
        ("{% endif %}", {}),
    ])
    def test_broken_template_is_loud(self, template, ctx):
        with pytest.raises(ValueError) as ei:
            md.render_template(template, ctx)
        assert "指令" in str(ei.value)

    def test_non_str_template(self):
        with pytest.raises(TypeError) as ei:
            md.render_template(None, {})
        assert "template" in str(ei.value)


class TestValidTemplates:
    def test_variable(self):
        assert md.render_template("Hi {{ name }}", {"name": "W"}) == "Hi W"

    def test_if_else(self):
        tpl = "{% if x %}Y{% else %}N{% endif %}"
        assert md.render_template(tpl, {"x": True}) == "Y"
        assert md.render_template(tpl, {"x": False}) == "N"

    def test_for_loop(self):
        tpl = "{% for i in xs %}[{{ i }}]{% endfor %}"
        assert md.render_template(tpl, {"xs": [1, 2]}) == "[1]\n[2]"

    def test_plain_text_passthrough(self):
        assert md.render_template("hello", {}) == "hello"


class TestMarkdownTextValidation:
    @pytest.mark.parametrize("bad", [None, 123, ["# H"]])
    def test_extract_frontmatter(self, bad):
        with pytest.raises(TypeError) as ei:
            md.extract_frontmatter(bad)
        assert "markdown_text" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123])
    def test_count_words(self, bad):
        with pytest.raises(TypeError) as ei:
            md.count_words(bad)
        assert "markdown_text" in str(ei.value)

    def test_valid_paths(self):
        assert md.extract_frontmatter("---\ntitle: T\n---\n\n# H") == {"title": "T"}
        assert md.extract_frontmatter("# 无 frontmatter") == {}
        assert md.count_words("# H\n\nhello world") == 3
        assert md.count_words("") == 0
