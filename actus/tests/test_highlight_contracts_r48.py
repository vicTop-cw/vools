"""highlight.py 契约测试：语言映射、Shiki 调用、Markdown 解析、错误处理。"""

import pytest
import os
from unittest.mock import patch, MagicMock
from vools.actus.highlight import (
    LANGUAGE_MAP,
    CODEBLOCK_LANG_MAP,
    SHIKI_SCRIPT,
    _resolve_lang,
    check_shiki_available,
    highlight_code,
    highlight_file,
    highlight_actus_md,
    highlight_actus_file,
    get_available_themes,
    get_available_languages,
    preview_terminal,
    preview_html,
    preview_file_terminal,
    preview_file_html,
)


class TestResolveLang:
    """_resolve_lang: 语言映射解析。"""

    @pytest.mark.parametrize("lang,expected", [
        ("python", "python"),
        ("py", "python"),
        ("javascript", "javascript"),
        ("js", "javascript"),
        ("typescript", "typescript"),
        ("ts", "typescript"),
        ("tsx", "tsx"),
        ("jsx", "jsx"),
        ("go", "go"),
        ("rust", "rust"),
        ("rs", "rust"),
        ("bash", "bash"),
        ("sh", "bash"),
        ("shell", "bash"),
        # zsh NOT in CODEBLOCK_LANG_MAP — inconsistency with LANGUAGE_MAP
        ("json", "json"),
        ("yaml", "yaml"),
        ("yml", "yaml"),
        ("toml", "toml"),
        ("md", "markdown"),
        ("html", "html"),
        ("css", "css"),
        ("sql", "sql"),
        ("dockerfile", "dockerfile"),
        ("ini", "ini"),
        ("xml", "xml"),
    ])
    def test_known_langs(self, lang, expected):
        assert _resolve_lang(lang) == expected

    def test_case_insensitive(self):
        assert _resolve_lang("PYTHON") == "python"
        assert _resolve_lang("PY") == "python"

    def test_unknown_lang_passthrough(self):
        assert _resolve_lang("rust2") == "rust2"
        assert _resolve_lang("cobol") == "cobol"


class TestCheckShikiAvailable:
    """check_shiki_available: Shiki 可用性检查。"""

    def test_available(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            assert check_shiki_available() is True

    def test_unavailable(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            assert check_shiki_available() is False

    def test_exception_returns_false(self):
        with patch("vools.actus.highlight.run_cmd_safe",
                    side_effect=Exception("node not found")):
            assert check_shiki_available() is False


class TestHighlightCode:
    """highlight_code: 代码高亮调用。"""

    def test_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\x1b[33mhello\x1b[0m"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = highlight_code("hello", lang="python")
            assert out == "\x1b[33mhello\x1b[0m"

    def test_nonzero_returncode_returns_original(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = highlight_code("hello", lang="python")
            assert out == "hello"

    def test_exception_returns_original(self):
        with patch("vools.actus.highlight.run_cmd_safe",
                    side_effect=Exception("spawn failed")):
            out = highlight_code("hello", lang="python")
            assert out == "hello"

    def test_empty_stdout(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = highlight_code("hello", lang="python")
            assert out == ""

    def test_html_mode(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "<span class=\"tok-kw\">print</span>"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = highlight_code("print", lang="python", mode="html")
            assert out == "<span class=\"tok-kw\">print</span>"


class TestHighlightFile:
    """highlight_file: 文件高亮。"""

    def test_success(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print('hello')", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\x1b[33mprint\x1b[0m"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = highlight_file(str(f))
            assert out == "\x1b[33mprint\x1b[0m"

    def test_nonexistent_returns_empty(self, tmp_path):
        out = highlight_file(str(tmp_path / "nope.py"))
        assert out == ""

    def test_bad_encoding_returns_empty(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_bytes(b'\xff\xfe\x00\x01\x02')
        out = highlight_file(str(f))
        assert out == ""

    def test_unknown_ext_passthrough(self, tmp_path):
        f = tmp_path / "test.unknownext"
        f.write_text("some code", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "highlighted"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = highlight_file(str(f))
            assert out == "highlighted"


class TestHighlightActusMd:
    """highlight_actus_md: Markdown 代码块解析与高亮。"""

    def test_code_block_highlighted(self):
        md = "Some text\n```python\nprint('hi')\n```\nMore text"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\x1b[33mHI\x1b[0m"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = highlight_actus_md(md)
            assert "```python" in out
            assert "HI" in out

    def test_html_mode_wraps_in_fences(self):
        md = "```python\nprint('hi')\n```"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "<span>hi</span>"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = highlight_actus_md(md, mode="html")
            assert "```python" in out
            assert "<span>hi</span>" in out

    def test_no_code_blocks(self):
        md = "Just plain text, no code blocks here."
        out = highlight_actus_md(md)
        assert out == md

    def test_multiple_code_blocks(self):
        md = "```python\nx=1\n```\n\n```json\n{}\n```\nend"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "HI"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = highlight_actus_md(md)
            # 两个代码块都应该被处理
            assert out.count("HI") == 2

    def test_code_block_with_no_lang(self):
        # 没有语言标记的代码块不被匹配
        md = "```\nsome code\n```"
        out = highlight_actus_md(md)
        assert out == md


class TestHighlightActusFile:
    """highlight_actus_file: 读取 .actus.md 并高亮。"""

    def test_success(self, tmp_path):
        f = tmp_path / "test.actus.md"
        f.write_text("```python\nprint(1)\n```", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "HI"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = highlight_actus_file(str(f))
            assert "HI" in out

    def test_nonexistent_returns_empty(self, tmp_path):
        out = highlight_actus_file(str(tmp_path / "nope.md"))
        assert out == ""


class TestGetAvailableThemes:
    """get_available_themes: 主题列表。"""

    def test_returns_list(self):
        themes = get_available_themes()
        assert isinstance(themes, list)
        assert len(themes) > 0
        assert "github-dark" in themes


class TestGetAvailableLanguages:
    """get_available_languages: 语言列表。"""

    def test_returns_sorted_unique(self):
        langs = get_available_languages()
        assert isinstance(langs, list)
        assert len(langs) == len(set(langs))
        assert langs == sorted(langs)
        assert "python" in langs
        assert "javascript" in langs


class TestPreviewFunctions:
    """preview_* 便捷函数。"""

    def test_preview_terminal(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "HI"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = preview_terminal("print", lang="python")
            assert out == "HI"

    def test_preview_html(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "<span>HI</span>"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = preview_html("print", lang="python")
            assert out == "<span>HI</span>"

    def test_preview_file_terminal(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print(1)", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "HI"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = preview_file_terminal(str(f))
            assert out == "HI"

    def test_preview_file_html(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print(1)", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "<span>HI</span>"
        with patch("vools.actus.highlight.run_cmd_safe", return_value=mock_result):
            out = preview_file_html(str(f))
            assert out == "<span>HI</span>"
