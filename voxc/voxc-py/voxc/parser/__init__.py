"""Recursive descent parser for Vox language.

Parses token stream from VoxLexer into AST nodes.
"""

from voxc.ast_nodes import (
    Module, Span, FnParam, LiteralValue,
    stmt_vardecl, stmt_fndef, stmt_expr, stmt_return, stmt_if, stmt_import,
    stmt_test, stmt_suite, stmt_template_decl, stmt_define_decl, stmt_operator_decl,
    stmt_struct_def, stmt_class_def, stmt_enum_def, stmt_trait_def, stmt_impl_block,
    stmt_extend_decl, stmt_match, stmt_comptime_block, stmt_transtime_block,
    stmt_ignore, stmt_exclude,
    struct_field, class_field, enum_variant, trait_method, match_arm,
    pattern_ident, pattern_lit, pattern_wildcard, pattern_guard,
    expr_literal, expr_ident, expr_binary, expr_call, expr_list, expr_if,
    expr_method_call, expr_attribute, expr_tuple, expr_template_invoke,
    type_named, type_optional, type_list, type_dict, type_generic,
)


class VoxParser:
    """Recursive descent parser for Vox."""

    def __init__(self):
        self.tokens = []
        self.pos = 0
        self.source_file = "<unknown>"
        # Pending doc comments collected from /// tokens, attached to next declaration
        self.pending_doc = None

    def parse(self, tokens, source_file="<unknown>"):
        """Parse token list into a Module AST node."""
        self.tokens = list(tokens)
        self.pos = 0
        self.source_file = source_file

        statements = []
        while not self._check("EOF"):
            stmt = self._parse_stmt()
            if stmt:
                statements.append(stmt)

        module_name = source_file.replace(".vox", "").replace("\\", "/").split("/")[-1]
        module = Module(module_name, statements, self._span(0, len(self.tokens)))

        # Expand templates
        module_dict = module.to_json()
        expanded = expand_templates(module_dict)

        # Rebuild Module from expanded dict
        from voxc.ast_nodes import Span as S
        result = Module(module_name, expanded.get("statements", []), S(
            expanded["span"]["file"], expanded["span"]["line"], expanded["span"]["col"],
            expanded["span"]["end_line"], expanded["span"]["end_col"]
        ))
        return result

    # ---- Token helpers ----

    def _peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def _check(self, type_, value=None):
        t = self._peek()
        if t is None:
            return type_ == "EOF"
        if value is not None:
            return t.type == type_ and t.value == value
        return t.type == type_

    def _match(self, type_, value=None):
        if self._check(type_, value):
            t = self.tokens[self.pos]
            self.pos += 1
            return t
        t = self._peek()
        expected = "{} {}".format(type_, value) if value else type_
        actual = "{} {}".format(t.type, t.value) if t else "EOF"
        raise SyntaxError("Expected {} but got {} at line {}".format(expected, actual, t.line if t else 0))

    def _consume(self, type_, value=None):
        """Consume a token if it matches, otherwise return None."""
        if self._check(type_, value):
            return self._match(type_, value)
        return None

    def _skip_newlines(self):
        """Skip NEWLINE tokens."""
        while self._check("NEWLINE"):
            self.pos += 1

    def _span(self, start, end=None):
        """Create a Span from token positions."""
        if end is None:
            end = self.pos
        if 0 <= start < len(self.tokens):
            t = self.tokens[start]
            line, col = t.line, t.col
        else:
            line, col = 1, 0
        return Span(self.source_file, line, col, line, col + 1)

    # ---- Statement parsing ----

    def _parse_stmt(self):
        """Parse a single statement."""
        self._skip_newlines()

        # Collect pending doc comments (/// tokens) — attach to next declaration.
        # Always reset pending_doc so it doesn't leak to subsequent statements.
        doc_lines = []
        while self._check("DOC"):
            doc_token = self._match("DOC")
            if doc_token.value:
                doc_lines.append(doc_token.value)
            self._skip_newlines()
        self.pending_doc = "\n".join(doc_lines) if doc_lines else None

        t = self._peek()
        if t is None or t.type == "EOF":
            return None

        if t.type == "KEYWORD":
            return self._parse_keyword_stmt(t.value)

        if t.type == "NAME":
            return self._parse_name_stmt()

        if t.type == "OPERATOR" and t.value == "@":
            return self._parse_decorator()

        # Non-declaration statement: clear pending doc
        self.pending_doc = None
        return self._parse_expr_stmt()

    def _parse_keyword_stmt(self, keyword):
        """Parse a statement starting with a keyword."""
        if keyword == "val" or keyword == "let":
            # `let` is an alias for `val` (immutable binding)
            return self._parse_var_decl(False)
        if keyword == "var":
            return self._parse_var_decl(True)
        if keyword == "const":
            return self._parse_const_decl()
        if keyword == "lazy":
            return self._parse_lazy_decl()
        if keyword == "def":
            return self._parse_fn_def()
        if keyword == "if":
            return self._parse_if_stmt()
        if keyword == "return":
            return self._parse_return_stmt()
        if keyword == "import":
            return self._parse_import_stmt()
        if keyword == "from":
            return self._parse_from_import()
        if keyword == "for":
            return self._parse_for_loop()
        if keyword == "while":
            return self._parse_while_loop()
        if keyword == "loop":
            return self._parse_loop()
        if keyword == "test":
            return self._parse_test()
        if keyword == "suite":
            return self._parse_suite()
        if keyword == "template":
            return self._parse_template_decl()
        if keyword == "define":
            return self._parse_define_decl()
        if keyword in ("prefix", "infix", "suffix", "nthfix", "pairfix"):
            return self._parse_operator_decl(keyword)
        if keyword == "struct":
            return self._parse_struct_def()
        if keyword == "class":
            return self._parse_class_def()
        if keyword == "enum":
            return self._parse_enum_def()
        if keyword == "trait":
            return self._parse_trait_def()
        if keyword == "impl":
            return self._parse_impl_block()
        if keyword == "extend":
            return self._parse_extend_decl()
        if keyword == "match":
            return self._parse_match_stmt()
        if keyword == "comptime":
            return self._parse_comptime_block()
        if keyword == "transtime":
            return self._parse_transtime_block()
        if keyword == "ignore":
            return self._parse_ignore_stmt()
        if keyword == "exclude":
            return self._parse_exclude_stmt()

        raise SyntaxError("Unexpected keyword '{}' at line {}".format(keyword, self._peek().line))

    def _parse_name_stmt(self):
        """Parse a statement starting with an identifier (assignment or expression)."""
        start = self.pos
        name_token = self._match("NAME")
        name = name_token.value

        # Check for assignment
        if self._check("OPERATOR", "="):
            self._match("OPERATOR", "=")
            value = self._parse_expr()
            return stmt_vardecl(name, value, mutable=True, span=self._span(start))
        if self._check("OPERATOR", "+="):
            return self._parse_aug_assign(name_token, "+=", start)
        if self._check("OPERATOR", "-="):
            return self._parse_aug_assign(name_token, "-=", start)

        # Method call or field access — fall back to expression parser
        if self._check("OPERATOR", "."):
            self.pos = start
            return self._parse_expr_stmt()

        # Expression statement
        self.pos = start
        return self._parse_expr_stmt()

    def _parse_aug_assign(self, name_token, op, start):
        self._match("OPERATOR", op)
        value = self._parse_expr()
        # For now, desugar to: name = name op value
        left = expr_ident(name_token.value, self._span(start))
        binop = op[0]  # +, -, *, /, %
        right = value
        return stmt_vardecl(name_token.value, expr_binary(left, binop, right), mutable=True, span=self._span(start))

    def _parse_var_decl(self, mutable):
        """Parse val/var declaration."""
        start = self.pos - 1  # account for keyword already consumed
        self._match("KEYWORD")  # val or var
        name = self._match("NAME").value

        # Optional type annotation
        type_ann = None
        if self._check("PUNCT", ":"):
            self._match("PUNCT", ":")
            type_ann = self._parse_type()

        self._match("OPERATOR", "=")
        value = self._parse_expr()

        return stmt_vardecl(name, value, mutable=mutable, type_annotation=type_ann, span=self._span(start))

    def _parse_const_decl(self):
        """Parse const declaration."""
        start = self.pos - 1
        self._match("KEYWORD")  # const
        name = self._match("NAME").value

        type_ann = None
        if self._check("PUNCT", ":"):
            self._match("PUNCT", ":")
            type_ann = self._parse_type()

        self._match("OPERATOR", "=")
        value = self._parse_expr()

        from voxc.ast_nodes import stmt_constdecl
        return stmt_constdecl(name, value, type_annotation=type_ann, span=self._span(start))

    def _parse_lazy_decl(self):
        """Parse lazy variable declaration: lazy var x = expr or lazy val x = expr"""
        start = self.pos - 1
        self._match("KEYWORD")  # lazy
        # Optional var/val keyword
        if self._check("KEYWORD", "var") or self._check("KEYWORD", "val"):
            self._match("KEYWORD")  # consume var/val
        name = self._match("NAME").value
        type_annotation = None
        if self._check("PUNCT", ":"):
            self._match("PUNCT", ":")
            type_annotation = self._parse_type()
        self._match("OPERATOR", "=")
        value = self._parse_expr()
        from voxc.ast_nodes import stmt_lazy_decl
        return stmt_lazy_decl(name, type_annotation, value, span=self._span(start))

    def _parse_fn_def(self):
        """Parse function definition."""
        start = self.pos - 1
        self._match("KEYWORD")  # def
        name = self._match("NAME").value

        # Optional generics
        generics = []
        if self._check("OPERATOR", "<"):
            generics = self._parse_generics()

        # Parameters
        self._match("PUNCT", "(")
        params = []
        if not self._check("PUNCT", ")"):
            params = self._parse_params()
        self._match("PUNCT", ")")

        # Return type
        return_type = None
        if self._check("OPERATOR", "->"):
            self._match("OPERATOR", "->")
            return_type = self._parse_type()

        self._match("PUNCT", ":")

        # Body
        body = self._parse_block()

        doc = self.pending_doc
        self.pending_doc = None
        return stmt_fndef(name, params, body, return_type=return_type, generics=generics, doc=doc, span=self._span(start))

    def _parse_params(self):
        """Parse function parameters."""
        params = []
        while not self._check("PUNCT", ")"):
            name = self._match("NAME").value
            type_ann = None
            default = None
            variadic = False

            if self._check("OPERATOR", "*"):
                self._match("OPERATOR", "*")
                variadic = True

            if self._check("PUNCT", ":"):
                self._match("PUNCT", ":")
                type_ann = self._parse_type()

            if self._check("OPERATOR", "="):
                self._match("OPERATOR", "=")
                default = self._parse_expr()

            params.append(FnParam(name, type_ann, default, variadic))

            if self._check("PUNCT", ","):
                self._match("PUNCT", ",")

        return params

    def _parse_generics(self):
        """Parse generic parameters <T, U>."""
        self._match("OPERATOR", "<")
        generics = []
        while not self._check("OPERATOR", ">"):
            name = self._match("NAME").value
            generics.append({"name": name, "bounds": []})
            if self._check("PUNCT", ","):
                self._match("PUNCT", ",")
        self._match("OPERATOR", ">")
        return generics

    def _parse_if_stmt(self):
        """Parse if/elif/else statement."""
        start = self.pos - 1
        self._match("KEYWORD")  # if
        condition = self._parse_expr()
        self._match("PUNCT", ":")
        then_body = self._parse_block()

        elif_chain = []
        self._skip_newlines()
        while self._check("KEYWORD", "elif"):
            self._match("KEYWORD")
            cond = self._parse_expr()
            self._match("PUNCT", ":")
            body = self._parse_block()
            elif_chain.append((cond.to_json(), [b.to_json() if hasattr(b, 'to_json') else b for b in body]))
            self._skip_newlines()

        else_body = None
        self._skip_newlines()
        if self._check("KEYWORD", "else"):
            self._match("KEYWORD")
            self._match("PUNCT", ":")
            else_body = self._parse_block()

        return stmt_if(condition, then_body, elif_chain, else_body, span=self._span(start))

    def _parse_return_stmt(self):
        """Parse return statement."""
        start = self.pos - 1
        self._match("KEYWORD")  # return

        value = None
        if not self._check("NEWLINE") and not self._check("EOF") and not self._check("DEDENT"):
            value = self._parse_expr()

        return stmt_return(value, span=self._span(start))

    def _parse_import_stmt(self):
        """Parse import statement."""
        start = self.pos - 1
        self._match("KEYWORD")  # import
        module_parts = []
        module_parts.append(self._match("NAME").value)
        while self._check("OPERATOR", "."):
            self._match("OPERATOR", ".")
            module_parts.append(self._match("NAME").value)

        items = None
        alias = None
        if self._check("OPERATOR", "::"):
            self._match("OPERATOR", "::")
            self._match("PUNCT", "{")
            items = []
            while not self._check("PUNCT", "}"):
                items.append(self._match("NAME").value)
                if self._check("PUNCT", ","):
                    self._match("PUNCT", ",")
            self._match("PUNCT", "}")
        elif self._check("KEYWORD", "as"):
            self._match("KEYWORD")
            alias = self._match("NAME").value

        return stmt_import(module_parts, items, alias, span=self._span(start))

    def _parse_from_import(self):
        """Parse from ... import ... statement."""
        start = self.pos - 1
        self._match("KEYWORD")  # from
        module_parts = []
        module_parts.append(self._match("NAME").value)
        while self._check("OPERATOR", "."):
            self._match("OPERATOR", ".")
            module_parts.append(self._match("NAME").value)

        self._match("KEYWORD", "import")
        items = [self._match("NAME").value]
        while self._check("PUNCT", ","):
            self._match("PUNCT", ",")
            items.append(self._match("NAME").value)

        from voxc.ast_nodes import stmt_from_import
        return stmt_from_import(module_parts, items, span=self._span(start))

    def _parse_for_loop(self):
        """Parse for loop."""
        start = self.pos - 1
        self._match("KEYWORD")  # for
        var = self._match("NAME").value
        self._match("KEYWORD", "in")
        iterable = self._parse_expr()

        guard = None
        if self._check("KEYWORD", "if"):
            self._match("KEYWORD")
            guard = self._parse_expr()

        self._match("PUNCT", ":")
        body = self._parse_block()

        else_body = None
        if self._check("KEYWORD", "else"):
            self._match("KEYWORD")
            self._match("PUNCT", ":")
            else_body = self._parse_block()

        from voxc.ast_nodes import stmt_for_loop
        return stmt_for_loop(var, iterable, guard, body, else_body, span=self._span(start))

    def _parse_while_loop(self):
        """Parse while loop."""
        start = self.pos - 1
        self._match("KEYWORD")  # while
        condition = self._parse_expr()
        self._match("PUNCT", ":")
        body = self._parse_block()

        else_body = None
        if self._check("KEYWORD", "else"):
            self._match("KEYWORD")
            self._match("PUNCT", ":")
            else_body = self._parse_block()

        from voxc.ast_nodes import stmt_while_loop
        return stmt_while_loop(condition, body, else_body, span=self._span(start))

    def _parse_loop(self):
        """Parse infinite loop."""
        start = self.pos - 1
        self._match("KEYWORD")  # loop
        self._match("PUNCT", ":")
        body = self._parse_block()

        from voxc.ast_nodes import stmt_loop
        return stmt_loop(body, span=self._span(start))

    def _parse_test(self):
        """Parse test case."""
        start = self.pos - 1
        self._match("KEYWORD")  # test
        name = self._match("NAME").value
        self._match("PUNCT", ":")
        body = self._parse_block()
        return stmt_test(name, body, span=self._span(start))

    def _parse_suite(self):
        """Parse test suite."""
        start = self.pos - 1
        self._match("KEYWORD")  # suite
        name = self._match("NAME").value
        self._match("PUNCT", ":")
        body = self._parse_block()
        return stmt_suite(name, body, span=self._span(start))

    def _parse_template_decl(self):
        """Parse template declaration."""
        start = self.pos - 1
        self._match("KEYWORD")  # template
        name = self._match("NAME").value

        # Optional generics
        generics = []
        if self._check("OPERATOR", "<"):
            generics = self._parse_generics()

        # Parameters
        self._match("PUNCT", "(")
        params = []
        if not self._check("PUNCT", ")"):
            params = self._parse_params()
        self._match("PUNCT", ")")

        self._match("PUNCT", ":")
        body = self._parse_block()

        return stmt_template_decl(name, params, body, generics, span=self._span(start))

    def _parse_define_decl(self):
        """Parse define type constraint declaration."""
        start = self.pos - 1
        self._match("KEYWORD")  # define
        name = self._match("NAME").value

        # Optional generics
        generics = []
        if self._check("OPERATOR", "<"):
            generics = self._parse_generics()

        self._match("PUNCT", ":")
        self._match("NEWLINE")
        self._match("INDENT")

        props = []
        statics = []
        typemethods = []
        instancemethods = []
        check = None

        while not self._check("DEDENT") and not self._check("EOF"):
            self._skip_newlines()
            if self._check("DEDENT") or self._check("EOF"):
                break

            section = self._match("NAME").value
            self._match("PUNCT", ":")
            self._match("NEWLINE")
            self._match("INDENT")

            if section == "props":
                props = self._parse_define_entries()
            elif section == "statics":
                statics = self._parse_define_entries()
            elif section == "typemethods":
                typemethods = self._parse_define_entries()
            elif section == "instancemethods":
                instancemethods = self._parse_define_entries()
            elif section == "check":
                check = self._parse_block()
            else:
                raise SyntaxError("Unknown define section '{}' at line {}".format(section, self._peek().line))

            self._match("DEDENT")

        self._match("DEDENT")

        return stmt_define_decl(name, props, statics, typemethods, instancemethods, generics, check, span=self._span(start))

    def _parse_operator_decl(self, op_type_keyword):
        """Parse operator declaration: prefix/infix/suffix/nthfix/pairfix."""
        start = self.pos - 1
        self._match("KEYWORD")  # consume the op_type keyword

        # Map keyword to OperatorType enum variant
        op_type_map = {
            "prefix": "Prefix", "infix": "Infix", "suffix": "Suffix",
            "nthfix": "Nthfix", "pairfix": "Pairfix",
        }
        op_type = op_type_map[op_type_keyword]

        # Parse operator symbol (may be multi-character)
        symbol = ""
        t = self._peek()
        if t.type == "OPERATOR":
            symbol = self._match("OPERATOR").value
            # For multi-character operators (e.g., ++), consume consecutive operators
            while self._peek().type == "OPERATOR":
                symbol += self._match("OPERATOR").value
        elif t.type == "PUNCT":
            symbol = self._match("PUNCT").value
        elif t.type == "NAME":
            symbol = self._match("NAME").value
        else:
            raise SyntaxError("Expected operator symbol after '{}' at line {}".format(op_type_keyword, t.line))

        # For pairfix, the symbol represents both open/close symbols
        # (e.g., 《》 is two chars, QQ is one token treated as both)
        if op_type_keyword == "pairfix":
            pass  # symbol is already set, represents both sides

        # Optional generics
        generics = []
        if self._check("OPERATOR", "<"):
            generics = self._parse_generics()

        # Function name
        name = self._match("NAME").value

        # Parameters
        self._match("PUNCT", "(")
        params = []
        if not self._check("PUNCT", ")"):
            params = self._parse_params()
        self._match("PUNCT", ")")

        # Return type
        return_type = type_named("void")
        if self._check("OPERATOR", "->"):
            self._match("OPERATOR", "->")
            return_type = self._parse_type()

        self._match("PUNCT", ":")
        self._match("NEWLINE")

        # Body (skip it, implementation details are not needed for AST)
        self._match("INDENT")
        self._skip_block_body()
        # _skip_block_body already consumed the matching DEDENT

        return stmt_operator_decl(op_type, symbol, name, params, return_type, generics, span=self._span(start))

    def _parse_struct_def(self):
        """Parse struct definition."""
        start = self.pos - 1
        self._match("KEYWORD")  # struct
        name = self._match("NAME").value

        # Optional generics
        generics = []
        if self._check("OPERATOR", "<"):
            generics = self._parse_generics()

        self._match("PUNCT", ":")
        self._match("NEWLINE")
        self._match("INDENT")

        fields = self._parse_struct_fields()
        self._match("DEDENT")

        doc = self.pending_doc
        self.pending_doc = None
        return stmt_struct_def(name, fields, generics, doc=doc, span=self._span(start))

    def _parse_struct_fields(self):
        """Parse struct field declarations."""
        fields = []
        while not self._check("DEDENT") and not self._check("EOF"):
            self._skip_newlines()
            # Skip DOC tokens inside struct body (field-level docs not yet attached)
            while self._check("DOC"):
                self._match("DOC")
                self._skip_newlines()
            if self._check("DEDENT") or self._check("EOF"):
                break
            field_name = self._match("NAME").value
            self._match("PUNCT", ":")
            field_type = self._parse_type()
            fields.append(struct_field(field_name, field_type))
        return fields

    def _parse_class_def(self):
        """Parse class definition."""
        start = self.pos - 1
        self._match("KEYWORD")  # class
        name = self._match("NAME").value

        # Optional parent
        parent = None
        if self._check("PUNCT", "("):
            self._match("PUNCT", "(")
            parent = self._match("NAME").value
            self._match("PUNCT", ")")

        self._match("PUNCT", ":")
        self._match("NEWLINE")
        self._match("INDENT")

        fields = []
        methods = []

        while not self._check("DEDENT") and not self._check("EOF"):
            self._skip_newlines()
            # Skip DOC tokens inside class body
            while self._check("DOC"):
                self._match("DOC")
                self._skip_newlines()
            if self._check("DEDENT") or self._check("EOF"):
                break

            # Check if it's a method (def keyword) or field
            if self._check("KEYWORD", "def"):
                methods.append(self._parse_stmt())
            else:
                field_name = self._match("NAME").value
                self._match("PUNCT", ":")
                field_type = self._parse_type()
                mutable = False
                # Optional = default
                default = None
                if self._check("OPERATOR", "="):
                    self._match("OPERATOR", "=")
                    default = self._parse_expr()
                fields.append(class_field(field_name, field_type, default, mutable))

        self._match("DEDENT")

        doc = self.pending_doc
        self.pending_doc = None
        return stmt_class_def(name, fields, methods, parent, doc=doc, span=self._span(start))

    def _parse_enum_def(self):
        """Parse enum definition."""
        start = self.pos - 1
        self._match("KEYWORD")  # enum
        name = self._match("NAME").value

        # Optional generics
        generics = []
        if self._check("OPERATOR", "<"):
            generics = self._parse_generics()

        self._match("PUNCT", ":")
        self._match("NEWLINE")
        self._match("INDENT")

        variants = []
        while not self._check("DEDENT") and not self._check("EOF"):
            self._skip_newlines()
            # Skip DOC tokens inside enum body
            while self._check("DOC"):
                self._match("DOC")
                self._skip_newlines()
            if self._check("DEDENT") or self._check("EOF"):
                break
            var_name = self._match("NAME").value
            # Optional data type
            data = None
            if self._check("PUNCT", "("):
                self._match("PUNCT", "(")
                data = self._parse_type()
                self._match("PUNCT", ")")
            variants.append(enum_variant(var_name, data))

        self._match("DEDENT")

        doc = self.pending_doc
        self.pending_doc = None
        return stmt_enum_def(name, variants, generics, doc=doc, span=self._span(start))

    def _parse_trait_def(self):
        """Parse trait definition."""
        start = self.pos - 1
        self._match("KEYWORD")  # trait
        name = self._match("NAME").value

        # Optional generics
        generics = []
        if self._check("OPERATOR", "<"):
            generics = self._parse_generics()

        self._match("PUNCT", ":")
        self._match("NEWLINE")
        self._match("INDENT")

        methods = self._parse_trait_methods()

        self._match("DEDENT")

        doc = self.pending_doc
        self.pending_doc = None
        return stmt_trait_def(name, methods, generics, doc=doc, span=self._span(start))

    def _parse_trait_methods(self):
        """Parse trait method declarations."""
        methods = []
        while not self._check("DEDENT") and not self._check("EOF"):
            self._skip_newlines()
            # Skip DOC tokens inside trait body
            while self._check("DOC"):
                self._match("DOC")
                self._skip_newlines()
            if self._check("DEDENT") or self._check("EOF"):
                break

            self._match("KEYWORD", "def")
            method_name = self._match("NAME").value

            # Optional generics
            if self._check("OPERATOR", "<"):
                self._parse_generics()

            self._match("PUNCT", "(")
            params = []
            if not self._check("PUNCT", ")"):
                params = self._parse_params()
            self._match("PUNCT", ")")

            # Return type
            return_type = None
            if self._check("OPERATOR", "->"):
                self._match("OPERATOR", "->")
                return_type = self._parse_type()

            # Default implementation
            default_body = None
            if self._check("PUNCT", ":"):
                self._match("PUNCT", ":")
                default_body = self._parse_block()

            methods.append(trait_method(method_name, params, return_type, default_body))

        return methods

    def _parse_impl_block(self):
        """Parse impl block."""
        start = self.pos - 1
        self._match("KEYWORD")  # impl

        trait_name = None
        type_name = self._match("NAME").value

        # Check for "impl Trait for Type" syntax
        if self._check("KEYWORD", "for"):
            self._match("KEYWORD", "for")
            trait_name = type_name
            type_name = self._match("NAME").value

        self._match("PUNCT", ":")
        self._match("NEWLINE")
        self._match("INDENT")

        methods = []
        while not self._check("DEDENT") and not self._check("EOF"):
            self._skip_newlines()
            if self._check("DEDENT") or self._check("EOF"):
                break
            methods.append(self._parse_stmt())

        self._match("DEDENT")

        return stmt_impl_block(type_name, methods, trait_name, span=self._span(start))

    def _parse_extend_decl(self):
        """Parse extend declaration."""
        start = self.pos - 1
        self._match("KEYWORD")  # extend

        target = self._match("NAME").value

        self._match("KEYWORD", "for")
        for_type = self._match("NAME").value

        self._match("PUNCT", ":")
        self._match("NEWLINE")
        self._match("INDENT")

        methods = []
        while not self._check("DEDENT") and not self._check("EOF"):
            self._skip_newlines()
            if self._check("DEDENT") or self._check("EOF"):
                break
            methods.append(self._parse_stmt())

        self._match("DEDENT")

        return stmt_extend_decl(target, for_type, methods, span=self._span(start))

    def _parse_match_stmt(self):
        """Parse match statement."""
        start = self.pos - 1
        self._match("KEYWORD")  # match

        expr = self._parse_expr()
        self._match("PUNCT", ":")
        self._match("NEWLINE")
        self._match("INDENT")

        arms = []
        while not self._check("DEDENT") and not self._check("EOF"):
            self._skip_newlines()
            if self._check("DEDENT") or self._check("EOF"):
                break

            # Parse pattern
            pattern = self._parse_pattern()

            # Optional guard
            guard = None
            if self._check("KEYWORD", "if"):
                self._match("KEYWORD", "if")
                guard = self._parse_expr()

            self._match("OPERATOR", "=>")

            body = []
            if self._check("NEWLINE"):
                # Multi-line arm body with indented block
                self._match("NEWLINE")
                self._match("INDENT")
                while not self._check("DEDENT") and not self._check("EOF"):
                    self._skip_newlines()
                    if self._check("DEDENT") or self._check("EOF"):
                        break
                    body.append(self._parse_stmt())
                self._match("DEDENT")
            else:
                # Single-line expression arm
                s = self._parse_stmt()
                body.append(s)

            arms.append(match_arm(pattern, body, guard))

        self._match("DEDENT")

        return stmt_match(expr, arms, span=self._span(start))

    def _parse_pattern(self):
        """Parse a pattern."""
        t = self._peek()

        if t.type == "NAME":
            name = self._match("NAME").value
            if name == "_":
                return pattern_wildcard()
            return pattern_ident(name)

        if t.type == "NUMBER":
            value = self._match("NUMBER").value
            return pattern_lit("Int", int(value))

        if t.type == "STRING":
            value = self._match("STRING").value
            return pattern_lit("String", value)

        raise SyntaxError("Expected pattern at line {}".format(t.line))

    def _parse_comptime_block(self):
        """Parse comptime block — executed at Rust compile time."""
        start = self.pos - 1
        self._match("KEYWORD")  # comptime

        self._match("PUNCT", ":")
        body = self._parse_block()

        return stmt_comptime_block(body, span=self._span(start))

    def _parse_transtime_block(self):
        """Parse transtime block — executed at Vox transpilation time."""
        start = self.pos - 1
        self._match("KEYWORD")  # transtime

        self._match("PUNCT", ":")
        body = self._parse_block()

        return stmt_transtime_block(body, span=self._span(start))

    def _parse_ignore_stmt(self):
        """Parse ignore statement.

        Supported forms:
            ignore test name:
                body
            ignore test "test_name":
                body
        Generates #[ignore] attribute on the test function in Rust codegen.
        """
        start = self.pos - 1
        self._match("KEYWORD")  # ignore

        # Target — what is being ignored (e.g. "test", which is a keyword)
        # Accept either NAME or KEYWORD (since `test` is a keyword)
        t = self._peek()
        if t is not None and (t.type == "NAME" or t.type == "KEYWORD"):
            target = self._match(t.type).value
        else:
            raise SyntaxError("Expected target name after 'ignore' at line {}".format(
                t.line if t else 0))

        # Optional name — may be a NAME or a STRING literal
        name = None
        if self._check("NAME"):
            name = self._match("NAME").value
        elif self._check("STRING"):
            name = self._match("STRING").value
            # Strip surrounding quotes
            if len(name) >= 2 and name[0] in "\"'" and name[-1] == name[0]:
                name = name[1:-1]

        # Optional parameter list: ignore test fn_name() { ... }
        if self._check("PUNCT", "("):
            self._match("PUNCT", "(")
            # Skip params (not stored on IgnoreStmt)
            while not self._check("PUNCT", ")"):
                self.pos += 1
            self._match("PUNCT", ")")

        if name is None:
            name = "ignored_{}".format(target)

        self._match("PUNCT", ":")
        body = self._parse_block()

        return stmt_ignore(target, name, body, span=self._span(start))

    def _parse_exclude_stmt(self):
        """Parse exclude statement.

        Syntax: exclude module_name { item1, item2 }
        Imports everything from module EXCEPT listed items.
        """
        start = self.pos - 1
        self._match("KEYWORD")  # exclude

        # Module path (dotted or double-colon separated)
        module_parts = [self._match("NAME").value]
        while self._check("OPERATOR", ".") or self._check("OPERATOR", "::"):
            sep = self._peek().value
            self._match("OPERATOR", sep)
            module_parts.append(self._match("NAME").value)

        # Items to exclude
        items = []
        if self._check("PUNCT", "{"):
            self._match("PUNCT", "{")
            while not self._check("PUNCT", "}"):
                items.append(self._match("NAME").value)
                if self._check("PUNCT", ","):
                    self._match("PUNCT", ",")
            self._match("PUNCT", "}")
        elif self._check("PUNCT", ":"):
            # Block form: exclude mod:
            #     item1
            #     item2
            self._match("PUNCT", ":")
            self._match("NEWLINE")
            self._match("INDENT")
            while not self._check("DEDENT") and not self._check("EOF"):
                self._skip_newlines()
                if self._check("DEDENT") or self._check("EOF"):
                    break
                items.append(self._match("NAME").value)
            self._match("DEDENT")

        return stmt_exclude(module_parts, items, span=self._span(start))

    def _skip_block_body(self):
        """Skip over a block body without building AST."""
        depth = 1
        while depth > 0 and not self._check("EOF"):
            if self._check("DEDENT"):
                self._match("DEDENT")
                depth -= 1
            elif self._check("INDENT"):
                self._match("INDENT")
                depth += 1
            else:
                self.pos += 1

    def _parse_define_entries(self):
        """Parse define constraint entries: name: type."""
        entries = []
        while not self._check("DEDENT") and not self._check("EOF"):
            self._skip_newlines()
            if self._check("DEDENT") or self._check("EOF"):
                break
            entry_name = self._match("NAME").value
            self._match("PUNCT", ":")
            entry_type = self._parse_type()
            entries.append((entry_name, entry_type.to_json() if hasattr(entry_type, 'to_json') else entry_type))
        return entries

    def _parse_decorator(self):
        """Parse decorator @name (supports chaining)."""
        from voxc.ast_nodes import stmt_decorated
        start = self.pos
        decorators = []
        while self._check("OPERATOR", "@"):
            self._match("OPERATOR", "@")
            decorators.append(self._match("NAME").value)
            self._skip_newlines()
        stmt = self._parse_stmt()
        return stmt_decorated(decorators, stmt, span=self._span(start))

    def _parse_expr_stmt(self):
        """Parse an expression statement."""
        start = self.pos
        expr = self._parse_expr()
        return stmt_expr(expr, span=self._span(start))

    def _parse_block(self):
        """Parse an indented block of statements."""
        self._match("NEWLINE")
        self._match("INDENT")

        stmts = []
        while not self._check("DEDENT") and not self._check("EOF"):
            stmt = self._parse_stmt()
            if stmt:
                stmts.append(stmt)
            self._skip_newlines()

        self._match("DEDENT")
        return stmts

    # ---- Expression parsing ----

    def _parse_expr(self):
        """Parse an expression (top level)."""
        return self._parse_if_expr()

    def _parse_if_expr(self):
        """Parse ternary if-expression: a if cond else b."""
        left = self._parse_comparison()
        if self._check("KEYWORD", "if"):
            saved_pos = self.pos
            self._match("KEYWORD")
            condition = self._parse_expr()
            # Distinguish: if followed by ":" is a statement, not a ternary expression
            if self._check("PUNCT", ":"):
                # Roll back: this is a statement-level if
                self.pos = saved_pos
                return left
            # Ternary expression: left if condition else right
            self._match("KEYWORD", "else")
            else_expr = self._parse_expr()
            return expr_if(condition, left, else_expr)
        return left

    def _parse_comparison(self):
        """Parse comparison expressions, including `in` and `not in`."""
        left = self._parse_additive()
        while True:
            # Standard comparison operators
            if self._check("OPERATOR") and self._peek().value in ("==", "!=", "<", ">", "<=", ">="):
                op = self._match("OPERATOR").value
                right = self._parse_additive()
                left = expr_binary(left, op, right)
            # `in` keyword (membership test)
            elif self._check("KEYWORD", "in"):
                self._match("KEYWORD", "in")
                right = self._parse_additive()
                left = expr_binary(left, "in", right)
            # `not in` keyword sequence
            elif self._check("KEYWORD", "not") and self._peek_next_is("KEYWORD", "in"):
                self._match("KEYWORD", "not")
                self._match("KEYWORD", "in")
                right = self._parse_additive()
                left = expr_binary(left, "not in", right)
            else:
                break
        return left

    def _peek_next_is(self, type_, value):
        """Check if the token after the current one matches the given type/value."""
        if self.pos + 1 < len(self.tokens):
            nxt = self.tokens[self.pos + 1]
            if value is not None:
                return nxt.type == type_ and nxt.value == value
            return nxt.type == type_
        return False

    def _parse_additive(self):
        """Parse additive expressions (+ -)."""
        left = self._parse_multiplicative()
        while self._check("OPERATOR") and self._peek().value in ("+", "-"):
            op = self._match("OPERATOR").value
            right = self._parse_multiplicative()
            left = expr_binary(left, op, right)
        return left

    def _parse_multiplicative(self):
        """Parse multiplicative expressions (* / %)."""
        left = self._parse_unary()
        while self._check("OPERATOR") and self._peek().value in ("*", "/", "%"):
            op = self._match("OPERATOR").value
            right = self._parse_unary()
            left = expr_binary(left, op, right)
        return left

    def _parse_unary(self):
        """Parse unary expressions (- !) and lambdas."""
        # Lambda: |params| body  (e.g., |x| x + 1, |x, y| x + y)
        if self._check("OPERATOR", "|"):
            return self._parse_lambda()
        if self._check("OPERATOR") and self._peek().value in ("-", "!"):
            op = self._match("OPERATOR").value
            operand = self._parse_unary()
            return expr_unary(op, operand)
        return self._parse_call()

    def _parse_lambda(self):
        """Parse a lambda/closure: |params| body"""
        from voxc.ast_nodes import expr_lambda
        start = self.pos
        self._match("OPERATOR", "|")
        params = []
        if not self._check("OPERATOR", "|"):
            params.append(self._match("NAME").value)
            while self._check("PUNCT", ","):
                self._match("PUNCT", ",")
                params.append(self._match("NAME").value)
        self._match("OPERATOR", "|")
        # Optional return type: |x| -> int body
        return_type = None
        if self._check("OPERATOR", "->"):
            self._match("OPERATOR", "->")
            return_type = self._parse_type()
        body = self._parse_expr()
        return expr_lambda(params, body, return_type=return_type, span=self._span(start))

    def _parse_call(self):
        """Parse function calls and method calls."""
        expr = self._parse_primary()

        while True:
            if self._check("PUNCT", "("):
                self._match("PUNCT", "(")
                args = []
                if not self._check("PUNCT", ")"):
                    args = self._parse_args()
                self._match("PUNCT", ")")
                expr = expr_call(expr, args)
            elif self._check("OPERATOR", "."):
                self._match("OPERATOR", ".")
                # Method/attribute name can be a NAME or a KEYWORD
                # (e.g., `re.match(...)` — `match` is a keyword but used as method name)
                t = self._peek()
                if t is not None and (t.type == "NAME" or t.type == "KEYWORD"):
                    name = self._match(t.type).value
                else:
                    name = self._match("NAME").value
                if self._check("PUNCT", "("):
                    self._match("PUNCT", "(")
                    args = []
                    if not self._check("PUNCT", ")"):
                        args = self._parse_args()
                    self._match("PUNCT", ")")
                    expr = expr_method_call(expr, name, args)
                else:
                    expr = expr_attribute(expr, name)
            elif self._check("PUNCT", "["):
                self._match("PUNCT", "[")
                index = self._parse_expr()
                self._match("PUNCT", "]")
                from voxc.ast_nodes import expr_index
                expr = expr_index(expr, index)
            else:
                break

        return expr

    def _parse_args(self):
        """Parse function arguments."""
        args = [self._parse_expr()]
        while self._check("PUNCT", ","):
            self._match("PUNCT", ",")
            args.append(self._parse_expr())
        return args

    def _parse_primary(self):
        """Parse primary expressions (literals, identifiers, parenthesized)."""
        t = self._peek()
        if t is None:
            raise SyntaxError("Unexpected end of input")

        if t.type == "NUMBER":
            self._match("NUMBER")
            value = t.value
            if "." in value:
                return expr_literal("Float", float(value))
            return expr_literal("Int", int(value))

        if t.type == "STRING":
            self._match("STRING")
            # Strip quotes
            s = t.value
            if s.startswith('"') and s.endswith('"'):
                s = s[1:-1]
            elif s.startswith("'") and s.endswith("'"):
                s = s[1:-1]
            return expr_literal("String", s)

        if t.type == "KEYWORD":
            if t.value == "true":
                self._match("KEYWORD")
                return expr_literal("Bool", True)
            if t.value == "false":
                self._match("KEYWORD")
                return expr_literal("Bool", False)
            if t.value == "none":
                self._match("KEYWORD")
                return expr_literal("None", None)

        if t.type == "NAME":
            self._match("NAME")
            return expr_ident(t.value)

        if t.type == "PUNCT":
            if t.value == "(":
                return self._parse_tuple_or_paren()
            if t.value == "[":
                return self._parse_list()
            if t.value == "{":
                return self._parse_set_or_dict()

        if t.type == "DICT_OPEN":
            return self._parse_dict()

        raise SyntaxError("Unexpected token '{}' at line {}".format(t.value, t.line))

    def _parse_tuple_or_paren(self):
        """Parse parenthesized expression or tuple."""
        self._match("PUNCT", "(")
        expr = self._parse_expr()

        if self._check("PUNCT", ","):
            elements = [expr]
            while self._check("PUNCT", ","):
                self._match("PUNCT", ",")
                if self._check("PUNCT", ")"):
                    break
                elements.append(self._parse_expr())
            self._match("PUNCT", ")")
            return expr_tuple(elements)

        self._match("PUNCT", ")")
        return expr  # just parenthesized

    def _parse_list(self):
        """Parse list literal [a, b, c]."""
        self._match("PUNCT", "[")
        elements = []
        if not self._check("PUNCT", "]"):
            elements = self._parse_args()
        self._match("PUNCT", "]")
        return expr_list(elements)

    def _parse_set_or_dict(self):
        """Parse set literal {a, b}."""
        self._match("PUNCT", "{")
        # Empty set: {}
        if self._check("PUNCT", "}"):
            self._match("PUNCT", "}")
            from voxc.ast_nodes import expr_set
            return expr_set([])

        elements = self._parse_args()
        self._match("PUNCT", "}")
        from voxc.ast_nodes import expr_set
        return expr_set(elements)

    def _parse_dict(self):
        """Parse dict literal {: key: val, ...}."""
        self._match("DICT_OPEN")
        entries = []

        if self._check("PUNCT", "}"):
            self._match("PUNCT", "}")
            from voxc.ast_nodes import expr_dict
            return expr_dict(entries)

        while not self._check("PUNCT", "}"):
            key = self._parse_expr()
            if isinstance(key, dict) and key.get("node") == "Ident":
                key = {"node": "Literal", "span": key["span"], "value": {"kind": "String", "value": key["name"]}}
            self._match("PUNCT", ":")
            value = self._parse_expr()
            entries.append((key, value))

            if self._check("PUNCT", ","):
                self._match("PUNCT", ",")

        self._match("PUNCT", "}")
        from voxc.ast_nodes import expr_dict
        return expr_dict(entries)

    def _parse_type(self):
        """Parse type annotation."""
        t = self._peek()
        if t.type == "NAME":
            name = self._match("NAME").value
            while self._check("OPERATOR", "."):
                self._match("OPERATOR", ".")
                name += "." + self._match("NAME").value
            if self._check("OPERATOR", "<"):
                self._match("OPERATOR", "<")
                args = [self._parse_type()]
                while self._check("PUNCT", ","):
                    self._match("PUNCT", ",")
                    args.append(self._parse_type())
                self._match("OPERATOR", ">")
                result = type_generic(name, args)
            else:
                result = type_named(name)
        elif t.type == "PUNCT" and t.value == "(":
            # Function type or tuple type
            self._match("PUNCT", "(")
            params = []
            if not self._check("PUNCT", ")"):
                params = [self._parse_type()]
                while self._check("PUNCT", ","):
                    self._match("PUNCT", ",")
                    params.append(self._parse_type())
            self._match("PUNCT", ")")

            # Check for function type arrow
            if self._check("OPERATOR", "->"):
                self._match("OPERATOR", "->")
                return_type = self._parse_type()
                from voxc.ast_nodes import type_fn
                result = type_fn(params, return_type)
            else:
                # Tuple type
                from voxc.ast_nodes import type_tuple
                result = type_tuple(params)
        elif t.type == "PUNCT" and t.value == "[":
            self._match("PUNCT", "[")
            inner = self._parse_type()
            self._match("PUNCT", "]")
            result = type_list(inner)
        elif t.type == "DICT_OPEN":
            self._match("DICT_OPEN")
            key_type = self._parse_type()
            self._match("PUNCT", ":")
            value_type = self._parse_type()
            self._match("PUNCT", "}")
            result = type_dict(key_type, value_type)
        else:
            raise SyntaxError("Expected type at line {}".format(t.line))

        # Check for Optional suffix: T? means Optional<T>
        while self._check("OPERATOR", "?") or self._check("OPERATOR", "??"):
            if self._check("OPERATOR", "??"):
                self._match("OPERATOR", "??")
            else:
                self._match("OPERATOR", "?")
            from voxc.ast_nodes import type_optional
            result = type_optional(result)

        return result


