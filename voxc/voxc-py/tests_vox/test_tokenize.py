"""Tests for ``voxc.libs.tokenize.VoxLexer``.

Runnable both as a pytest module and as a standalone script::

    python -m pytest tests_vox/test_tokenize.py -v
    python tests_vox/test_tokenize.py
"""

import os
import sys
import traceback

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from voxc.libs.tokenize import VoxLexer  # noqa: E402
from voxc.libs.token import Token, TokenType  # noqa: E402


def _lex(source):
    """Helper: tokenize source and return token list."""
    lexer = VoxLexer()
    return lexer.tokenize(source)


def test_basic_tokens():
    """Test basic keyword, name, number, operator, punct tokens."""
    tokens = _lex("let x = 42")
    types = [t.type for t in tokens]
    values = [t.value for t in tokens]

    assert TokenType.KEYWORD in types
    assert TokenType.NAME in types
    assert TokenType.NUMBER in types
    assert TokenType.OPERATOR in types
    assert TokenType.EOF in types

    assert "let" in values
    assert "x" in values
    assert "42" in values
    assert "=" in values


def test_keywords_recognized():
    """Test that keywords from ALL_KEYWORDS are recognized."""
    from voxc.libs.keyword import ALL_KEYWORDS
    for kw in list(ALL_KEYWORDS)[:10]:
        tokens = _lex(kw)
        first = tokens[0]
        assert first.type == TokenType.KEYWORD, "expected KEYWORD for {!r}, got {!r}".format(kw, first.type)
        assert first.value == kw


def test_name_token():
    """Test NAME token for identifiers."""
    tokens = _lex("foo bar _baz x123")
    names = [t for t in tokens if t.type == TokenType.NAME]
    assert len(names) == 4
    assert names[0].value == "foo"
    assert names[1].value == "bar"
    assert names[2].value == "_baz"
    assert names[3].value == "x123"


def test_number_tokens():
    """Test NUMBER tokens for integers and floats."""
    tokens = _lex("1 2.5 0.3 100")
    numbers = [t for t in tokens if t.type == TokenType.NUMBER]
    assert len(numbers) == 4
    assert numbers[0].value == "1"
    assert numbers[1].value == "2.5"
    assert numbers[2].value == "0.3"
    assert numbers[3].value == "100"


def test_string_single_quote():
    """Test single-quoted strings."""
    tokens = _lex("'hello'")
    strings = [t for t in tokens if t.type == TokenType.STRING]
    assert len(strings) == 1
    assert strings[0].value == "'hello'"


def test_string_double_quote():
    """Test double-quoted strings."""
    tokens = _lex('"world"')
    strings = [t for t in tokens if t.type == TokenType.STRING]
    assert len(strings) == 1
    assert strings[0].value == '"world"'


def test_string_with_escape():
    """Test strings with escape sequences."""
    tokens = _lex(r'"hello\nworld"')
    strings = [t for t in tokens if t.type == TokenType.STRING]
    assert len(strings) == 1


def test_raw_string():
    """Test raw strings r'...' and r"..."."""
    tokens = _lex('r"raw\\string"')
    strings = [t for t in tokens if t.type == TokenType.STRING]
    assert len(strings) == 1

    tokens2 = _lex("r'raw\\string'")
    strings2 = [t for t in tokens2 if t.type == TokenType.STRING]
    assert len(strings2) == 1


def test_multiline_string_double():
    """Test triple-double-quoted multi-line strings."""
    source = 'x = """line1\nline2\nline3"""'
    tokens = _lex(source)
    strings = [t for t in tokens if t.type == TokenType.STRING]
    assert len(strings) == 1
    assert "line1" in strings[0].value
    assert "line2" in strings[0].value
    assert "line3" in strings[0].value


def test_multiline_string_single():
    """Test triple-single-quoted multi-line strings."""
    source = "x = '''line1\nline2\nline3'''"
    tokens = _lex(source)
    strings = [t for t in tokens if t.type == TokenType.STRING]
    assert len(strings) == 1


def test_operators():
    """Test various operators."""
    tokens = _lex("+ - * / == != <= >= = += -= *=")
    ops = [t for t in tokens if t.type == TokenType.OPERATOR]
    assert len(ops) >= 5


def test_punctuation():
    """Test punctuation tokens."""
    tokens = _lex("{ } [ ] ( ) : , ;")
    puncts = [t for t in tokens if t.type == TokenType.PUNCT]
    assert len(puncts) == 9


def test_dict_open():
    """Test DICT_OPEN token {:."""
    tokens = _lex("{:")
    dict_opens = [t for t in tokens if t.type == TokenType.DICT_OPEN]
    assert len(dict_opens) == 1
    assert dict_opens[0].value == "{:"


def test_line_comment():
    """Test // line comments are skipped."""
    tokens = _lex("x = 1 // comment")
    names = [t for t in tokens if t.type == TokenType.NAME]
    assert len(names) == 1
    assert names[0].value == "x"


def test_block_comment():
    """Test /* */ block comments are skipped."""
    tokens = _lex("x /* comment */ y")
    names = [t for t in tokens if t.type == TokenType.NAME]
    assert len(names) == 2
    assert names[0].value == "x"
    assert names[1].value == "y"


def test_doc_comment():
    """Test /// doc comments produce DOC token."""
    tokens = _lex("/// This is a doc comment")
    docs = [t for t in tokens if t.type == TokenType.DOC]
    assert len(docs) == 1
    assert docs[0].value == "This is a doc comment"


