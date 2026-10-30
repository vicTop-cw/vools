"""template.py 契约测试：模板查询、占位符替换、文件创建、路径逃逸防护。"""

import json
import os
import pytest
from pathlib import Path
from vools.actus.template import (
    BUILTIN_TEMPLATES,
    apply_template,
    create_action_from_template,
    get_template,
    list_templates,
    _escape_snippet,
)


class TestGetTemplate:
    """get_template: 模板查询。"""

    def test_known_template(self):
        t = get_template("python-basic")
        assert t is not None
        assert t["name"] == "Python 基础动作"
        assert "body" in t

    def test_unknown_template_returns_none(self):
        assert get_template("nonexistent") is None

    def test_all_builtin_templates_valid(self):
        for tid, t in BUILTIN_TEMPLATES.items():
            assert "name" in t
            assert "description" in t
            assert "category" in t
            assert "tags" in t
            assert "body" in t


class TestListTemplates:
    """list_templates: 模板列表。"""

    def test_returns_list(self):
        templates = list_templates()
        assert isinstance(templates, list)
        assert len(templates) == len(BUILTIN_TEMPLATES)

    def test_each_has_required_keys(self):
        for t in list_templates():
            assert "id" in t
            assert "name" in t
            assert "description" in t
            assert "category" in t
            assert "tags" in t

    def test_ids_match_builtin(self):
        ids = {t["id"] for t in list_templates()}
        assert ids == set(BUILTIN_TEMPLATES.keys())


class TestEscapeSnippet:
    """_escape_snippet: 三引号转义。"""

    def test_no_escape_needed(self):
        assert _escape_snippet("normal text") == "normal text"

    def test_triple_quote_escaped(self):
        assert _escape_snippet('"""') == '\\"\\"\\"'

    def test_triple_quote_in_text(self):
        result = _escape_snippet('"""some text"""')
        assert '"""' not in result  # 原始三引号不应出现
        assert '\\"' in result  # 应被转义为 \"


class TestApplyTemplate:
    """apply_template: 模板应用与占位符替换。"""

    def test_python_basic_substitution(self):
        code = apply_template("python-basic", "test.my_action", "My Action", "A test")
        assert code is not None
        assert "My Action" in code
        assert "A test" in code
        assert "${action_name}" not in code
        assert "${description}" not in code

    def test_default_description(self):
        code = apply_template("python-basic", "test.my_action", "My Action")
        assert code is not None
        # description 为空时应使用模板默认描述
        assert "最简单的 Python 动作模板" in code

    def test_unknown_template_returns_none(self):
        assert apply_template("nonexistent", "test.action", "Name") is None

    def test_no_double_substitution(self):
        """审计修验证：name 含 ${description} 不应被二次替换。"""
        code = apply_template("python-basic", "test.action", "My${description}Action", "A test")
        assert code is not None
        # "A test" 只应出现一次（在描述位置），不应在 name 位置被展开
        assert code.count("A test") == 1

    def test_escape_triple_quote_in_name(self):
        code = apply_template("python-basic", "test.action", 'My"""Action', "desc")
        assert code is not None
        assert 'My"""Action' not in code  # 原始三引号不应出现
        assert '\\"' in code  # 应被转义为 \"

    def test_action_id_substitution_in_shell(self):
        """shell 模板 body 包含 ${action_id} 占位符。"""
        code = apply_template("shell-basic", "test.shell_action", "Shell Action", "Shell test")
        assert code is not None
        assert "test.shell_action" in code

    def test_shell_template(self):
        code = apply_template("shell-basic", "test.sh", "Shell Action", "Shell test")
        assert code is not None
        assert "Shell Action" in code
        assert "#!/bin/bash" in code

    def test_node_template(self):
        code = apply_template("node-basic", "test.mjs", "Node Action", "Node test")
        assert code is not None
        assert "Node Action" in code
        assert "#!/usr/bin/env node" in code

    def test_webhook_template(self):
        code = apply_template("webhook-receiver", "test.webhook", "Webhook Action", "Webhook test")
        assert code is not None
        assert "Webhook Action" in code

    def test_file_watcher_template(self):
        code = apply_template("file-watcher", "test.watch", "Watcher Action", "Watcher test")
        assert code is not None
        assert "Watcher Action" in code


