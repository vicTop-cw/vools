"""Vox code formatter / pretty-printer.

Formats Vox source code according to consistent style rules.

Public surface:
    FormatOptions  - configuration for formatting style
    VoxFormatter   - main formatter class with format(source) method
    format_file    - convenience function to format a file in-place
"""

import os
import re


# ---------------------------------------------------------------------------
# FormatOptions
# ---------------------------------------------------------------------------

class FormatOptions(object):
    """Configuration options for the Vox code formatter.

    Attributes:
        indent_size:      Number of spaces per indentation level (default 4).
        quote_char:       Preferred quote character for strings: '"' or "'"
                          (default '"').
        max_line_length:  Target maximum line length in characters (default 88).
                          Used as a hint for line wrapping decisions.
        strip_trailing:   Whether to strip trailing whitespace from lines
                          (default True).
        end_with_newline: Whether to ensure the file ends with a newline
                          (default True).
    """

    def __init__(self, indent_size=4, quote_char='"', max_line_length=88,
                 strip_trailing=True, end_with_newline=True):
        if indent_size < 0:
            raise ValueError("indent_size must be non-negative")
        if quote_char not in ('"', "'"):
            raise ValueError("quote_char must be '\"' or \"'\"")
        if max_line_length < 1:
            raise ValueError("max_line_length must be at least 1")

        self.indent_size = indent_size
        self.quote_char = quote_char
        self.max_line_length = max_line_length
        self.strip_trailing = strip_trailing
        self.end_with_newline = end_with_newline

    def __repr__(self):
        return (
            "FormatOptions(indent_size={!r}, quote_char={!r}, "
            "max_line_length={!r}, strip_trailing={!r}, "
            "end_with_newline={!r})"
        ).format(
            self.indent_size, self.quote_char, self.max_line_length,
            self.strip_trailing, self.end_with_newline,
        )


# ---------------------------------------------------------------------------
# Token types (minimal, for line-level formatting)
# ---------------------------------------------------------------------------

# These are used by the line-level tokenizer inside VoxFormatter. We keep a
# separate tiny tokenizer here so that tabnny.py can be used without pulling
# in the full voxc.lexer dependency.

_LINE_TOKEN_STRING = "STRING"
_LINE_TOKEN_COMMENT = "COMMENT"
_LINE_TOKEN_OPERATOR = "OPERATOR"
_LINE_TOKEN_PUNCT = "PUNCT"
_LINE_TOKEN_WORD = "WORD"
_LINE_TOKEN_NUMBER = "NUMBER"
_LINE_TOKEN_WHITESPACE = "WHITESPACE"


# ---------------------------------------------------------------------------
# VoxFormatter
# ---------------------------------------------------------------------------