def stmt_from_import(module, items, span=None):
    from voxc.ast_nodes import Span as S
    s = span or S.unknown()
    return {"node": "FromImport", "span": s.to_json(), "module": module, "items": items}


def stmt_for_loop(var, iterable, guard, body, else_body, span=None):
    from voxc.ast_nodes import Span as S
    s = span or S.unknown()
    result = {"node": "ForLoop", "span": s.to_json(), "var": var, "iterable": iterable.to_json(),
              "guard": guard.to_json() if guard else None,
              "body": [b.to_json() if hasattr(b, 'to_json') else b for b in body]}
    if else_body:
        result["else_body"] = [b.to_json() if hasattr(b, 'to_json') else b for b in else_body]
    return result


def stmt_while_loop(condition, body, else_body, span=None):
    from voxc.ast_nodes import Span as S
    s = span or S.unknown()
    result = {"node": "WhileLoop", "span": s.to_json(), "condition": condition.to_json(),
              "body": [b.to_json() if hasattr(b, 'to_json') else b for b in body]}
    if else_body:
        result["else_body"] = [b.to_json() if hasattr(b, 'to_json') else b for b in else_body]
    return result


def stmt_loop(body, span=None):
    from voxc.ast_nodes import Span as S
    s = span or S.unknown()
    return {"node": "LoopStmt", "span": s.to_json(),
            "body": [b.to_json() if hasattr(b, 'to_json') else b for b in body]}


