"""Tests for ``voxc.libs.keyword`` and ``voxc.libs.token``.

Runnable both as a pytest module and as a standalone script::

    python -m pytest tests_vox/test_keyword_token.py -v
    python tests_vox/test_keyword_token.py
"""

import os
import sys
import traceback

# Make the project importable when run as a plain script from anywhere
# (pytest picks the package up via rootdir, but the standalone path
# does not). Insert at the front so we shadow any stale install.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from voxc.libs.keyword import (  # noqa: E402
    KEYWORD_CATEGORIES,
    ALL_KEYWORDS,
    is_keyword,
    keyword_category,
    is_declaration,
    is_control_flow,
    is_exception,
    is_concurrency,
    is_operator_decl,
    is_meta,
    is_import,
    is_test,
    is_modifier,
    is_literal,
    is_type_ref,
    is_other,
)
from voxc.libs.token import (  # noqa: E402
    TokenType,
    Token,
    TokenStream,
    OPERATORS,
    PUNCTUATIONS,
)


# ===========================================================================
# keyword.py tests
# ===========================================================================

def test_all_keywords_recognized():
    for word in ALL_KEYWORDS:
        assert is_keyword(word), "keyword not recognized: " + repr(word)


def test_non_keyword_rejected():
    for word in ("foo", "bar", "x", "_priv", "Function", "", "VAL", "If", "self"):
        assert not is_keyword(word), "false positive: " + repr(word)


def test_keyword_category_returns_correct_category():
    cases = {
        # DECLARATION
        "val": "DECLARATION",
        "def": "DECLARATION",
        "trait": "DECLARATION",
        "lazy": "DECLARATION",
        # CONTROL_FLOW
        "if": "CONTROL_FLOW",
        "return": "CONTROL_FLOW",
        "guard": "CONTROL_FLOW",
        "where": "CONTROL_FLOW",
        # EXCEPTION
        "try": "EXCEPTION",
        "raise": "EXCEPTION",
        "raises": "EXCEPTION",
        # CONCURRENCY
        "async": "CONCURRENCY",
        "spawn": "CONCURRENCY",
        "yield": "CONCURRENCY",
        # OPERATOR_DECL
        "infix": "OPERATOR_DECL",
        "pairfix": "OPERATOR_DECL",
        # META
        "macro": "META",
        "comptime": "META",
        "is": "META",
        # IMPORT
        "import": "IMPORT",
        "from": "IMPORT",
        "as": "IMPORT",
        # TEST
        "test": "TEST",
        "suite": "TEST",
        "assert": "TEST",
        # MODIFIER
        "pub": "MODIFIER",
        "static": "MODIFIER",
        "owned": "MODIFIER",
        # LITERAL
        "true": "LITERAL",
        "false": "LITERAL",
        "none": "LITERAL",
        "let": "LITERAL",
        "then": "LITERAL",
        # TYPE_REF
        "Self": "TYPE_REF",
        "super": "TYPE_REF",
        "Type": "TYPE_REF",
        "Enum": "TYPE_REF",
        "Static": "TYPE_REF",
        "untyped": "TYPE_REF",
        "block": "TYPE_REF",
        # OTHER
        "of": "OTHER",
        "omit": "OTHER",
        "ignore": "OTHER",
        "with": "OTHER",
    }
    for word, expected in cases.items():
        actual = keyword_category(word)
        assert actual == expected, (
            "category for {!r}: expected {!r}, got {!r}".format(
                word, expected, actual,
            )
        )


def test_keyword_category_none_for_non_keyword():
    assert keyword_category("not_a_keyword") is None
    assert keyword_category("") is None
    # case-sensitivity: 'self' is not the same as 'Self'
    assert keyword_category("self") is None
    assert keyword_category("IF") is None


def test_category_helpers_match_category():
    assert is_declaration("val")
    assert is_declaration("struct")
    assert not is_declaration("if")

    assert is_control_flow("while")
    assert is_control_flow("defer")
    assert not is_control_flow("try")

    assert is_exception("catch")
    assert not is_exception("async")

    assert is_concurrency("await")
    assert not is_concurrency("val")

    assert is_operator_decl("prefix")
    assert not is_operator_decl("macro")

    assert is_meta("comptime")
    assert is_meta("external")
    assert not is_meta("import")

    assert is_import("from")
    assert not is_import("test")

    assert is_test("suite")
    assert not is_test("pub")

    assert is_modifier("static")
    assert is_modifier("abstract")
    assert not is_modifier("val")

    assert is_literal("none")
    assert not is_literal("Self")

    assert is_type_ref("super")
    assert not is_type_ref("true")

    assert is_other("omit")
    assert not is_other("val")


