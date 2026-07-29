"""Indent-sensitive lexer for Vox language.

Standalone implementation using Token class from voxc.libs.token and
keyword definitions from voxc.libs.keyword.
"""

from voxc.libs.token import Token, TokenType, OPERATORS, PUNCTUATIONS
from voxc.libs.keyword import ALL_KEYWORDS


class VoxLexer(object):
    """Lexer that produces INDENT/DEDENT tokens for indentation-based syntax.

    Interface-compatible with voxc.lexer.VoxLexer but uses the Token
    class from voxc.libs.token instead of a namedtuple.
    """

    KEYWORDS = ALL_KEYWORDS
    OPERATOR_SET = OPERATORS
    PUNCT_SET = PUNCTUATIONS

    def __init__(self):
        pass

    def tokenize(self, source):
        """Tokenize source code into a list of Token objects.

        Args:
            source: Source code string.

        Returns:
            List of Token objects.
        """
        tokens = []
        lines = source.split("\n")
        indent_stack = [0]
        line_num = 0
        pending_newline = False
        in_multiline_string = False
        multiline_quote = None
        multiline_start_line = 0
        multiline_start_col = 0
        multiline_value_parts = []

        for raw_line in lines:
            line_num += 1
            line = raw_line.rstrip("\r")

            if in_multiline_string:
                end_pos = line.find(multiline_quote * 3)
                if end_pos == -1:
                    multiline_value_parts.append(line)
                    continue
                else:
                    multiline_value_parts.append(line[:end_pos])
                    full_value = multiline_quote * 3 + "\n".join(multiline_value_parts) + multiline_quote * 3
                    tokens.append(self._make_token(
                        TokenType.STRING, full_value,
                        multiline_start_line, multiline_start_col
                    ))
                    in_multiline_string = False
                    line = line[end_pos + 3:]
                    if not line.strip():
                        continue
                    col = end_pos + 3
                    line_tokens = self._tokenize_rest(line, line_num, col)
                    tokens.extend(line_tokens)
                    pending_newline = True
                    continue

            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("///") and not stripped.startswith("////"):
                doc_text = stripped[3:].strip()
                indent = len(line) - len(line.lstrip(" "))
                tokens.append(self._make_token(TokenType.DOC, doc_text, line_num, indent))
                continue

            if stripped.startswith("//"):
                continue

            indent = len(line) - len(line.lstrip(" "))

            if indent > indent_stack[-1]:
                if pending_newline:
                    tokens.append(self._make_token(TokenType.NEWLINE, "\n", line_num, 0))
                    pending_newline = False
                indent_stack.append(indent)
                tokens.append(self._make_token(TokenType.INDENT, "<INDENT>", line_num, 0))
            elif indent < indent_stack[-1]:
                while indent < indent_stack[-1]:
                    indent_stack.pop()
                    tokens.append(self._make_token(TokenType.DEDENT, "<DEDENT>", line_num, 0))
                    tokens.append(self._make_token(TokenType.NEWLINE, "\n", line_num, 0))
                if indent != indent_stack[-1]:
                    raise SyntaxError("Inconsistent indentation at line {}".format(line_num))

            content_start = indent
            line_content = line[content_start:]

            result = self._tokenize_line_with_multiline(
                line_content, line_num, content_start
            )

            if result.get("multiline_pending"):
                in_multiline_string = True
                multiline_quote = result["multiline_quote"]
                multiline_start_line = result["multiline_start_line"]
                multiline_start_col = result["multiline_start_col"]
                multiline_value_parts = [result["multiline_partial"]]
                line_tokens = result["tokens"]
            else:
                line_tokens = result["tokens"]

            if line_tokens:
                tokens.extend(line_tokens)
                pending_newline = True

        while len(indent_stack) > 1:
            indent_stack.pop()
            tokens.append(self._make_token(TokenType.DEDENT, "<DEDENT>", line_num, 0))
        if pending_newline:
            tokens.append(self._make_token(TokenType.NEWLINE, "\n", line_num, 0))

        tokens.append(self._make_token(TokenType.EOF, "<EOF>", line_num, 0))
        return tokens

    def _tokenize_line_with_multiline(self, line, line_num, col_offset):
        """Tokenize a line, handling multi-line string starts.

        Returns a dict with:
            tokens: list of Token found on this line before any multi-line string
            multiline_pending: bool, whether we're inside a multi-line string
            multiline_quote: the quote char used
            multiline_start_line/col: start position
            multiline_partial: partial content (the part on this line after the opening quotes)
        """
        tokens = []
        pos = 0

        while pos < len(line):
            ch = line[pos]

            if ch == " ":
                pos += 1
                continue

            if ch == "/" and pos + 1 < len(line) and line[pos + 1] == "/":
                break

            if ch == "/" and pos + 1 < len(line) and line[pos + 1] == "*":
                end = line.find("*/", pos + 2)
                if end == -1:
                    break
                pos = end + 2
                continue

            if (ch == 'r' or ch == 'R') and pos + 1 < len(line) and line[pos + 1] in ('"', "'"):
                quote = line[pos + 1]
                if pos + 3 < len(line) and line[pos + 1:pos + 4] == quote * 3:
                    start = pos
                    pos += 4
                    end = line.find(quote * 3, pos)
                    if end == -1:
                        return {
                            "tokens": tokens,
                            "multiline_pending": True,
                            "multiline_quote": quote,
                            "multiline_start_line": line_num,
                            "multiline_start_col": col_offset + start,
                            "multiline_partial": line[pos:],
                        }
                    else:
                        value = line[start:end + 3]
                        tokens.append(self._make_token(
                            TokenType.STRING, value, line_num, col_offset + start
                        ))
                        pos = end + 3
                        continue
                else:
                    start = pos
                    pos += 2
                    while pos < len(line) and line[pos] != quote:
                        pos += 1
                    if pos < len(line):
                        pos += 1
                    value = line[start + 1:pos]
                    tokens.append(self._make_token(
                        TokenType.STRING, value, line_num, col_offset + start
                    ))
                    continue

            if ch == '"' or ch == "'":
                quote = ch
                if pos + 2 < len(line) and line[pos:pos + 3] == quote * 3:
                    start = pos
                    pos += 3
                    end = line.find(quote * 3, pos)
                    if end == -1:
                        return {
                            "tokens": tokens,
                            "multiline_pending": True,
                            "multiline_quote": quote,
                            "multiline_start_line": line_num,
                            "multiline_start_col": col_offset + start,
                            "multiline_partial": line[pos:],
                        }
                    else:
                        value = line[start:end + 3]
                        tokens.append(self._make_token(
                            TokenType.STRING, value, line_num, col_offset + start
                        ))
                        pos = end + 3
                        continue
                else:
                    start = pos
                    pos += 1
                    while pos < len(line) and line[pos] != quote:
                        if line[pos] == "\\":
                            pos += 1
                        pos += 1
                    if pos < len(line):
                        pos += 1
                    value = line[start:pos]
                    tokens.append(self._make_token(
                        TokenType.STRING, value, line_num, col_offset + start
                    ))
                    continue

            if ch == "{" and pos + 1 < len(line) and line[pos + 1] == ":":
                tokens.append(self._make_token(
                    TokenType.DICT_OPEN, "{:", line_num, col_offset + pos
                ))
                pos += 2
                continue

            if pos + 1 < len(line):
                two = line[pos:pos + 2]
                three = line[pos:pos + 3] if pos + 2 < len(line) else ""

                if three in self.OPERATOR_SET:
                    tokens.append(self._make_token(
                        TokenType.OPERATOR, three, line_num, col_offset + pos
                    ))
                    pos += 3
                    continue
                if two in self.OPERATOR_SET:
                    tokens.append(self._make_token(
                        TokenType.OPERATOR, two, line_num, col_offset + pos
                    ))
                    pos += 2
                    continue

            if ch in self.PUNCT_SET:
                tokens.append(self._make_token(
                    TokenType.PUNCT, ch, line_num, col_offset + pos
                ))
                pos += 1
                continue

            if ch in "+-*/%=<>!|&^~@.?":
                tokens.append(self._make_token(
                    TokenType.OPERATOR, ch, line_num, col_offset + pos
                ))
                pos += 1
                continue

            if ch.isdigit() or (ch == "." and pos + 1 < len(line) and line[pos + 1].isdigit() and (pos + 2 >= len(line) or line[pos + 1:pos + 3] != "..")):
                start = pos
                is_float = ch == "."
                pos += 1
                while pos < len(line) and (line[pos].isdigit() or line[pos] == "."):
                    if line[pos] == ".":
                        if pos + 1 < len(line) and line[pos + 1] == ".":
                            break
                        if is_float:
                            break
                        is_float = True
                    pos += 1
                value = line[start:pos]
                tokens.append(self._make_token(
                    TokenType.NUMBER, value, line_num, col_offset + start
                ))
                continue

            if ch.isalpha() or ch == "_":
                start = pos
                pos += 1
                while pos < len(line) and (line[pos].isalnum() or line[pos] == "_"):
                    pos += 1
                value = line[start:pos]
                if value in self.KEYWORDS:
                    tokens.append(self._make_token(
                        TokenType.KEYWORD, value, line_num, col_offset + start
                    ))
                else:
                    tokens.append(self._make_token(
                        TokenType.NAME, value, line_num, col_offset + start
                    ))
                continue

            raise SyntaxError(
                "Unexpected character '{}' at line {} col {}".format(
                    ch, line_num, col_offset + pos
                )
            )

        return {
            "tokens": tokens,
            "multiline_pending": False,
        }

    def _tokenize_rest(self, line, line_num, col_offset):
        """Tokenize the rest of a line after a multi-line string ends."""
        result = self._tokenize_line_with_multiline(line, line_num, col_offset)
        return result["tokens"]

    def _make_token(self, type_, value, line, col):
        return Token(type_, value, line, col)
