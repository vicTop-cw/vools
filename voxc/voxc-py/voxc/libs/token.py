"""Vox language token type constants and Token / TokenStream classes.

This module is a self-contained replacement for the ``Token`` namedtuple
defined in :mod:`voxc.lexer`. It uses a regular class instead of a
namedtuple so that:

  * new fields can be added without breaking ``__init__`` callers that
    pass keyword arguments,
  * equality / hashing semantics can be customized independently of
    the field set,
  * JSON round-tripping (``to_dict`` / ``from_dict``) lives on the type
    itself, next to the data it operates on.

Public surface:
    TokenType      - constants for token type names
    Token          - a single token with position info
    TokenStream    - cursor over a list of Token
    OPERATORS      - frozenset of operator lexemes
    PUNCTUATIONS   - frozenset of single-char punctuation lexemes
"""

# ---------------------------------------------------------------------------
# Token type constants
# ---------------------------------------------------------------------------

class TokenType:
    """Symbolic constants for token types produced by the lexer.

    The values are short uppercase strings; they match the ``type`` field
    historically produced by :class:`voxc.lexer.VoxLexer` so that
    token-stream consumers (parsers, AST builders) can be migrated
    incrementally.
    """

    KEYWORD   = "KEYWORD"
    NAME      = "NAME"
    NUMBER    = "NUMBER"
    STRING    = "STRING"
    OPERATOR  = "OPERATOR"
    PUNCT     = "PUNCT"
    NEWLINE   = "NEWLINE"
    INDENT    = "INDENT"
    DEDENT    = "DEDENT"
    EOF       = "EOF"
    DOC       = "DOC"
    DICT_OPEN = "DICT_OPEN"


# ---------------------------------------------------------------------------
# Operator / punctuation lexeme sets
# ---------------------------------------------------------------------------
# These mirror the values hard-coded in voxc.lexer.VoxLexer. Keeping a
# second copy here is intentional: token.py is meant to be importable
# without dragging in the full lexer (which imports ``re`` etc.).

OPERATORS = frozenset({
    "==", "!=", "<=", ">=", "<", ">",
    "+", "-", "*", "/", "%", "**",
    "&&", "||", "!",
    "=", "+=", "-=", "*=", "/=", "%=",
    "::", ".", "?.", "??",
    "..", "..=",
    "->", "=>", "|",
    "@",
    "{:",  # dict opener, lexed as a single OPERATOR/DICT_OPEN token
})

PUNCTUATIONS = frozenset("{[]}():,;")


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

class Token:
    """A single token produced by the lexer.

    Attributes:
        type:  one of the :class:`TokenType` constants (or any string
               the lexer chooses to emit, e.g. a custom token type).
        value: the literal source text of the token; never ``None`` for
               real tokens (the EOF sentinel uses ``"<EOF>"``).
        line:  1-based line number where the token starts.
        col:   0-based column number where the token starts.
        file:  name of the source file the token came from, or ``None``
               if the source was an in-memory string.
    """

    __slots__ = ("type", "value", "line", "col", "file")

    def __init__(self, type_, value, line=0, col=0, file=None):
        self.type  = type_
        self.value = value
        self.line  = line
        self.col   = col
        self.file  = file

    # --- dunder protocol ---

    def __repr__(self):
        return "Token(type={!r}, value={!r}, line={}, col={}, file={!r})".format(
            self.type, self.value, self.line, self.col, self.file,
        )

    def __eq__(self, other):
        if not isinstance(other, Token):
            return NotImplemented
        return (
            self.type  == other.type
            and self.value == other.value
            and self.line  == other.line
            and self.col   == other.col
            and self.file  == other.file
        )

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self):
        return hash((self.type, self.value, self.line, self.col, self.file))

    # --- serialization ---

    def to_dict(self):
        """Serialize to a plain ``dict`` suitable for JSON encoding.

        The keys are stable: ``type``, ``value``, ``line``, ``col``,
        ``file``. ``file`` may be ``None`` (JSON null).
        """
        return {
            "type":  self.type,
            "value": self.value,
            "line":  self.line,
            "col":   self.col,
            "file":  self.file,
        }

    @staticmethod
    def from_dict(d):
        """Reconstruct a :class:`Token` from a dict produced by
        :meth:`to_dict`.

        Missing fields default to ``0`` for ``line``/``col`` and ``None``
        for ``file``, so a partial dict (e.g. just ``{"type", "value"}``)
        still produces a valid Token.
        """
        return Token(
            type_=d.get("type"),
            value=d.get("value"),
            line=d.get("line", 0),
            col=d.get("col", 0),
            file=d.get("file"),
        )