def expr_unary(op, operand, span=None):
    from voxc.ast_nodes import _UNOP_MAP, Span as S
    s = span or S.unknown()
    mapped_op = _UNOP_MAP.get(op, op)
    operand_json = operand.to_json() if hasattr(operand, 'to_json') else operand
    return {"node": "UnaryOp", "span": s.to_json(), "op": mapped_op, "operand": operand_json}


def expr_index(target, index, span=None):
    from voxc.ast_nodes import Span as S
    s = span or S.unknown()
    return {"node": "Index", "span": s.to_json(), "target": target.to_json(), "index": index.to_json()}


def expr_set(elements, span=None):
    from voxc.ast_nodes import Span as S
    s = span or S.unknown()
    return {"node": "SetLiteral", "span": s.to_json(), "elements": [e.to_json() for e in elements]}


def expr_dict(entries, span=None):
    from voxc.ast_nodes import Span as S
    s = span or S.unknown()
    return {"node": "DictLiteral", "span": s.to_json(),
            "entries": [(k.to_json() if hasattr(k, 'to_json') else k, v.to_json() if hasattr(v, 'to_json') else v) for (k, v) in entries]}


def expand_templates(module_dict):
    """Post-process AST: expand template invocations.

    Walks the AST dict, finds TemplateDecl nodes (removes them),
    and replaces Call nodes referencing template names with expanded bodies.
    """
    import copy

    # 1. Collect template declarations
    templates = {}
    remaining_stmts = []
    for stmt in module_dict.get("statements", []):
        if stmt.get("node") == "TemplateDecl":
            name = stmt["name"]
            params = [p["name"] for p in stmt.get("params", [])]
            templates[name] = {
                "params": params,
                "body": stmt.get("body", []),
            }
        else:
            remaining_stmts.append(stmt)

    if not templates:
        return module_dict

    module_dict["statements"] = remaining_stmts

    # 2. Walk AST and expand template calls
    _expand_ast(module_dict, templates)

    return module_dict