def test_categories_are_disjoint():
    # Each keyword appears in at most one category.
    seen = {}
    for cat, words in KEYWORD_CATEGORIES.items():
        for w in words:
            assert w not in seen, (
                "keyword {!r} appears in both {!r} and {!r}".format(
                    w, seen.get(w), cat,
                )
            )
            seen[w] = cat


def test_all_keywords_union_matches_categories():
    expected = set()
    for words in KEYWORD_CATEGORIES.values():
        expected.update(words)
    assert set(ALL_KEYWORDS) == expected


def test_all_keywords_is_frozenset():
    # frozenset guarantees O(1) membership and immutability; verify we
    # actually got one (not a plain set, not a list).
    assert isinstance(ALL_KEYWORDS, frozenset)


def test_expected_keyword_count():
    # Lock the total in: if a keyword is added or removed without
    # updating the categories this trips immediately.
    expected_per_category = {
        "DECLARATION": 13,
        "CONTROL_FLOW": 15,
        "EXCEPTION": 5,
        "CONCURRENCY": 5,
        "OPERATOR_DECL": 5,
        "META": 6,
        "IMPORT": 4,
        "TEST": 3,
        "MODIFIER": 6,
        "LITERAL": 5,
        "TYPE_REF": 7,
        "OTHER": 4,
    }
    for cat, n in expected_per_category.items():
        actual = len(KEYWORD_CATEGORIES[cat])
        assert actual == n, (
            "category {!r}: expected {} keywords, got {}".format(cat, n, actual)
        )
    assert len(ALL_KEYWORDS) == sum(expected_per_category.values())


# ===========================================================================
# token.py tests
# ===========================================================================

def test_tokentype_constants_distinct_and_named():
    types = [
        TokenType.KEYWORD, TokenType.NAME, TokenType.NUMBER,
        TokenType.STRING, TokenType.OPERATOR, TokenType.PUNCT,
        TokenType.NEWLINE, TokenType.INDENT, TokenType.DEDENT,
        TokenType.EOF, TokenType.DOC, TokenType.DICT_OPEN,
    ]
    # all distinct
    assert len(set(types)) == len(types), "token type constants collide"
    # all are plain strings (so they JSON-serialize naturally)
    for t in types:
        assert isinstance(t, str)
    # spot-check a couple of values
    assert TokenType.KEYWORD == "KEYWORD"
    assert TokenType.DICT_OPEN == "DICT_OPEN"
    assert TokenType.EOF == "EOF"


def test_token_creation_and_attrs():
    t = Token(TokenType.NAME, "foo", line=12, col=3, file="a.vox")
    assert t.type  == TokenType.NAME
    assert t.value == "foo"
    assert t.line  == 12
    assert t.col   == 3
    assert t.file  == "a.vox"


def test_token_defaults():
    t = Token(TokenType.NUMBER, "42")
    assert t.type  == TokenType.NUMBER
    assert t.value == "42"
    assert t.line  == 0
    assert t.col   == 0
    assert t.file  is None


def test_token_repr_contains_essentials():
    t = Token(TokenType.STRING, '"hi"', line=1, col=2, file="b.vox")
    r = repr(t)
    assert "Token(" in r
    assert "STRING" in r
    assert '"hi"' in r
    assert "line=1" in r
    assert "col=2" in r
    assert "b.vox" in r


def test_token_repr_with_none_file():
    t = Token(TokenType.EOF, "<EOF>")
    r = repr(t)
    assert "EOF" in r
    assert "None" in r  # file defaults to None


def test_token_to_dict_shape():
    t = Token(TokenType.OPERATOR, "->", line=5, col=10, file="c.vox")
    d = t.to_dict()
    assert d == {
        "type": "OPERATOR",
        "value": "->",
        "line": 5,
        "col": 10,
        "file": "c.vox",
    }
    # JSON-serializable (no custom objects)
    import json
    json.dumps(d)  # raises if not serializable