# ---------------------------------------------------------------------------
# TokenStream
# ---------------------------------------------------------------------------

class TokenStream:
    """Cursor over a list of :class:`Token` objects.

    A ``TokenStream`` is a thin wrapper that gives parser code a
    convenient ``peek``/``next``/``has_more``/``position`` interface
    without exposing the underlying list mutations.

    The stream is *not* immutable: :meth:`rewind` can move the cursor
    backwards, and :meth:`next` advances it forward. The underlying
    token list, however, is copied at construction time so external
    mutations to the caller's list do not affect the stream.
    """

    __slots__ = ("_tokens", "_pos")

    def __init__(self, tokens=None):
        # Defensive copy so callers can mutate their own list freely.
        self._tokens = list(tokens) if tokens is not None else []
        self._pos = 0

    # --- container protocol ---

    def __len__(self):
        return len(self._tokens)

    def __iter__(self):
        # Iteration walks the entire token list and does NOT move the
        # cursor. This makes ``for tok in stream`` safe to use for
        # inspection during debugging without disturbing parse state.
        return iter(self._tokens)

    def __getitem__(self, idx):
        return self._tokens[idx]

    # --- cursor state ---

    @property
    def position(self):
        """Current 0-based cursor position (number of consumed tokens)."""
        return self._pos

    def rewind(self, pos=0):
        """Reset the cursor to ``pos`` (default: 0 = start of stream).

        Raises :class:`IndexError` if ``pos`` is out of range. Use this
        for backtracking; typical parsers do not need it but it is
        cheap to provide.
        """
        if pos < 0 or pos > len(self._tokens):
            raise IndexError("position out of range: {}".format(pos))
        self._pos = pos

    def has_more(self):
        """Return True if at least one token remains unconsumed."""
        return self._pos < len(self._tokens)

    # --- inspection / consumption ---

    def peek(self, offset=0):
        """Return the token ``offset`` positions ahead, without consuming.

        ``offset=0`` (the default) returns the next token to be
        consumed. Returns ``None`` if the lookahead is past the end of
        the stream, or if ``offset`` is negative.
        """
        idx = self._pos + offset
        if idx < 0 or idx >= len(self._tokens):
            return None
        return self._tokens[idx]

    def next(self):
        """Consume and return the next token.

        Returns ``None`` if the cursor is already past the end of the
        stream.
        """
        if self._pos >= len(self._tokens):
            return None
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def expect(self, type_=None, value=None):
        """Consume the next token, optionally asserting its type/value.

        If ``type_`` is given, the next token's ``type`` must match;
        if ``value`` is given, its ``value`` must match. On mismatch or
        EOF, :class:`SyntaxError` is raised with a descriptive message.

        Returns the consumed token on success.
        """
        tok = self.next()
        if tok is None:
            raise SyntaxError("expected token but reached EOF")
        if type_ is not None and tok.type != type_:
            raise SyntaxError(
                "expected type {!r} but got {!r} ({!r} at line {} col {})".format(
                    type_, tok.type, tok.value, tok.line, tok.col,
                )
            )
        if value is not None and tok.value != value:
            raise SyntaxError(
                "expected value {!r} but got {!r} at line {} col {}".format(
                    value, tok.value, tok.line, tok.col,
                )
            )
        return tok