def _expand_ast(node, templates):
    """Recursively walk AST dict, expanding template calls."""
    import copy

    if not isinstance(node, dict):
        return node

    # Handle Call nodes that reference templates
    if node.get("node") == "Call":
        func = node.get("func", {})
        if func.get("node") == "Ident" and func.get("name") in templates:
            tmpl = templates[func["name"]]
            args = node.get("args", [])
            return _expand_template_body(tmpl, args, templates)

    # Recursively process children
    for key, value in list(node.items()):
        if isinstance(value, dict):
            node[key] = _expand_ast(value, templates)
        elif isinstance(value, list):
            # Expand and flatten: template expansion may return multiple statements
            new_list = []
            for item in value:
                if isinstance(item, dict) and item.get("node") == "Call":
                    func = item.get("func", {})
                    if func.get("node") == "Ident" and func.get("name") in templates:
                        tmpl = templates[func["name"]]
                        args = item.get("args", [])
                        result = _expand_template_body(tmpl, args, templates)
                        if isinstance(result, list):
                            new_list.extend(result)
                        else:
                            new_list.append(result)
                    else:
                        new_list.append(_expand_ast(item, templates))
                elif isinstance(item, dict):
                    new_list.append(_expand_ast(item, templates))
                else:
                    new_list.append(item)
            node[key] = new_list

    return node