def test_doc_comment_not_regular_comment():
    """Test that //// is treated as regular comment, not DOC."""
    tokens = _lex("//// not a doc comment")
    docs = [t for t in tokens if t.type == TokenType.DOC]
    assert len(docs) == 0


def test_indent_dedent():
    """Test INDENT and DEDENT tokens."""
    source = "if true:\n    x = 1\n    y = 2\nz = 3"
    tokens = _lex(source)
    types = [t.type for t in tokens]

    assert TokenType.INDENT in types
    assert TokenType.DEDENT in types

    indent_idx = types.index(TokenType.INDENT)
    dedent_idx = types.index(TokenType.DEDENT)
    assert indent_idx < dedent_idx


def test_newline_tokens():
    """Test NEWLINE tokens between statements."""
    source = "x = 1\ny = 2"
    tokens = _lex(source)
    newlines = [t for t in tokens if t.type == TokenType.NEWLINE]
    assert len(newlines) >= 1


def test_eof_token():
    """Test that EOF token is always last."""
    tokens = _lex("x = 1")
    assert tokens[-1].type == TokenType.EOF
    assert tokens[-1].value == "<EOF>"


def test_position_info():
    """Test line (1-based) and col (0-based) position info."""
    tokens = _lex("let x = 42")
    first = tokens[0]
    assert first.line == 1
    assert first.col == 0

    last_real = [t for t in tokens if t.type not in (TokenType.NEWLINE, TokenType.EOF)][-1]
    assert last_real.line == 1


def test_multiple_lines_position():
    """Test position info across multiple lines."""
    source = "x = 1\ny = 2"
    tokens = _lex(source)
    names = [t for t in tokens if t.type == TokenType.NAME]
    assert names[0].line == 1
    assert names[1].line == 2


def test_empty_lines_skipped():
    """Test that empty lines are skipped."""
    source = "x = 1\n\n\ny = 2"
    tokens = _lex(source)
    names = [t for t in tokens if t.type == TokenType.NAME]
    assert len(names) == 2


def test_token_is_token_class():
    """Test that returned tokens are Token class instances (not namedtuple)."""
    tokens = _lex("x = 1")
    for t in tokens:
        assert isinstance(t, Token), "expected Token instance, got {!r}".format(type(t))


def test_interface_compatibility_with_old_lexer():
    """Test basic interface compatibility: tokenize() returns list with type/value/line/col."""
    tokens = _lex("let foo = 42")
    assert isinstance(tokens, list)
    assert len(tokens) > 0
    t = tokens[0]
    assert hasattr(t, "type")
    assert hasattr(t, "value")
    assert hasattr(t, "line")
    assert hasattr(t, "col")


def test_arrow_operator():
    """Test -> operator."""
    tokens = _lex("x -> y")
    ops = [t for t in tokens if t.type == TokenType.OPERATOR and t.value == "->"]
    assert len(ops) == 1


def test_fat_arrow_operator():
    """Test => operator."""
    tokens = _lex("x => y")
    ops = [t for t in tokens if t.type == TokenType.OPERATOR and t.value == "=>"]
    assert len(ops) == 1


def test_double_colon():
    """Test :: operator."""
    tokens = _lex("x::y")
    ops = [t for t in tokens if t.type == TokenType.OPERATOR and t.value == "::"]
    assert len(ops) == 1


def test_range_operator():
    """Test .. operator."""
    tokens = _lex("1..10")
    ops = [t for t in tokens if t.type == TokenType.OPERATOR and t.value == ".."]
    assert len(ops) == 1


def test_question_dot():
    """Test ?. operator."""
    tokens = _lex("x?.y")
    ops = [t for t in tokens if t.type == TokenType.OPERATOR and t.value == "?."]
    assert len(ops) == 1


def test_nullish_coalescing():
    """Test ?? operator."""
    tokens = _lex("x ?? y")
    ops = [t for t in tokens if t.type == TokenType.OPERATOR and t.value == "??"]
    assert len(ops) == 1


def test_power_operator():
    """Test ** operator."""
    tokens = _lex("x ** y")
    ops = [t for t in tokens if t.type == TokenType.OPERATOR and t.value == "**"]
    assert len(ops) == 1


def test_logical_operators():
    """Test && and || operators."""
    tokens = _lex("x && y || z")
    and_ops = [t for t in tokens if t.type == TokenType.OPERATOR and t.value == "&&"]
    or_ops = [t for t in tokens if t.type == TokenType.OPERATOR and t.value == "||"]
    assert len(and_ops) == 1
    assert len(or_ops) == 1


def test_at_operator():
    """Test @ operator."""
    tokens = _lex("@decorator")
    ops = [t for t in tokens if t.type == TokenType.OPERATOR and t.value == "@"]
    assert len(ops) == 1


def test_pipe_operator():
    """Test | operator."""
    tokens = _lex("x | y")
    ops = [t for t in tokens if t.type == TokenType.OPERATOR and t.value == "|"]
    assert len(ops) == 1


def test_multiline_string_followed_by_code():
    """Test code after a multi-line string on the same line."""
    source = 'x = """hello"""\ny = 1'
    tokens = _lex(source)
    names = [t for t in tokens if t.type == TokenType.NAME]
    assert len(names) >= 2


def _run_all():
    """Run every ``test_*`` function in this module; print a report.

    Returns True if all pass, False otherwise.
    """
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