def test_token_from_dict_full():
    d = {"type": "NAME", "value": "x", "line": 3, "col": 4, "file": "f.vox"}
    t = Token.from_dict(d)
    assert t.type  == "NAME"
    assert t.value == "x"
    assert t.line  == 3
    assert t.col   == 4
    assert t.file  == "f.vox"


def test_token_from_dict_partial_uses_defaults():
    d = {"type": "NUMBER", "value": "1"}
    t = Token.from_dict(d)
    assert t.type  == "NUMBER"
    assert t.value == "1"
    assert t.line  == 0
    assert t.col   == 0
    assert t.file  is None


def test_token_to_dict_from_dict_roundtrip():
    original = Token(
        TokenType.PUNCT, ",", line=42, col=17, file="round.vox",
    )
    restored = Token.from_dict(original.to_dict())
    assert restored == original
    assert restored is not original  # different instance
    assert hash(restored) == hash(original)


def test_token_equality_and_hash():
    a = Token(TokenType.NAME, "x", 1, 2, "f")
    b = Token(TokenType.NAME, "x", 1, 2, "f")
    c = Token(TokenType.NAME, "x", 1, 2, "g")  # different file
    d = Token(TokenType.NAME, "x", 9, 2, "f")  # different line

    assert a == b
    assert not (a != b)
    assert a != c
    assert a != d
    # Token vs non-Token: NotImplemented falls back to identity
    assert a != "not a token"
    assert not (a == "not a token")

    assert hash(a) == hash(b)
    # usable as dict key / set member
    s = {a, b, c}
    assert len(s) == 2  # a and b are equal


def test_token_uses_slots():
    # __slots__ prevents arbitrary attribute assignment; this both
    # documents and locks in that behaviour.
    t = Token(TokenType.NAME, "x")
    assert not hasattr(t, "__dict__")
    try:
        t.extra = 1
        raise AssertionError("expected AttributeError from __slots__")
    except AttributeError:
        pass


# ---------------------------------------------------------------------------
# TokenStream
# ---------------------------------------------------------------------------

def _make_stream():
    """A small 4-token stream used by most stream tests."""
    return TokenStream([
        Token(TokenType.NUMBER,  "1",     1, 0),
        Token(TokenType.OPERATOR, "+",    1, 1),
        Token(TokenType.NUMBER,  "2",    1, 2),
        Token(TokenType.EOF,     "<EOF>", 1, 3),
    ])


def test_tokenstream_initial_state():
    s = _make_stream()
    assert len(s) == 4
    assert s.position == 0
    assert s.has_more() is True


def test_tokenstream_peek_does_not_advance():
    s = _make_stream()
    t = s.peek()
    assert t is not None
    assert t.value == "1"
    assert s.position == 0
    # lookahead
    assert s.peek(1).value == "+"
    assert s.peek(2).value == "2"
    assert s.peek(3).value == "<EOF>"
    # out-of-range -> None
    assert s.peek(4) is None
    assert s.peek(-1) is None
    # cursor still untouched
    assert s.position == 0


def test_tokenstream_next_advances():
    s = _make_stream()
    a = s.next()
    b = s.next()
    assert a.value == "1"
    assert b.value == "+"
    assert s.position == 2
    assert s.has_more() is True


def test_tokenstream_next_at_eof_returns_none():
    s = _make_stream()
    for _ in range(4):
        tok = s.next()
        assert tok is not None
    assert s.has_more() is False
    assert s.position == 4
    assert s.next() is None
    # cursor stays past-end on repeated reads
    assert s.next() is None
    assert s.position == 4


def test_tokenstream_peek_at_eof_returns_none():
    s = _make_stream()
    for _ in range(4):
        s.next()
    assert s.peek() is None
    assert s.peek(0) is None


def test_tokenstream_rewind_to_zero():
    s = _make_stream()
    s.next()
    s.next()
    assert s.position == 2
    s.rewind()
    assert s.position == 0
    assert s.peek().value == "1"


def test_tokenstream_rewind_to_specific_pos():
    s = _make_stream()
    s.next(); s.next(); s.next()
    assert s.position == 3
    s.rewind(1)
    assert s.position == 1
    assert s.peek().value == "+"