def _expand_template_body(template, args, templates):
    """Expand a template body with given arguments.

    Returns a list of statement dicts (or a single expression dict).
    """
    import copy

    # Build substitution map: __param_name__ → arg AST
    subs = {}
    for i, param_name in enumerate(template["params"]):
        placeholder = "__{}__".format(param_name)
        if i < len(args):
            subs[placeholder] = args[i]

    # Deep copy the body and substitute
    body = copy.deepcopy(template["body"])

    # Check if the body is a single expression (for expression-position use)
    if len(body) == 1 and body[0].get("node") == "ExprStmt":
        expr = body[0].get("expr", {})
        result = _substitute_in_ast(expr, subs)
        return _expand_ast(result, templates)

    # Otherwise return statement list
    result = [_substitute_in_ast(s, subs) for s in body]
    return _expand_ast(result, templates)


def _substitute_in_ast(node, subs):
    """Replace __param__ placeholders in AST with actual arguments."""
    if not isinstance(node, dict):
        return node

    # Check if this is an Ident with a placeholder name
    if node.get("node") == "Ident" and node.get("name") in subs:
        return subs[node["name"]]

    # Recursively substitute
    for key, value in node.items():
        if isinstance(value, dict):
            node[key] = _substitute_in_ast(value, subs)
        elif isinstance(value, list):
            node[key] = [_substitute_in_ast(item, subs) if isinstance(item, dict) else item for item in value]
        elif isinstance(value, str) and value in subs:
            node[key] = subs[value]

    return node