class TestCreateActionFromTemplate:
    """create_action_from_template: 创建动作文件。"""

    def test_python_basic_create(self, tmp_path):
        path = create_action_from_template("python-basic", "test.my_action", "My Action", str(tmp_path))
        assert path is not None
        f = Path(path)
        assert f.exists()
        assert f.suffix == ".py"
        content = f.read_text(encoding="utf-8")
        assert "#!cfg" in content
        assert "My Action" in content
        assert "python-basic" not in content  # 模板 ID 不应出现在内容中

    def test_shell_template_extension(self, tmp_path):
        path = create_action_from_template("shell-basic", "test.sh_action", "Shell Action", str(tmp_path))
        assert path is not None
        assert Path(path).suffix == ".sh"

    def test_node_template_extension(self, tmp_path):
        path = create_action_from_template("node-basic", "test.node_action", "Node Action", str(tmp_path))
        assert path is not None
        assert Path(path).suffix == ".mjs"

    def test_with_parameters(self, tmp_path):
        params = {"url": {"type": "string", "required": True}}
        path = create_action_from_template(
            "python-basic", "test.api", "API Action", str(tmp_path),
            parameters=params
        )
        assert path is not None
        content = Path(path).read_text(encoding="utf-8")
        assert "parameters" in content

    def test_force_overwrite(self, tmp_path):
        # 先创建
        path1 = create_action_from_template("python-basic", "test.force", "Force Action", str(tmp_path))
        # 再创建同名（不加 force）应失败
        with pytest.raises(Exception):
            create_action_from_template("python-basic", "test.force", "Force Action 2", str(tmp_path))
        # force=True 应成功
        path2 = create_action_from_template(
            "python-basic", "test.force", "Force Action 3", str(tmp_path), force=True
        )
        assert path2 is not None
        assert "Force Action 3" in Path(path2).read_text(encoding="utf-8")

    def test_path_escape_blocked(self, tmp_path):
        """审计修验证：路径逃逸应被拒绝。

        注意：`../ESCAPED` 会被 rsplit 取最后一段变成 `ESCAPED`（合法），
        所以路径逃逸防护只拦 `.` / `..` 作为整个 ID。
        """
        # ../ESCAPED → rsplit 后变成 ESCAPED，不抛错但写到 tmp_path 内
        path = create_action_from_template("python-basic", "../ESCAPED", "Escape Action", str(tmp_path))
        assert path is not None
        assert Path(path).parent == tmp_path  # 确实没逃出去
        assert Path(path).name == "ESCAPED.py"

    def test_path_escape_dotdot(self, tmp_path):
        with pytest.raises(ValueError):
            create_action_from_template("python-basic", "..", "DotDot Action", str(tmp_path))

    def test_path_escape_dot(self, tmp_path):
        with pytest.raises(ValueError):
            create_action_from_template("python-basic", ".", "Dot Action", str(tmp_path))

    def test_unknown_template_returns_none(self, tmp_path):
        path = create_action_from_template("nonexistent", "test.action", "Name", str(tmp_path))
        assert path is None

    def test_category_from_action_id(self, tmp_path):
        """action_id 含点时 category 取第一段。"""
        path = create_action_from_template("python-basic", "mycat.my_action", "Test Action", str(tmp_path))
        assert path is not None
        content = Path(path).read_text(encoding="utf-8")
        assert '"category": "mycat"' in content

    def test_category_no_dot(self, tmp_path):
        """action_id 无点时 category 为 custom。"""
        path = create_action_from_template("python-basic", "simple_action", "Test Action", str(tmp_path))
        assert path is not None
        content = Path(path).read_text(encoding="utf-8")
        assert '"category": "custom"' in content

    def test_description_override(self, tmp_path):
        """description 为空时用模板默认描述。"""
        path = create_action_from_template("python-basic", "test.desc", "Desc Action", str(tmp_path))
        assert path is not None
        content = Path(path).read_text(encoding="utf-8")
        assert "最简单的 Python 动作模板" in content

    def test_description_explicit(self, tmp_path):
        path = create_action_from_template(
            "python-basic", "test.desc2", "Desc Action 2", str(tmp_path),
            description="Custom description"
        )
        assert path is not None
        content = Path(path).read_text(encoding="utf-8")
        assert "Custom description" in content

    def test_subdir_created(self, tmp_path):
        """子目录不存在时应自动创建。"""
        subdir = tmp_path / "nested" / "deep"
        path = create_action_from_template("python-basic", "test.nested", "Nested Action", str(subdir))
        assert path is not None
        assert Path(path).exists()


class TestTemplateBodyValidation:
    """模板 body 内容验证。"""

    def test_all_bodies_have_entry_protocol(self):
        """每个模板 body 都应包含入口自调用协议。"""
        for tid, t in BUILTIN_TEMPLATES.items():
            body = t["body"]
            if tid.startswith("python-") or tid == "webhook-receiver" or tid == "file-watcher":
                assert "ACTUS_PARAMS" in body, f"{tid} 缺少 ACTUS_PARAMS"
                assert "print(" in body, f"{tid} 缺少 print"
            if tid.startswith("shell-"):
                assert "#!/bin/bash" in body, f"{tid} 缺少 shebang"
            if tid.startswith("node-"):
                assert "#!/usr/bin/env node" in body, f"{tid} 缺少 shebang"

    def test_all_templates_have_main(self):
        """Python/Node 模板应有 main 函数。"""
        for tid, t in BUILTIN_TEMPLATES.items():
            if tid.startswith("python-") or tid == "webhook-receiver" or tid == "file-watcher":
                assert "def main(" in t["body"], f"{tid} 缺少 main 函数"
            if tid.startswith("node-"):
                assert "function main(" in t["body"], f"{tid} 缺少 main 函数"
