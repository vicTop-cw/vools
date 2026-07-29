"""Vox language keyword definitions and categorization.

This module is the single source of truth for the set of reserved words
in the Vox language, organized by syntactic/semantic role. The existing
lexer (``voxc.lexer``) keeps its own ``KEYWORDS`` set for performance; the
categorization here is intended for higher-level tools (parsers, linters,
syntax highlighters, documentation generators).

Categories:
    DECLARATION    - introduces a new binding or type
    CONTROL_FLOW   - changes the flow of execution
    EXCEPTION      - exception handling
    CONCURRENCY    - async / parallel execution
    OPERATOR_DECL  - custom operator declarations
    META           - meta-programming facilities
    IMPORT         - module import / re-export
    TEST           - test framework declarations
    MODIFIER       - declaration modifiers
    LITERAL        - literal value keywords
    TYPE_REF       - keywords that reference a type
    OTHER          - misc contextual keywords
"""

# Keyword categories. Order of categories is stable (insertion order);
# order of keywords within a category follows the spec.
KEYWORD_CATEGORIES = {
    "DECLARATION": (
        "val", "var", "const", "def", "struct", "enum",
        "class", "trait", "impl", "extend", "template",
        "define", "lazy",
    ),
    "CONTROL_FLOW": (
        "if", "elif", "else", "while", "for", "in", "loop",
        "match", "when", "where", "break", "continue",
        "return", "defer", "guard",
    ),
    "EXCEPTION": (
        "try", "catch", "finally", "raise", "raises",
    ),
    "CONCURRENCY": (
        "async", "await", "go", "spawn", "yield",
    ),
    "OPERATOR_DECL": (
        "prefix", "infix", "suffix", "nthfix", "pairfix",
    ),
    "META": (
        "macro", "comptime", "transtime", "external",
        "include", "is",
    ),
    "IMPORT": (
        "import", "from", "as", "exclude",
    ),
    "TEST": (
        "test", "suite", "assert",
    ),
    "MODIFIER": (
        "pub", "override", "abstract", "static", "mut", "owned",
    ),
    "LITERAL": (
        "true", "false", "none", "let", "then",
    ),
    "TYPE_REF": (
        "Self", "super", "Type", "Enum", "Static",
        "untyped", "block",
    ),
    "OTHER": (
        "of", "omit", "ignore", "with",
    ),
}

# Flat set of all keywords, derived from the categories above so that
# the two can never drift out of sync. frozenset for O(1) membership
# tests and immutability.
ALL_KEYWORDS = frozenset(
    word
    for words in KEYWORD_CATEGORIES.values()
    for word in words
)

# Per-word -> category lookup table, also derived automatically.
_KEYWORD_TO_CATEGORY = {}
for _cat, _words in KEYWORD_CATEGORIES.items():
    for _w in _words:
        _KEYWORD_TO_CATEGORY[_w] = _cat
del _cat, _w, _words


def is_keyword(word):
    """Return True if ``word`` is a reserved Vox keyword.

    ``word`` must be a string; comparison is exact (Vox keywords are
    case-sensitive, e.g. ``Self`` is a keyword but ``self`` is not).
    """
    return word in ALL_KEYWORDS


def keyword_category(word):
    """Return the category name for ``word``.

    Returns ``None`` if ``word`` is not a keyword. The returned string
    matches one of the keys in :data:`KEYWORD_CATEGORIES`.
    """
    return _KEYWORD_TO_CATEGORY.get(word)


# --- convenience category predicates ---
# One predicate per category, to make call sites read naturally:
#   if is_declaration(kw): ...

def is_declaration(word):
    """True if ``word`` belongs to the DECLARATION category."""
    return keyword_category(word) == "DECLARATION"


def is_control_flow(word):
    """True if ``word`` belongs to the CONTROL_FLOW category."""
    return keyword_category(word) == "CONTROL_FLOW"


def is_exception(word):
    """True if ``word`` belongs to the EXCEPTION category."""
    return keyword_category(word) == "EXCEPTION"


def is_concurrency(word):
    """True if ``word`` belongs to the CONCURRENCY category."""
    return keyword_category(word) == "CONCURRENCY"


def is_operator_decl(word):
    """True if ``word`` belongs to the OPERATOR_DECL category."""
    return keyword_category(word) == "OPERATOR_DECL"


def is_meta(word):
    """True if ``word`` belongs to the META category."""
    return keyword_category(word) == "META"


def is_import(word):
    """True if ``word`` belongs to the IMPORT category."""
    return keyword_category(word) == "IMPORT"


def is_test(word):
    """True if ``word`` belongs to the TEST category."""
    return keyword_category(word) == "TEST"


def is_modifier(word):
    """True if ``word`` belongs to the MODIFIER category."""
    return keyword_category(word) == "MODIFIER"


def is_literal(word):
    """True if ``word`` belongs to the LITERAL category."""
    return keyword_category(word) == "LITERAL"


def is_type_ref(word):
    """True if ``word`` belongs to the TYPE_REF category."""
    return keyword_category(word) == "TYPE_REF"


def is_other(word):
    """True if ``word`` belongs to the OTHER category."""
    return keyword_category(word) == "OTHER"