class VoxFormatter(object):
    """Vox source code formatter.

    Usage::

        fmt = VoxFormatter()
        result = fmt.format(source_code)
    """

    # Keywords that start a new block (increase indentation on next line)
    _BLOCK_KEYWORDS = frozenset({
        "if", "elif", "else", "while", "for", "match", "case",
        "def", "class", "struct", "trait", "impl", "enum",
        "try", "catch", "finally",
        "with", "when", "where",
        "block", "suite", "test",
        "macro", "template",
        "loop",
    })

    # Keywords that are declaration-like (trigger double blank lines above
    # at the top level)
    _DECL_KEYWORDS = frozenset({
        "def", "class", "struct", "trait", "impl", "enum",
        "macro", "template", "test", "suite",
    })

    # Operators that should have spaces on both sides
    _SPACED_OPERATORS = frozenset({
        "==", "!=", "<=", ">=", "<", ">",
        "+", "-", "*", "/", "%", "**",
        "&&", "||",
        "=", "+=", "-=", "*=", "/=", "%=",
        "->", "=>", "|",
        "..", "..=", "??", "?.",
    })

    # Operators that should NOT have surrounding spaces (unary, member access)
    _UNSPACED_OPERATORS = frozenset({
        "!", "::", ".", "@",
    })

    def __init__(self, options=None):
        self.options = options if options is not None else FormatOptions()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format(self, source):
        """Format Vox source code and return the formatted string.

        Args:
            source: A string containing Vox source code.

        Returns:
            A string containing the formatted source code.
        """
        lines = source.split("\n")
        formatted_lines = self._format_lines(lines)
        result = "\n".join(formatted_lines)

        if self.options.end_with_newline and result and not result.endswith("\n"):
            result += "\n"
        elif not self.options.end_with_newline and result.endswith("\n"):
            result = result.rstrip("\n")

        return result

    # ------------------------------------------------------------------
    # Core formatting pipeline
    # ------------------------------------------------------------------

    def _format_lines(self, lines):
        """Format a list of source lines, returning a list of lines."""
        normalized = []
        for line in lines:
            if self.options.strip_trailing:
                line = line.rstrip()
            normalized.append(line)

        processed = self._process_blank_lines(normalized)
        indented = self._fix_indentation(processed)
        adjusted = self._adjust_blank_lines(indented)
        formatted = [self._format_line_content(line) for line in adjusted]

        return formatted

    def _process_blank_lines(self, lines):
        """Normalize blank lines: collapse multiple blank lines into one,
        remove leading blank lines.

        Detailed blank line rules (top-level declarations get 2 blank lines,
        etc.) are applied later in _adjust_blank_lines, after indentation
        has been fixed.
        """
        result = []
        prev_was_blank = True

        for line in lines:
            stripped = line.strip()

            if not stripped:
                if not prev_was_blank:
                    result.append("")
                prev_was_blank = True
                continue

            result.append(line)
            prev_was_blank = False

        while result and not result[0].strip():
            result.pop(0)

        while result and not result[-1].strip():
            result.pop()

        return result

    def _adjust_blank_lines(self, lines):
        """Adjust blank lines according to style rules.

        - Two blank lines before top-level function/class definitions.
        - One blank line between other top-level statements.
        - No extra blank lines inside blocks (preserve single blank lines).
        """
        result = []
        indent_size = self.options.indent_size

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                result.append("")
                i += 1
                continue

            current_indent = self._count_indent(line)
            is_top_level = current_indent == 0
            is_decl = self._is_declaration(stripped)
            is_comment = self._is_comment_or_doc(stripped)

            if is_top_level and result and not is_comment:
                prev_non_blank = len(result) - 1
                while prev_non_blank >= 0 and not result[prev_non_blank].strip():
                    prev_non_blank -= 1

                if prev_non_blank >= 0:
                    prev_line = result[prev_non_blank].strip()
                    prev_is_decl = self._is_declaration(prev_line)
                    prev_is_comment = self._is_comment_or_doc(prev_line)

                    if is_decl or prev_is_decl:
                        blanks_needed = 2
                    else:
                        blanks_needed = 1

                    blanks_existing = len(result) - prev_non_blank - 1
                    blanks_to_add = blanks_needed - blanks_existing
                    for _ in range(blanks_to_add):
                        result.append("")

            result.append(line)
            i += 1

        return result

    @staticmethod
    def _ensure_blank_lines(result, count):
        """Ensure at least ``count`` blank lines at the end of result."""
        blank_count = 0
        idx = len(result) - 1
        while idx >= 0 and not result[idx].strip():
            blank_count += 1
            idx -= 1

        needed = count - blank_count
        for _ in range(needed):
            result.append("")

    @staticmethod
    def _count_indent(line):
        """Count leading spaces (not tabs)."""
        count = 0
        for ch in line:
            if ch == " ":
                count += 1
            else:
                break
        return count

    def _is_comment_or_doc(self, stripped):
        """Check if a stripped line is a comment or doc comment."""
        return stripped.startswith("//")

    def _is_declaration(self, stripped):
        """Check if a line starts a declaration (def, class, etc.)."""
        for kw in self._DECL_KEYWORDS:
            if stripped.startswith(kw + " ") or stripped == kw or stripped.startswith(kw + "\t"):
                return True
        return False

    def _starts_block(self, stripped):
        """Check if a line starts a new indentation block."""
        for kw in self._BLOCK_KEYWORDS:
            if stripped.startswith(kw + " ") or stripped.startswith(kw + "(") or stripped.startswith(kw + ":"):
                return True
        if stripped.endswith(":"):
            return True
        if "=>" in stripped:
            return True
        return False

    def _fix_indentation(self, lines):
        """Fix indentation to use consistent indent_size spaces per level.

        Uses a hybrid approach: trust block-start keywords to increase
        indentation, and use original indentation as a hint for when to
        decrease indentation.

        When original code has no indentation at all (all lines start at
        column 0), we conservatively keep indent_level based on block
        structure rather than dedenting aggressively.
        """
        result = []
        indent_level = 0
        indent_size = self.options.indent_size

        has_any_indentation = False
        for line in lines:
            if self._count_indent(line) > 0:
                has_any_indentation = True
                break

        for line in lines:
            stripped = line.strip()

            if not stripped:
                result.append("")
                continue

            if self._is_comment_or_doc(stripped):
                result.append(" " * (indent_level * indent_size) + stripped)
                continue

            current_indent = self._count_indent(line)

            if self._line_causes_dedent(stripped):
                indent_level = max(0, indent_level - 1)

            elif has_any_indentation and indent_level > 0:
                expected_indent = indent_level * indent_size
                if current_indent < expected_indent - indent_size // 2:
                    if indent_size > 0:
                        diff = expected_indent - current_indent
                        levels = max(1, (diff + indent_size - 1) // indent_size)
                        indent_level = max(0, indent_level - levels)
                    else:
                        indent_level = 0

            proper_indent = " " * (indent_level * indent_size)
            result.append(proper_indent + stripped)

            if self._starts_block(stripped):
                indent_level += 1

        return result

    def _line_causes_dedent(self, stripped):
        """Check if this line keyword ends a block (dedent before it)."""
        dedent_keywords = ("elif", "else", "catch", "finally", "case")
        for kw in dedent_keywords:
            if stripped.startswith(kw + " ") or stripped == kw or stripped.startswith(kw + ":"):
                return True
        return False

    # ------------------------------------------------------------------
    # Line content formatting
    # ------------------------------------------------------------------

    def _format_line_content(self, line):
        """Format the content of a single line (spacing around operators,
        commas, colons, etc.)."""
        if not line.strip():
            return ""

        leading_space = line[:len(line) - len(line.lstrip())]
        content = line.lstrip()

        code_part, comment_part = self._split_comment(content)

        formatted_code = self._format_code_part(code_part)

        if comment_part is not None:
            if formatted_code.strip():
                result = formatted_code.rstrip() + "  " + comment_part
            else:
                result = comment_part
        else:
            result = formatted_code

        return leading_space + result

    def _split_comment(self, line_content):
        """Split a line into code and comment parts.

        Returns (code_part, comment_part) where comment_part may be None.
        """
        tokens = self._tokenize_line(line_content)
        code_tokens = []
        comment_token = None

        for tok in tokens:
            if tok[0] == _LINE_TOKEN_COMMENT:
                comment_token = tok[1]
                break
            code_tokens.append(tok)

        code_part = "".join(t[1] for t in code_tokens)
        return code_part, comment_token

    def _tokenize_line(self, line_content):
        """Very simple line-level tokenizer.

        Returns list of (type, value) tuples.
        """
        tokens = []
        pos = 0
        n = len(line_content)

        while pos < n:
            ch = line_content[pos]

            if ch == " " or ch == "\t":
                start = pos
                while pos < n and line_content[pos] in (" ", "\t"):
                    pos += 1
                tokens.append((_LINE_TOKEN_WHITESPACE, line_content[start:pos]))
                continue

            if ch == "/" and pos + 1 < n and line_content[pos + 1] == "/":
                tokens.append((_LINE_TOKEN_COMMENT, line_content[pos:]))
                break

            if ch == "/" and pos + 1 < n and line_content[pos + 1] == "*":
                end = line_content.find("*/", pos + 2)
                if end == -1:
                    tokens.append((_LINE_TOKEN_COMMENT, line_content[pos:]))
                    break
                pos = end + 2
                continue

            if ch == '"' or ch == "'":
                quote = ch
                start = pos
                pos += 1
                while pos < n and line_content[pos] != quote:
                    if line_content[pos] == "\\" and pos + 1 < n:
                        pos += 1
                    pos += 1
                if pos < n:
                    pos += 1
                tokens.append((_LINE_TOKEN_STRING, line_content[start:pos]))
                continue

            if ch.isdigit() or (ch == "." and pos + 1 < n and line_content[pos + 1].isdigit()):
                start = pos
                has_dot = ch == "."
                pos += 1
                while pos < n and (line_content[pos].isdigit() or line_content[pos] == "."):
                    if line_content[pos] == ".":
                        if has_dot:
                            break
                        has_dot = True
                    pos += 1
                tokens.append((_LINE_TOKEN_NUMBER, line_content[start:pos]))
                continue

            if ch.isalpha() or ch == "_":
                start = pos
                while pos < n and (line_content[pos].isalnum() or line_content[pos] == "_"):
                    pos += 1
                tokens.append((_LINE_TOKEN_WORD, line_content[start:pos]))
                continue

            three = line_content[pos:pos + 3] if pos + 2 < n else ""
            two = line_content[pos:pos + 2] if pos + 1 < n else ""

            if three in self._SPACED_OPERATORS or three in self._UNSPACED_OPERATORS:
                tokens.append((_LINE_TOKEN_OPERATOR, three))
                pos += 3
                continue

            if two in self._SPACED_OPERATORS or two in self._UNSPACED_OPERATORS:
                tokens.append((_LINE_TOKEN_OPERATOR, two))
                pos += 2
                continue

            if ch == "{" and pos + 1 < n and line_content[pos + 1] == ":":
                tokens.append((_LINE_TOKEN_OPERATOR, "{:"))
                pos += 2
                continue

            if ch in "{}[]()":
                tokens.append((_LINE_TOKEN_PUNCT, ch))
                pos += 1
                continue

            if ch in ",;:":
                tokens.append((_LINE_TOKEN_PUNCT, ch))
                pos += 1
                continue

            if ch in "+-*/%=<>!&|^~@?.":
                tokens.append((_LINE_TOKEN_OPERATOR, ch))
                pos += 1
                continue

            tokens.append((_LINE_TOKEN_WORD, ch))
            pos += 1

        return tokens

    def _format_code_part(self, code):
        """Format the code portion of a line (no comments)."""
        if not code.strip():
            return code

        tokens = self._tokenize_line(code)
        result_tokens = []

        i = 0
        while i < len(tokens):
            tok_type, tok_val = tokens[i]

            if tok_type == _LINE_TOKEN_WHITESPACE:
                i += 1
                continue

            prev_type, prev_val = (None, None)
            if result_tokens:
                prev_type, prev_val = result_tokens[-1]

            space_before = self._needs_space_before(
                tok_type, tok_val, prev_type, prev_val, tokens, i,
            )

            if space_before and result_tokens:
                result_tokens.append((_LINE_TOKEN_WHITESPACE, " "))

            if tok_type == _LINE_TOKEN_STRING:
                normalized = self._normalize_string_quotes(tok_val)
                result_tokens.append((tok_type, normalized))
            else:
                result_tokens.append((tok_type, tok_val))

            i += 1

        return "".join(t[1] for t in result_tokens)

    def _needs_space_before(self, tok_type, tok_val, prev_type, prev_val,
                            all_tokens, current_idx):
        """Determine whether a space is needed before this token."""
        if prev_type is None:
            return False

        if prev_type == _LINE_TOKEN_WHITESPACE:
            return False

        if tok_type == _LINE_TOKEN_PUNCT and tok_val in ("(", ")", "[", "]", "{", "}"):
            return self._space_around_bracket(prev_type, prev_val, tok_val,
                                              all_tokens, current_idx, is_open=False)

        if prev_type == _LINE_TOKEN_PUNCT and prev_val in ("(", "[", "{", "{:"):
            if tok_type == _LINE_TOKEN_PUNCT and tok_val in (")", "]", "}"):
                return False
            return False

        if tok_type == _LINE_TOKEN_PUNCT and tok_val == ",":
            return False

        if tok_type == _LINE_TOKEN_PUNCT and tok_val == ";":
            return False

        if tok_type == _LINE_TOKEN_PUNCT and tok_val == ":":
            return self._space_before_colon(prev_type, prev_val, all_tokens, current_idx)

        if prev_type == _LINE_TOKEN_PUNCT and prev_val == ",":
            return True

        if prev_type == _LINE_TOKEN_PUNCT and prev_val == ";":
            return True

        if prev_type == _LINE_TOKEN_PUNCT and prev_val == ":":
            return self._space_after_colon(all_tokens, current_idx - 1)

        if tok_type == _LINE_TOKEN_OPERATOR:
            if tok_val in self._UNSPACED_OPERATORS:
                return False
            if tok_val in ("!",):
                return False
            if tok_val in ("+", "-") and self._is_unary_minus_plus(tok_val, prev_type, prev_val, all_tokens, current_idx):
                if prev_type is None:
                    return False
                if prev_type == _LINE_TOKEN_PUNCT and prev_val in ("(", "[", "{", ",", ":", ";"):
                    return False
                if prev_type == _LINE_TOKEN_OPERATOR and prev_val not in ("=", "+=", "-=", "*=", "/=", "%="):
                    return False
            return True

        if prev_type == _LINE_TOKEN_OPERATOR:
            if prev_val in self._UNSPACED_OPERATORS:
                return False
            if prev_val in ("!",):
                return False
            if prev_val in ("+", "-"):
                prev_prev_type = None
                prev_prev_val = None
                j = current_idx - 1
                while j >= 0 and all_tokens[j][0] == _LINE_TOKEN_WHITESPACE:
                    j -= 1
                if j >= 0 and all_tokens[j][1] == prev_val:
                    j -= 1
                    while j >= 0 and all_tokens[j][0] == _LINE_TOKEN_WHITESPACE:
                        j -= 1
                    if j >= 0:
                        prev_prev_type, prev_prev_val = all_tokens[j]
                if self._is_unary_minus_plus(prev_val, prev_prev_type, prev_prev_val, all_tokens, current_idx - 1):
                    return False
            return True

        if prev_type == _LINE_TOKEN_WORD and tok_type == _LINE_TOKEN_PUNCT and tok_val == "(":
            if prev_val in ("if", "while", "for", "match", "return", "yield", "raise",
                            "assert", "not", "and", "or", "in", "is"):
                return True
            return False

        if prev_type == _LINE_TOKEN_PUNCT and prev_val == ")" and tok_type == _LINE_TOKEN_WORD:
            return True

        if prev_type == _LINE_TOKEN_STRING and tok_type == _LINE_TOKEN_STRING:
            return True

        if prev_type == _LINE_TOKEN_WORD and tok_type == _LINE_TOKEN_WORD:
            return True

        if prev_type == _LINE_TOKEN_WORD and tok_type == _LINE_TOKEN_NUMBER:
            return True

        if prev_type == _LINE_TOKEN_NUMBER and tok_type == _LINE_TOKEN_WORD:
            return True

        if prev_type == _LINE_TOKEN_NUMBER and tok_type == _LINE_TOKEN_NUMBER:
            return True

        if prev_type == _LINE_TOKEN_WORD and tok_type == _LINE_TOKEN_STRING:
            return True

        if prev_type == _LINE_TOKEN_STRING and tok_type == _LINE_TOKEN_WORD:
            return True

        return False

    def _space_around_bracket(self, prev_type, prev_val, bracket_val,
                              all_tokens, current_idx, is_open):
        """Determine spacing around brackets."""
        if bracket_val in ("(", "[", "{"):
            if prev_type == _LINE_TOKEN_WORD:
                if prev_val in ("if", "while", "for", "match", "return", "yield",
                                "raise", "assert", "not", "and", "or", "in", "is"):
                    return True
                return False
            if prev_type == _LINE_TOKEN_OPERATOR:
                return True
            if prev_type == _LINE_TOKEN_PUNCT and prev_val in (")", "]", "}"):
                return False
            return False
        else:
            return False

    def _space_before_colon(self, prev_type, prev_val, all_tokens, current_idx):
        """Determine if space is needed before a colon.

        Most of the time, no space before colon (type annotations, dict keys,
        slice syntax, etc.).
        """
        return False

    def _space_after_colon(self, all_tokens, current_idx):
        """Determine if space is needed after a colon (we're currently on colon)."""
        next_type, next_val = self._peek_non_ws(all_tokens, current_idx + 1)

        if next_type is None:
            return False

        if next_type == _LINE_TOKEN_PUNCT and next_val in (")", "]", "}", ","):
            return False

        return True

    def _is_unary_minus_plus(self, op_val, prev_type, prev_val, all_tokens, current_idx):
        """Check if +/- is being used as a unary operator."""
        if op_val not in ("+", "-"):
            return False

        if prev_type is None:
            return True

        if prev_type == _LINE_TOKEN_NUMBER:
            return False

        if prev_type == _LINE_TOKEN_STRING:
            return False

        if prev_type == _LINE_TOKEN_WORD:
            return False

        if prev_type == _LINE_TOKEN_PUNCT and prev_val in (")", "]", "}"):
            return False

        if prev_type == _LINE_TOKEN_OPERATOR:
            if prev_val in self._UNSPACED_OPERATORS:
                return True
            return True

        if prev_type == _LINE_TOKEN_PUNCT and prev_val in ("(", "[", "{", ",", ":", ";", "="):
            return True

        if prev_type == _LINE_TOKEN_WORD and prev_val in (
            "if", "while", "for", "return", "yield", "raise", "assert",
            "not", "and", "or", "in", "is", "elif", "case",
        ):
            return True

        return False

    @staticmethod
    def _peek_non_ws(tokens, start_idx):
        """Peek next non-whitespace token type and value."""
        i = start_idx
        while i < len(tokens):
            ttype, tval = tokens[i]
            if ttype != _LINE_TOKEN_WHITESPACE:
                return ttype, tval
            i += 1
        return None, None

    def _normalize_string_quotes(self, string_val):
        """Normalize string quotes to use the preferred quote character."""
        if len(string_val) < 2:
            return string_val

        preferred = self.options.quote_char
        first = string_val[0]
        last = string_val[-1]

        if first not in ('"', "'") or last not in ('"', "'"):
            return string_val

        if first == last and first == preferred:
            return string_val

        content = string_val[1:-1]

        if preferred in content:
            return string_val

        return preferred + content + preferred


# ---------------------------------------------------------------------------
# format_file convenience function
# ---------------------------------------------------------------------------

def format_file(filepath, options=None):
    """Format a Vox source file in-place.

    Args:
        filepath: Path to the .vox source file.
        options:  Optional FormatOptions instance.

    Returns:
        True if the file was modified, False if it was already formatted.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    formatter = VoxFormatter(options=options)
    formatted = formatter.format(source)

    if formatted == source:
        return False

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(formatted)

    return True
