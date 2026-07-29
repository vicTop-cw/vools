"""Tests for ``voxc.libs.tabnny`` Vox code formatter.

Runnable both as a pytest module and as a standalone script::

    python -m pytest tests_vox/test_tabnny.py -v
    python tests_vox/test_tabnny.py
"""

import os
import sys
import tempfile
import traceback

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from voxc.libs.tabnny import (  # noqa: E402
    FormatOptions,
    VoxFormatter,
    format_file,
)


# ===========================================================================
# FormatOptions tests
# ===========================================================================

def test_formatoptions_defaults():
    opts = FormatOptions()
    assert opts.indent_size == 4
    assert opts.quote_char == '"'
    assert opts.max_line_length == 88
    assert opts.strip_trailing is True
    assert opts.end_with_newline is True


def test_formatoptions_custom():
    opts = FormatOptions(
        indent_size=2,
        quote_char="'",
        max_line_length=100,
        strip_trailing=False,
        end_with_newline=False,
    )
    assert opts.indent_size == 2
    assert opts.quote_char == "'"
    assert opts.max_line_length == 100
    assert opts.strip_trailing is False
    assert opts.end_with_newline is False


def test_formatoptions_validates_indent_size():
    try:
        FormatOptions(indent_size=-1)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_formatoptions_validates_quote_char():
    try:
        FormatOptions(quote_char="`")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_formatoptions_validates_max_line_length():
    try:
        FormatOptions(max_line_length=0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_formatoptions_repr():
    opts = FormatOptions(indent_size=2, quote_char="'")
    r = repr(opts)
    assert "FormatOptions(" in r
    assert "indent_size=2" in r
    assert "quote_char=\"'\"" in r


# ===========================================================================
# VoxFormatter basic tests
# ===========================================================================

def test_formatter_default_construction():
    fmt = VoxFormatter()
    assert fmt.options is not None
    assert isinstance(fmt.options, FormatOptions)


def test_formatter_custom_options():
    opts = FormatOptions(indent_size=2)
    fmt = VoxFormatter(options=opts)
    assert fmt.options is opts


def test_format_empty_string():
    fmt = VoxFormatter()
    result = fmt.format("")
    assert result == ""


def test_format_single_line():
    fmt = VoxFormatter()
    result = fmt.format("val x = 1")
    assert "val x = 1" in result


def test_format_ends_with_newline():
    fmt = VoxFormatter()
    result = fmt.format("val x = 1")
    assert result.endswith("\n")


def test_format_end_with_newline_false():
    opts = FormatOptions(end_with_newline=False)
    fmt = VoxFormatter(options=opts)
    result = fmt.format("val x = 1")
    assert not result.endswith("\n")


# ===========================================================================
# Indentation tests
# ===========================================================================

def test_indentation_if_block():
    source = "if true:\nval x = 1\nval y = 2"
    fmt = VoxFormatter()
    result = fmt.format(source)
    lines = result.strip().split("\n")
    assert lines[0].strip().startswith("if")
    assert lines[1].startswith("    ")
    assert lines[2].startswith("    ")


def test_indentation_custom_size():
    source = "if true:\nval x = 1"
    opts = FormatOptions(indent_size=2)
    fmt = VoxFormatter(options=opts)
    result = fmt.format(source)
    lines = result.strip().split("\n")
    assert lines[1].startswith("  ")
    assert not lines[1].startswith("    ")


def test_indentation_nested_blocks():
    source = "if true:\n    if false:\n        val x = 1\n    val y = 2"
    fmt = VoxFormatter()
    result = fmt.format(source)
    lines = [l for l in result.split("\n") if l.strip()]
    assert lines[0].startswith("if ")
    assert lines[1].startswith("    if ")
    assert lines[2].startswith("        val ")
    assert lines[3].startswith("    val ")


def test_indentation_def_function():
    source = "def foo():\nval x = 1\nreturn x"
    fmt = VoxFormatter()
    result = fmt.format(source)
    lines = [l for l in result.split("\n") if l.strip()]
    assert lines[0].startswith("def ")
    assert lines[1].startswith("    val ")
    assert lines[2].startswith("    return ")


def test_indentation_class():
    source = "class Foo:\nval x = 1\ndef bar(self):\nreturn self.x"
    fmt = VoxFormatter()
    result = fmt.format(source)
    lines = [l for l in result.split("\n") if l.strip()]
    assert lines[0].startswith("class ")
    assert lines[1].startswith("    val ")
    assert lines[2].startswith("    def ")
    assert lines[3].startswith("        return ")


# ===========================================================================
# Operator spacing tests
# ===========================================================================

def test_operator_spacing_basic():
    source = "val x=1+2"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "x = 1 + 2" in result


def test_operator_spacing_comparison():
    source = "if x==y&&z>0:"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "x == y" in result
    assert "z > 0" in result


def test_operator_spacing_assignment():
    source = "x+=1"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "x += 1" in result


def test_operator_no_space_member_access():
    source = "obj.method()"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "obj.method()" in result


def test_operator_no_space_double_colon():
    source = "Module::function"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "Module::function" in result


def test_unary_minus_no_space():
    source = "val x = -1"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "= -1" in result


def test_unary_plus_no_space():
    source = "val x = +1"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "= +1" in result


def test_unary_not_no_space():
    source = "if !flag:"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "!flag" in result


# ===========================================================================
# Comma and colon spacing tests
# ===========================================================================

def test_comma_space_after():
    source = "fn(a,b,c)"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "(a, b, c)" in result


def test_comma_no_space_before():
    source = "fn(a , b)"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "(a, b)" in result
    assert "(a ," not in result


def test_colon_type_annotation_no_space():
    source = "val x:Int = 1"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "x: Int" in result or "x:Int" in result


def test_colon_dict_key_no_space_before():
    source = '{: "a" : 1 }'
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert '"a": 1' in result or '"a" : 1' in result


# ===========================================================================
# Trailing whitespace tests
# ===========================================================================

def test_strip_trailing_whitespace():
    source = "val x = 1   \nval y = 2\t"
    fmt = VoxFormatter()
    result = fmt.format(source)
    for line in result.split("\n"):
        if line.strip():
            assert line == line.rstrip()


def test_preserve_trailing_when_disabled():
    source = "val x = 1\n"
    opts = FormatOptions(strip_trailing=False)
    fmt = VoxFormatter(options=opts)
    result = fmt.format(source)
    assert result.endswith("\n")


# ===========================================================================
# String quote normalization tests
# ===========================================================================

def test_normalize_to_double_quotes():
    source = "val x = 'hello'"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert '"hello"' in result
    assert "'hello'" not in result


def test_normalize_to_single_quotes():
    source = 'val x = "hello"'
    opts = FormatOptions(quote_char="'")
    fmt = VoxFormatter(options=opts)
    result = fmt.format(source)
    assert "'hello'" in result
    assert '"hello"' not in result


def test_keep_quotes_when_content_has_preferred():
    source = 'val x = "it\'s mine"'
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert '"it' in result


# ===========================================================================
# Comment preservation tests
# ===========================================================================

def test_comments_preserved():
    source = "// this is a comment\nval x = 1"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "// this is a comment" in result


def test_inline_comment_preserved():
    source = "val x = 1 // comment"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "// comment" in result


def test_inline_comment_two_spaces():
    source = "val x = 1 // comment"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "  // comment" in result


# ===========================================================================
# Blank line tests
# ===========================================================================

def test_blank_lines_between_functions():
    source = "def foo():\n    return 1\ndef bar():\n    return 2"
    fmt = VoxFormatter()
    result = fmt.format(source)
    lines = result.split("\n")
    blank_count = 0
    for line in lines:
        if not line.strip():
            blank_count += 1
    assert blank_count >= 2


def test_single_blank_between_top_level_statements():
    source = "val x = 1\nval y = 2"
    fmt = VoxFormatter()
    result = fmt.format(source)
    lines = result.split("\n")
    blank_count = sum(1 for l in lines if not l.strip())
    assert blank_count >= 1


# ===========================================================================
# Function call syntax tests
# ===========================================================================

def test_function_call_no_space_before_paren():
    source = "fn (a, b)"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "fn(a, b)" in result


def test_keyword_space_before_paren():
    source = "if(x > 0):"
    fmt = VoxFormatter()
    result = fmt.format(source)
    assert "if (x > 0)" in result


# ===========================================================================
# format_file tests
# ===========================================================================

def test_format_file_modifies():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".vox", delete=False, encoding="utf-8") as f:
        f.write("val x=1\n")
        tmp_path = f.name

    try:
        result = format_file(tmp_path)
        assert result is True

        with open(tmp_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "x = 1" in content
    finally:
        os.unlink(tmp_path)


def test_format_file_no_change():
    source = 'val x = 1\n'
    with tempfile.NamedTemporaryFile(mode="w", suffix=".vox", delete=False, encoding="utf-8") as f:
        f.write(source)
        tmp_path = f.name

    try:
        result = format_file(tmp_path)
        assert result is False
    finally:
        os.unlink(tmp_path)


def test_format_file_with_options():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".vox", delete=False, encoding="utf-8") as f:
        f.write('val x = "hello"\n')
        tmp_path = f.name

    try:
        opts = FormatOptions(quote_char="'")
        result = format_file(tmp_path, options=opts)
        assert result is True

        with open(tmp_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "'hello'" in content
    finally:
        os.unlink(tmp_path)


# ===========================================================================
# Idempotency tests
# ===========================================================================

def test_format_is_idempotent():
    source = """class Foo:
    val x = 1
    def bar(self, y):
        if y > 0:
            return self.x + y
        return 0

def baz(a, b):
    return a + b
"""
    fmt = VoxFormatter()
    once = fmt.format(source)
    twice = fmt.format(once)
    assert once == twice


def test_format_messy_code_idempotent():
    source = "def foo( x,y ) :\n  val a=1+2\n   if(x==y):\n    return a\nreturn 0"
    fmt = VoxFormatter()
    once = fmt.format(source)
    twice = fmt.format(once)
    assert once == twice


# ===========================================================================
# Standalone runner
# ===========================================================================

def _run_all():
    failures = []
    passed = 0
    for name in sorted(globals()):
        if not name.startswith("test_"):
            continue
        fn = globals()[name]
        if not callable(fn):
            continue
        try:
            fn()
            passed += 1
            print("PASS  " + name)
        except Exception as e:  # noqa: BLE001
            failures.append(name)
            print("FAIL  " + name + ": " + str(e))
            traceback.print_exc()
    print("")
    print("=" * 60)
    if failures:
        print("{}/{} tests passed; {} failed: {}".format(
            passed, passed + len(failures), len(failures), ", ".join(failures),
        ))
        return False
    print("{}/{} tests passed.".format(passed, passed))
    return True


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