def test_tokenstream_rewind_rejects_bad_pos():
    s = _make_stream()
    try:
        s.rewind(-1)
        raise AssertionError("expected IndexError for negative pos")
    except IndexError:
        pass
    try:
        s.rewind(len(s) + 1)
        raise AssertionError("expected IndexError for pos > len")
    except IndexError:
        pass
    # rewind to exactly len() is allowed (cursor at EOF)
    s.rewind(len(s))
    assert s.position == len(s)
    assert s.has_more() is False


def test_tokenstream_getitem():
    s = _make_stream()
    assert s[0].value == "1"
    assert s[-1].value == "<EOF>"
    try:
        _ = s[99]
        raise AssertionError("expected IndexError")
    except IndexError:
        pass


def test_tokenstream_iter_does_not_move_cursor():
    s = _make_stream()
    values = [t.value for t in s]
    assert values == ["1", "+", "2", "<EOF>"]
    # iterating must not consume tokens
    assert s.position == 0
    assert s.has_more() is True


def test_tokenstream_empty():
    s = TokenStream()
    assert len(s) == 0
    assert s.has_more() is False
    assert s.peek() is None
    assert s.next() is None
    assert s.position == 0
    # rewind to 0 is the only valid position
    s.rewind(0)


def test_tokenstream_copies_input_list():
    # Mutating the source list after construction must not affect the
    # stream: the contract is that TokenStream owns its own copy.
    source = [Token(TokenType.NAME, "x")]
    s = TokenStream(source)
    source.append(Token(TokenType.NAME, "y"))
    assert len(s) == 1
    assert s.peek().value == "x"


def test_tokenstream_default_arg_is_empty():
    # Calling TokenStream() with no args must not share state across
    # instances (a classic mutable-default-arg bug).
    a = TokenStream()
    b = TokenStream()
    a.next()  # no-op on empty stream, but touches cursor
    assert b.position == 0


def test_tokenstream_expect_happy_path():
    s = _make_stream()
    t = s.expect(type_=TokenType.NUMBER, value="1")
    assert t.type == TokenType.NUMBER
    assert t.value == "1"
    assert s.position == 1


def test_tokenstream_expect_wrong_type():
    s = _make_stream()
    try:
        s.expect(type_=TokenType.STRING)
        raise AssertionError("expected SyntaxError")
    except SyntaxError:
        pass
    # cursor must still advance past the offending token (next() ran)
    assert s.position == 1


def test_tokenstream_expect_wrong_value():
    s = _make_stream()
    try:
        s.expect(type_=TokenType.NUMBER, value="42")
        raise AssertionError("expected SyntaxError")
    except SyntaxError:
        pass


def test_tokenstream_expect_at_eof():
    s = TokenStream()
    try:
        s.expect()
        raise AssertionError("expected SyntaxError on EOF")
    except SyntaxError:
        pass


# ---------------------------------------------------------------------------
# OPERATORS / PUNCTUATIONS constants
# ---------------------------------------------------------------------------

def test_operators_contains_expected_lexemes():
    # Spot-check a representative sample
    for op in ("->", "=>", "==", "!=", "<=", ">=", "&&", "||",
               "+", "-", "*", "/", "%", "**", "=", "::", "..",
               "?.", "??", "@", "{:"):
        assert op in OPERATORS, "missing operator: " + repr(op)


def test_operators_excludes_bare_punct():
    # Punctuation chars that the lexer tokenizes as PUNCT (not OPERATOR)
    # must NOT appear in OPERATORS, otherwise token classification would
    # be ambiguous.
    for p in ("{", "}", "[", "]", "(", ")", ":", ",", ";"):
        assert p not in OPERATORS, "punct leaked into OPERATORS: " + repr(p)


def test_punctuations_contains_expected_chars():
    for p in ("{", "}", "[", "]", "(", ")", ":", ",", ";"):
        assert p in PUNCTUATIONS, "missing punct: " + repr(p)


def test_operators_and_punctuations_are_frozensets():
    assert isinstance(OPERATORS, frozenset)
    assert isinstance(PUNCTUATIONS, frozenset)


# ===========================================================================
# Standalone runner (fallback when pytest is unavailable)
# ===========================================================================

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
        except Exception as e:  # noqa: BLE001 - we want all errors
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
