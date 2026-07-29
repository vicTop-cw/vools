"""Indent-sensitive lexer for Vox language.

Based on Python's INDENT/DEDENT token approach.
"""

import re
from collections import namedtuple

Token = namedtuple("Token", ["type", "value", "line", "col"])


class VoxLexer:
    """Lexer that produces INDENT/DEDENT tokens for indentation-based syntax."""

    KEYWORDS = {
        "and", "as", "assert", "async", "await",
        "block", "break",
        "case", "catch", "class", "comptime", "const", "continue",
        "defer", "def", "define",
        "elif", "else", "enum", "Enum", "event", "exclude", "extend", "external",
        "false", "finally", "for", "from",
        "go", "guard",
        "if", "ignore", "impl", "import", "in", "include", "infix", "is",
        "let", "loop",
        "lazy",
        "macro", "match", "mut",
        "not", "none", "nthfix",
        "of", "omit", "owned",
        "pairfix", "prefix",
        "raise", "raises", "return",
        "Self", "spawn", "Static", "struct", "suffix", "suite", "super",
        "template", "test", "then", "trait", "transtime", "true", "try", "Type",
        "untyped",
        "val", "var",
        "when", "where", "while", "with",
        "yield",
    }

    OPERATORS = {
        "==", "!=", "<=", ">=", "<", ">",
        "+", "-", "*", "/", "%", "**",
        "&&", "!",
        "=", "+=", "-=", "*=", "/=", "%=",
        "::", ".", "?.", "??",
        "..", "..=",
        "->", "=>", "|",
        "@",
        "{:",  # dict opener
    }

    def __init__(self):
        pass

    def tokenize(self, source):
        """Tokenize source code into a list of Token objects."""
        tokens = []
        lines = source.split("\n")
        indent_stack = [0]
        line_num = 0

        # Track pending NEWLINE before INDENT/DEDENT
        pending_newline = False

        for raw_line in lines:
            line_num += 1
            line = raw_line.rstrip("\r")

            # Skip empty lines
            stripped = line.strip()
            if not stripped:
                continue

            # Doc comments: /// (but not //// or more, which are regular comments)
            if stripped.startswith("///") and not stripped.startswith("////"):
                doc_text = stripped[3:].strip()
                tokens.append(self._make_token("DOC", doc_text, line_num, 0))
                continue

            # Skip regular comments
            if stripped.startswith("//"):
                continue

            # Calculate indentation (spaces only, 4 spaces = 1 indent level)
            indent = len(line) - len(line.lstrip(" "))

            # Handle indent/dedent
            if indent > indent_stack[-1]:
                if pending_newline:
                    tokens.append(self._make_token("NEWLINE", "\\n", line_num, 0))
                    pending_newline = False
                indent_stack.append(indent)
                tokens.append(self._make_token("INDENT", "<INDENT>", line_num, 0))
            elif indent < indent_stack[-1]:
                while indent < indent_stack[-1]:
                    indent_stack.pop()
                    tokens.append(self._make_token("DEDENT", "<DEDENT>", line_num, 0))
                    tokens.append(self._make_token("NEWLINE", "\\n", line_num, 0))
                if indent != indent_stack[-1]:
                    raise SyntaxError("Inconsistent indentation at line {}".format(line_num))

            # Tokenize the line content
            line_tokens = self._tokenize_line(stripped, line_num)
            tokens.extend(line_tokens)
            pending_newline = True

        # Emit remaining DEDENTs and NEWLINEs
        while len(indent_stack) > 1:
            indent_stack.pop()
            tokens.append(self._make_token("DEDENT", "<DEDENT>", line_num, 0))
        if pending_newline:
            tokens.append(self._make_token("NEWLINE", "\\n", line_num, 0))

        tokens.append(self._make_token("EOF", "<EOF>", line_num, 0))
        return tokens

    def _tokenize_line(self, line, line_num):
        """Tokenize a single line of code."""
        tokens = []
        col = 0
        pos = 0

        while pos < len(line):
            ch = line[pos]

            # Whitespace
            if ch == " ":
                pos += 1
                col += 1
                continue

            # Comments
            if ch == "/" and pos + 1 < len(line) and line[pos + 1] == "/":
                break  # rest of line is comment

            # Multi-line comment
            if ch == "/" and pos + 1 < len(line) and line[pos + 1] == "*":
                # Skip until */
                end = line.find("*/", pos + 2)
                if end == -1:
                    raise SyntaxError("Unterminated /* comment at line {}".format(line_num))
                pos = end + 2
                col += 2
                continue

            # Raw strings: r"..." or r'...' (no escape processing)
            if (ch == 'r' or ch == 'R') and pos + 1 < len(line) and line[pos + 1] in ('"', "'"):
                quote = line[pos + 1]
                start = pos
                pos += 2  # skip r and opening quote
                while pos < len(line) and line[pos] != quote:
                    pos += 1  # raw: no escape processing
                if pos < len(line):
                    pos += 1  # skip closing quote
                # Strip the r prefix but keep the quotes so parser sees a normal STRING
                value = line[start + 1:pos]
                tokens.append(self._make_token("STRING", value, line_num, start))
                continue

            # Strings
            if ch == '"' or ch == "'":
                quote = ch
                start = pos
                pos += 1
                while pos < len(line) and line[pos] != quote:
                    if line[pos] == "\\":
                        pos += 1  # skip escaped char
                    pos += 1
                if pos < len(line):
                    pos += 1  # skip closing quote
                value = line[start:pos]
                tokens.append(self._make_token("STRING", value, line_num, start))
                continue

            # Dict opener {:}
            if ch == "{" and pos + 1 < len(line) and line[pos + 1] == ":":
                tokens.append(self._make_token("DICT_OPEN", "{:", line_num, pos))
                pos += 2
                continue

            # Multi-char operators
            if pos + 1 < len(line):
                two = line[pos:pos + 2]
                three = line[pos:pos + 3] if pos + 2 < len(line) else ""

                if three in self.OPERATORS:
                    tokens.append(self._make_token("OPERATOR", three, line_num, pos))
                    pos += 3
                    continue
                if two in self.OPERATORS:
                    tokens.append(self._make_token("OPERATOR", two, line_num, pos))
                    pos += 2
                    continue

            # Single-char operators and punctuation
            if ch in "{}[]():,;":
                tokens.append(self._make_token("PUNCT", ch, line_num, pos))
                pos += 1
                continue

            if ch in "+-*/%=<>!|&^~@.?":
                tokens.append(self._make_token("OPERATOR", ch, line_num, pos))
                pos += 1
                continue

            # Numbers
            if ch.isdigit() or (ch == "." and pos + 1 < len(line) and line[pos + 1].isdigit()):
                start = pos
                is_float = ch == "."
                pos += 1
                while pos < len(line) and (line[pos].isdigit() or line[pos] == "."):
                    if line[pos] == ".":
                        if is_float:
                            break
                        is_float = True
                    pos += 1
                value = line[start:pos]
                tokens.append(self._make_token("NUMBER", value, line_num, start))
                continue

            # Identifiers and keywords
            if ch.isalpha() or ch == "_":
                start = pos
                pos += 1
                while pos < len(line) and (line[pos].isalnum() or line[pos] == "_"):
                    pos += 1
                value = line[start:pos]
                if value in self.KEYWORDS:
                    tokens.append(self._make_token("KEYWORD", value, line_num, start))
                else:
                    tokens.append(self._make_token("NAME", value, line_num, start))
                continue

            # Unknown character
            raise SyntaxError("Unexpected character '{}' at line {} col {}".format(ch, line_num, pos))

        return tokens

    def _make_token(self, type_, value, line, col):
        return Token(type_, value, line, col)