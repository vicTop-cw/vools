"""Lark-based Vox parser with fallback to existing VoxParser.

Provides a parse_source() function that returns JSON-serializable AST dicts
compatible with voxc.ast_nodes format.

When lark library is available, provides an experimental Lark-based parser.
When unavailable, falls back to the existing VoxParser implementation.
"""

import os
import sys

_LARK_AVAILABLE = False
try:
    from lark import Lark, Transformer, v_args
    from lark.indenter import Indenter
    _LARK_AVAILABLE = True
except ImportError:
    pass


def is_available():
    """Return True if the lark library is available."""
    return _LARK_AVAILABLE


def _make_span(filename, line, col, end_line, end_col):
    return {
        "file": filename,
        "line": line,
        "col": col,
        "end_line": end_line,
        "end_col": end_col,
    }


def _unknown_span(filename="<unknown>"):
    return _make_span(filename, 0, 0, 0, 0)


def parse_source(source, filename="<string>"):
    """Parse Vox source code and return AST dict (JSON-serializable).

    Returns AST compatible with voxc.ast_nodes format.
    Uses the existing VoxParser for reliable parsing.
    When lark is available, also provides experimental_lark_parse().
    """
    from voxc.lexer import VoxLexer
    from voxc.parser import VoxParser
    from voxc.ast_nodes import ast_to_json

    lexer = VoxLexer()
    tokens = lexer.tokenize(source)
    parser = VoxParser()
    module = parser.parse(tokens, filename)
    return ast_to_json(module)


if _LARK_AVAILABLE:

    _EXPERIMENTAL_GRAMMAR = r"""
        %import common.CNAME -> NAME
        %import common.NUMBER
        %import common.WS_INLINE
        %import common.SH_COMMENT
        %import common.C_COMMENT

        %ignore WS_INLINE
        %ignore SH_COMMENT
        %ignore C_COMMENT

        start: (_NL | statement)*

        ?statement: var_decl
                  | const_decl
                  | fn_def
                  | if_stmt
                  | for_loop
                  | while_loop
                  | loop_stmt
                  | struct_def
                  | class_def
                  | enum_def
                  | trait_def
                  | import_stmt
                  | from_import
                  | return_stmt
                  | expr_stmt
                  | doc_comment

        doc_comment: DOC_COMMENT

        var_decl: ("val" | "var" | "let") NAME (":" type_expr)? "=" expr
        const_decl: "const" NAME (":" type_expr)? "=" expr

        fn_def: "def" NAME ("<" generic_params ">")? "(" fn_params? ")" ("->" type_expr)? ":" _NL suite
        generic_params: NAME ("," NAME)*
        fn_params: fn_param ("," fn_param)*
        fn_param: "*"? NAME (":" type_expr)? ("=" expr)?

        if_stmt: "if" expr ":" _NL suite elif_chain? else_clause?
        elif_chain: ("elif" expr ":" _NL suite)+
        else_clause: "else" ":" _NL suite

        for_loop: "for" NAME "in" expr ("if" expr)? ":" _NL suite
        while_loop: "while" expr ":" _NL suite
        loop_stmt: "loop" ":" _NL suite

        struct_def: "struct" NAME ("<" generic_params ">")? ":" _NL suite
        struct_field: NAME ":" type_expr

        class_def: "class" NAME ("(" NAME ")")? ":" _NL suite

        enum_def: "enum" NAME ("<" generic_params ">")? ":" _NL suite
        enum_variant: NAME ("(" type_expr ")")?

        trait_def: "trait" NAME ("<" generic_params ">")? ":" _NL suite
        trait_method: "def" NAME "(" fn_params? ")" ("->" type_expr)? (":" _NL suite)?

        import_stmt: "import" dotted_name ("::" "{" import_items "}")? ("as" NAME)?
        from_import: "from" dotted_name "import" import_items
        import_items: NAME ("," NAME)*
        dotted_name: NAME ("." NAME)*

        return_stmt: "return" expr?

        expr_stmt: expr

        suite: _INDENT (statement | _NL)* _DEDENT

        ?expr: comparison

        ?comparison: additive (comp_op additive)*
        comp_op: "==" | "!=" | "<=" | ">=" | "<" | ">" | "in" | "not" "in"

        ?additive: multiplicative (add_op multiplicative)*
        add_op: "+" | "-"

        ?multiplicative: unary (mul_op unary)*
        mul_op: "*" | "/" | "%" | "**"

        ?unary: ("-" | "!") unary
              | call_expr

        ?call_expr: primary ("(" args? ")")* ("." NAME ("(" args? ")")?)*
        args: expr ("," expr)*

        ?primary: NUMBER
                | STRING
                | NAME
                | "true"
                | "false"
                | "none"
                | "(" expr ")"
                | "[" args? "]"
                | "{" args? "}"
                | "{:" dict_entries? "}"

        dict_entries: dict_entry ("," dict_entry)*
        dict_entry: expr ":" expr

        ?type_expr: type_primary ("<" type_args ">")?
        type_args: type_expr ("," type_expr)*
        ?type_primary: NAME ("." NAME)*
                     | "(" (type_expr ("," type_expr)*)? ")" ("->" type_expr)?
                     | "[" type_expr "]"
                     | "{:" type_expr ":" type_expr "}"

        STRING: /"[^"\\]*(\\.[^"\\]*)*"|'[^'\\]*(\\.[^'\\]*)*'/
        DOC_COMMENT: "///" /[^\n]*/

        _NL: /(\n|\r\n)+/
        _INDENT: "<INDENT>"
        _DEDENT: "<DEDENT>"
    """

    class VoxIndenter(Indenter):
        NL_type = '_NL'
        OPEN_PAREN_types = []
        CLOSE_PAREN_types = []
        INDENT_type = '_INDENT'
        DEDENT_type = '_DEDENT'
        tab_len = 4

    @v_args(inline=True)
    class VoxASTTransformer(Transformer):
        """Transform Lark parse tree into Vox AST dict format (experimental)."""

        def __init__(self, filename="<string>"):
            super().__init__()
            self.filename = filename

        def _span(self, token):
            if hasattr(token, "line"):
                end_line = getattr(token, "end_line", token.line)
                end_col = getattr(token, "end_column", token.column)
                return _make_span(
                    self.filename,
                    token.line,
                    token.column,
                    end_line,
                    end_col,
                )
            return _unknown_span(self.filename)

        def start(self, *items):
            stmts = [i for i in items if i is not None and not isinstance(i, str)]
            return {
                "name": os.path.splitext(os.path.basename(self.filename))[0],
                "statements": stmts,
                "span": _unknown_span(self.filename),
            }

        def statement(self, item):
            return item

        def doc_comment(self, doc):
            return None

        def var_decl(self, kw, name, type_ann, value):
            span = self._span(name)
            mutable = str(kw) == "var"
            result = {
                "node": "VarDecl",
                "span": span,
                "mutable": mutable,
                "name": str(name),
                "value": value,
            }
            if type_ann is not None:
                result["type_annotation"] = type_ann
            return result

        def const_decl(self, name, type_ann, value):
            span = self._span(name)
            result = {
                "node": "ConstDecl",
                "span": span,
                "name": str(name),
                "value": value,
            }
            if type_ann is not None:
                result["type_annotation"] = type_ann
            return result

        def fn_def(self, name, generics, params, return_type, body):
            span = self._span(name)
            return {
                "node": "FnDef",
                "span": span,
                "name": str(name),
                "generics": generics or [],
                "params": params or [],
                "return_type": return_type,
                "raises": None,
                "where_clauses": [],
                "body": body or [],
            }

        def generic_params(self, *names):
            return [{"name": str(n), "bounds": []} for n in names]

        def fn_params(self, *params):
            return list(params)

        def fn_param(self, *args):
            variadic = False
            idx = 0
            if args and str(args[0]) == "*":
                variadic = True
                idx = 1
            name = str(args[idx])
            idx += 1
            type_ann = None
            default = None
            if idx < len(args):
                arg = args[idx]
                if isinstance(arg, dict) and arg.get("node") in ("Named", "Generic", "List", "Dict", "Tuple", "FnType", "Optional"):
                    type_ann = arg
                    idx += 1
            if idx < len(args):
                default = args[idx]
            result = {"name": name, "variadic": variadic}
            if type_ann:
                result["type_annotation"] = type_ann
            if default is not None:
                result["default"] = default
            return result

        def if_stmt(self, condition, then_body, elif_chain, else_body):
            span = then_body[0]["span"] if then_body else _unknown_span(self.filename)
            elif_list = elif_chain if elif_chain else []
            return {
                "node": "IfStmt",
                "span": span,
                "condition": condition,
                "then_body": then_body or [],
                "elif_chain": elif_list,
                "else_body": else_body,
            }

        def elif_chain(self, *items):
            result = []
            i = 0
            while i < len(items):
                cond = items[i]
                body = items[i + 1]
                result.append((cond, body))
                i += 2
            return result

        def else_clause(self, body):
            return body

        def for_loop(self, var, iterable, guard, body):
            span = self._span(var)
            return {
                "node": "ForLoop",
                "span": span,
                "var": str(var),
                "iterable": iterable,
                "guard": guard,
                "body": body or [],
                "else_body": None,
            }

        def while_loop(self, condition, body):
            span = condition["span"] if isinstance(condition, dict) else _unknown_span(self.filename)
            return {
                "node": "WhileLoop",
                "span": span,
                "condition": condition,
                "body": body or [],
                "else_body": None,
            }

        def loop_stmt(self, body):
            span = _unknown_span(self.filename)
            return {
                "node": "Loop",
                "span": span,
                "body": body or [],
            }

        def struct_def(self, name, generics, fields):
            span = self._span(name)
            field_list = []
            for f in fields or []:
                if f and isinstance(f, dict) and "name" in f and "type_annotation" in f and "node" not in f:
                    field_list.append(f)
            return {
                "node": "StructDef",
                "span": span,
                "name": str(name),
                "generics": generics or [],
                "fields": field_list,
            }

        def struct_field(self, name, type_expr):
            span = self._span(name)
            return {
                "span": span,
                "name": str(name),
                "type_annotation": type_expr,
            }

        def class_def(self, name, parent, body):
            span = self._span(name)
            fields = []
            methods = []
            for item in body or []:
                if item and isinstance(item, dict):
                    if item.get("node") == "FnDef":
                        methods.append(item)
                    elif "name" in item and "type_annotation" in item and "node" not in item:
                        fields.append(item)
            return {
                "node": "ClassDef",
                "span": span,
                "name": str(name),
                "parent": parent,
                "fields": fields,
                "methods": methods,
            }

        def enum_def(self, name, generics, variants):
            span = self._span(name)
            variant_list = []
            for v in variants or []:
                if v and isinstance(v, dict) and "name" in v and "node" not in v:
                    variant_list.append(v)
            return {
                "node": "EnumDef",
                "span": span,
                "name": str(name),
                "generics": generics or [],
                "variants": variant_list,
            }

        def enum_variant(self, name, data=None):
            span = self._span(name)
            result = {"span": span, "name": str(name)}
            if data is not None:
                result["data"] = data
            return result

        def trait_def(self, name, generics, methods):
            span = self._span(name)
            method_list = []
            for m in methods or []:
                if m and isinstance(m, dict) and "name" in m and "params" in m and "node" not in m:
                    method_list.append(m)
            return {
                "node": "TraitDef",
                "span": span,
                "name": str(name),
                "generics": generics or [],
                "methods": method_list,
            }

        def trait_method(self, name, params, return_type, default_body):
            span = self._span(name)
            return {
                "span": span,
                "name": str(name),
                "params": params or [],
                "return_type": return_type,
                "default_body": default_body,
            }

        def import_stmt(self, module_parts, items, alias):
            span = _unknown_span(self.filename)
            module_list = module_parts if isinstance(module_parts, list) else [module_parts]
            result = {"node": "ImportStmt", "span": span, "module": module_list}
            if items:
                result["items"] = items
            if alias:
                result["alias"] = alias
            return result

        def from_import(self, module_parts, items):
            span = _unknown_span(self.filename)
            module_list = module_parts if isinstance(module_parts, list) else [module_parts]
            return {
                "node": "FromImport",
                "span": span,
                "module": module_list,
                "items": items,
            }

        def import_items(self, *items):
            return [str(i) for i in items]

        def dotted_name(self, *parts):
            return [str(p) for p in parts]

        def return_stmt(self, value=None):
            span = _unknown_span(self.filename)
            result = {"node": "ReturnStmt", "span": span}
            if value is not None:
                result["value"] = value
            return result

        def expr_stmt(self, expr):
            span = expr["span"] if isinstance(expr, dict) else _unknown_span(self.filename)
            return {"node": "ExprStmt", "span": span, "expr": expr}

        def suite(self, *stmts):
            return [s for s in stmts if s is not None and not isinstance(s, str)]

        def expr(self, e):
            return e

        def comparison(self, left, *rest):
            return self._binop(left, rest)

        def additive(self, left, *rest):
            return self._binop(left, rest)

        def multiplicative(self, left, *rest):
            return self._binop(left, rest)

        def _binop(self, left, rest):
            result = left
            i = 0
            while i < len(rest):
                op = str(rest[i])
                if op == "not" and i + 1 < len(rest) and str(rest[i + 1]) == "in":
                    op = "not in"
                    i += 1
                right = rest[i + 1]
                span = _unknown_span(self.filename)
                op_map = {
                    "+": "Add", "-": "Sub", "*": "Mul", "/": "Div", "%": "Mod", "**": "Pow",
                    "==": "Eq", "!=": "Ne", "<": "Lt", ">": "Gt", "<=": "Le", ">=": "Ge",
                    "&&": "And", "||": "Or", "..": "Range", "..=": "RangeInclusive",
                    "in": "In", "not in": "NotIn",
                }
                mapped_op = op_map.get(op, op)
                result = {"node": "BinaryOp", "span": span, "left": result, "op": mapped_op, "right": right}
                i += 2
            return result

        def unary(self, *args):
            if len(args) == 2:
                op = str(args[0])
                operand = args[1]
                span = _unknown_span(self.filename)
                unop_map = {"-": "Neg", "!": "Not"}
                mapped_op = unop_map.get(op, op)
                return {"node": "UnaryOp", "span": span, "op": mapped_op, "operand": operand}
            return args[0]

        def call_expr(self, primary, *rest):
            result = primary
            i = 0
            while i < len(rest):
                item = rest[i]
                if isinstance(item, list):
                    span = _unknown_span(self.filename)
                    result = {"node": "Call", "span": span, "func": result, "args": item}
                elif isinstance(item, tuple):
                    name, args = item
                    span = _unknown_span(self.filename)
                    if args is None:
                        result = {"node": "Attribute", "span": span, "target": result, "name": name}
                    else:
                        result = {"node": "MethodCall", "span": span, "receiver": result, "method": name, "args": args}
                i += 1
            return result

        def args(self, *exprs):
            return list(exprs)

        def primary(self, item):
            span = _unknown_span(self.filename)
            if hasattr(item, "type"):
                if item.type == "NUMBER":
                    val = str(item)
                    if "." in val:
                        return {"node": "Literal", "span": span, "value": {"kind": "Float", "value": float(val)}}
                    return {"node": "Literal", "span": span, "value": {"kind": "Int", "value": int(val)}}
                if item.type == "STRING":
                    s = str(item)
                    if len(s) >= 2 and s[0] in ('"', "'") and s[-1] == s[0]:
                        s = s[1:-1]
                    return {"node": "Literal", "span": span, "value": {"kind": "String", "value": s}}
                if item.type == "NAME":
                    return {"node": "Ident", "span": span, "name": str(item)}
            if isinstance(item, str):
                if item == "true":
                    return {"node": "Literal", "span": span, "value": {"kind": "Bool", "value": True}}
                if item == "false":
                    return {"node": "Literal", "span": span, "value": {"kind": "Bool", "value": False}}
                if item == "none":
                    return {"node": "Literal", "span": span, "value": {"kind": "None", "value": None}}
            return item

        def dict_entries(self, *entries):
            return list(entries)

        def dict_entry(self, key, value):
            return (key, value)

        def type_expr(self, base, args=None):
            if args:
                span = _unknown_span(self.filename)
                base_name = base if isinstance(base, str) else base.get("name", "")
                return {"node": "Generic", "span": span, "base": base_name, "args": args}
            return base

        def type_args(self, *args):
            return list(args)

        def type_primary(self, *args):
            span = _unknown_span(self.filename)
            if len(args) == 1 and isinstance(args[0], str):
                return {"node": "Named", "span": span, "name": str(args[0])}
            if len(args) > 1 and all(isinstance(a, str) for a in args):
                return {"node": "Named", "span": span, "name": ".".join(str(a) for a in args)}
            return {"node": "Named", "span": span, "name": str(args[0]) if args else ""}

    _experimental_parser_cache = None

    def _get_experimental_parser():
        global _experimental_parser_cache
        if _experimental_parser_cache is None:
            _experimental_parser_cache = Lark(
                _EXPERIMENTAL_GRAMMAR,
                start="start",
                parser="earley",
                postlex=VoxIndenter(),
                propagate_positions=True,
                ambiguity="explicit",
            )
        return _experimental_parser_cache

    def experimental_lark_parse(source, filename="<string>"):
        """Experimental Lark-based parser (may not handle all syntax correctly).

        For production use, use parse_source() instead.
        """
        parser = _get_experimental_parser()
        tree = parser.parse(source)
        transformer = VoxASTTransformer(filename)
        ast = transformer.transform(tree)
        return ast
