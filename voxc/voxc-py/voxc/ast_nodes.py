"""AST node definitions for Vox (Python side).

Mirrors the Rust AST node types for JSON serialization compatibility.
"""

# Operator string → PascalCase mapping for Rust BinaryOperator enum
_BINOP_MAP = {
    "+": "Add",
    "-": "Sub",
    "*": "Mul",
    "/": "Div",
    "%": "Mod",
    "**": "Pow",
    "==": "Eq",
    "!=": "Ne",
    "<": "Lt",
    ">": "Gt",
    "<=": "Le",
    ">=": "Ge",
    "&&": "And",
    "||": "Or",
    "..": "Range",
    "..=": "RangeInclusive",
    "in": "In",
    "not in": "NotIn",
}

_UNOP_MAP = {
    "-": "Neg",
    "!": "Not",
}


class Span:
    """Source location span."""
    def __init__(self, file, line, col, end_line, end_col):
        self.file = file
        self.line = line
        self.col = col
        self.end_line = end_line
        self.end_col = end_col

    def to_json(self):
        return {
            "file": self.file,
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "end_col": self.end_col,
        }

    @staticmethod
    def unknown():
        return Span("<unknown>", 0, 0, 0, 0)


class Module:
    """Top-level module."""
    def __init__(self, name, statements, span=None):
        self.name = name
        self.statements = statements
        self.span = span or Span.unknown()

    def to_json(self):
        return {
            "name": self.name,
            "statements": [_to_json(s) for s in self.statements],
            "span": _to_json(self.span),
        }


class LiteralValue:
    """Literal value."""
    def __init__(self, kind, value):
        self.kind = kind
        self.value = value

    def to_json(self):
        return {"kind": self.kind, "value": self.value}


class FnParam:
    """Function parameter."""
    def __init__(self, name, type_annotation=None, default=None, variadic=False):
        self.name = name
        self.type_annotation = type_annotation
        self.default = default
        self.variadic = variadic

    def to_json(self):
        result = {"name": self.name, "variadic": self.variadic}
        if self.type_annotation:
            result["type_annotation"] = _to_json(self.type_annotation)
        if self.default:
            result["default"] = _to_json(self.default)
        return result


# ---- Statement builders ----

def stmt_vardecl(name, value, mutable=False, type_annotation=None, span=None):
    s = span or Span.unknown()
    result = {"node": "VarDecl", "span": s.to_json(), "mutable": mutable, "name": name, "value": _to_json(value)}
    if type_annotation:
        result["type_annotation"] = _to_json(type_annotation)
    return result


def stmt_constdecl(name, value, type_annotation=None, span=None):
    s = span or Span.unknown()
    result = {"node": "ConstDecl", "span": s.to_json(), "name": name, "value": _to_json(value)}
    if type_annotation:
        result["type_annotation"] = _to_json(type_annotation)
    return result


def stmt_lazy_decl(name, type_annotation, value, span=None):
    s = span or Span.unknown()
    result = {"node": "LazyDecl", "span": s.to_json(), "name": name, "value": _to_json(value)}
    if type_annotation:
        result["type_annotation"] = _to_json(type_annotation)
    return result


def stmt_fndef(name, params, body, return_type=None, generics=None, doc=None, span=None):
    s = span or Span.unknown()
    result = {
        "node": "FnDef",
        "span": s.to_json(),
        "name": name,
        "generics": generics or [],
        "params": [_to_json(p) for p in params],
        "return_type": _to_json(return_type),
        "raises": None,
        "where_clauses": [],
        "body": [_to_json(b) for b in body],
    }
    if doc is not None:
        result["doc"] = doc
    return result


def stmt_expr(expr, span=None):
    s = span or Span.unknown()
    return {"node": "ExprStmt", "span": s.to_json(), "expr": _to_json(expr)}


def stmt_return(value=None, span=None):
    s = span or Span.unknown()
    result = {"node": "ReturnStmt", "span": s.to_json()}
    if value:
        result["value"] = _to_json(value)
    return result


def stmt_if(condition, then_body, elif_chain=None, else_body=None, span=None):
    s = span or Span.unknown()
    return {
        "node": "IfStmt",
        "span": s.to_json(),
        "condition": _to_json(condition),
        "then_body": [_to_json(b) for b in then_body],
        "elif_chain": elif_chain or [],
        "else_body": [_to_json(b) for b in else_body] if else_body else None,
    }


def stmt_import(module, items=None, alias=None, span=None):
    s = span or Span.unknown()
    result = {"node": "ImportStmt", "span": s.to_json(), "module": module}
    if items:
        result["items"] = items
    if alias:
        result["alias"] = alias
    return result


def stmt_test(name, body, span=None):
    s = span or Span.unknown()
    return {"node": "TestStmt", "span": s.to_json(), "name": name, "body": [_to_json(b) for b in body]}


def stmt_suite(name, body, span=None):
    s = span or Span.unknown()
    return {"node": "SuiteStmt", "span": s.to_json(), "name": name, "body": [_to_json(b) for b in body]}


def stmt_template_decl(name, params, body, generics=None, span=None):
    s = span or Span.unknown()
    return {
        "node": "TemplateDecl",
        "span": s.to_json(),
        "name": name,
        "generics": generics or [],
        "params": [_to_json(p) for p in params],
        "body": [_to_json(b) for b in body],
    }


def expr_template_invoke(name, args, span=None):
    s = span or Span.unknown()
    return {"node": "TemplateInvoke", "span": s.to_json(), "name": name, "args": [_to_json(a) for a in args]}


def stmt_define_decl(name, props, statics, typemethods, instancemethods, generics=None, check=None, span=None):
    s = span or Span.unknown()
    return {
        "node": "DefineDecl",
        "span": s.to_json(),
        "name": name,
        "generics": generics or [],
        "constraints": {
            "props": props or [],
            "statics": statics or [],
            "typemethods": typemethods or [],
            "instancemethods": instancemethods or [],
            "check": check,
        },
    }


def stmt_operator_decl(op_type, symbol, name, params, return_type, generics=None, where_clauses=None, span=None):
    s = span or Span.unknown()
    # params may be list of tuples (name, type) or FnParam objects
    params_json = []
    for p in params:
        if hasattr(p, 'to_json'):
            pj = p.to_json()
            params_json.append([pj["name"], pj.get("type_annotation")])
        else:
            params_json.append([p[0], _to_json(p[1])])
    return {
        "node": "OperatorDecl",
        "span": s.to_json(),
        "op_type": op_type,
        "symbol": symbol,
        "name": name,
        "generics": generics or [],
        "params": params_json,
        "return_type": _to_json(return_type),
        "where_clauses": where_clauses or [],
    }


def stmt_decorated(decorators, stmt, span=None):
    s = span or Span.unknown()
    return {"node": "DecoratedStmt", "span": s.to_json(), "decorators": decorators, "stmt": _to_json(stmt)}


def stmt_struct_def(name, fields, generics=None, doc=None, span=None):
    s = span or Span.unknown()
    result = {
        "node": "StructDef", "span": s.to_json(),
        "name": name, "generics": generics or [],
        "fields": [f.to_json() if hasattr(f, 'to_json') else f for f in fields],
    }
    if doc is not None:
        result["doc"] = doc
    return result


def stmt_class_def(name, fields, methods, parent=None, doc=None, span=None):
    s = span or Span.unknown()
    result = {
        "node": "ClassDef", "span": s.to_json(),
        "name": name, "parent": parent,
        "fields": [f.to_json() if hasattr(f, 'to_json') else f for f in fields],
        "methods": [_to_json(m) for m in methods],
    }
    if doc is not None:
        result["doc"] = doc
    return result


def stmt_enum_def(name, variants, generics=None, doc=None, span=None):
    s = span or Span.unknown()
    result = {
        "node": "EnumDef", "span": s.to_json(),
        "name": name, "generics": generics or [],
        "variants": [v.to_json() if hasattr(v, 'to_json') else v for v in variants],
    }
    if doc is not None:
        result["doc"] = doc
    return result


def stmt_trait_def(name, methods, generics=None, doc=None, span=None):
    s = span or Span.unknown()
    result = {
        "node": "TraitDef", "span": s.to_json(),
        "name": name, "generics": generics or [],
        "methods": [m.to_json() if hasattr(m, 'to_json') else m for m in methods],
    }
    if doc is not None:
        result["doc"] = doc
    return result


def stmt_impl_block(type_name, methods, trait_name=None, span=None):
    s = span or Span.unknown()
    return {
        "node": "ImplBlock", "span": s.to_json(),
        "trait_name": trait_name, "type_name": type_name,
        "methods": [_to_json(m) for m in methods],
    }


def stmt_extend_decl(target, for_type, methods=None, generics=None, span=None):
    s = span or Span.unknown()
    return {
        "node": "ExtendDecl", "span": s.to_json(),
        "target": target, "for_type": for_type,
        "generics": generics or [],
        "methods": [_to_json(m) for m in methods] if methods else [],
    }


def stmt_match(expr, arms, span=None):
    s = span or Span.unknown()
    return {
        "node": "MatchStmt", "span": s.to_json(),
        "expr": _to_json(expr),
        "arms": [a.to_json() if hasattr(a, 'to_json') else a for a in arms],
    }


def stmt_comptime_block(body, span=None):
    s = span or Span.unknown()
    return {"node": "ComptimeBlock", "span": s.to_json(), "body": [_to_json(b) for b in body]}


def stmt_transtime_block(body, span=None):
    s = span or Span.unknown()
    return {"node": "TranstimeBlock", "span": s.to_json(), "body": [_to_json(b) for b in body]}


def stmt_ignore(target, name, body, span=None):
    """ignore statement — e.g. ignore test name: generates #[ignore] attribute."""
    s = span or Span.unknown()
    return {
        "node": "IgnoreStmt",
        "span": s.to_json(),
        "target": target,
        "name": name,
        "body": [_to_json(b) for b in body],
    }


def stmt_exclude(module, items, span=None):
    """exclude statement — imports everything from module EXCEPT listed items."""
    s = span or Span.unknown()
    return {
        "node": "ExcludeStmt",
        "span": s.to_json(),
        "module": module,
        "items": list(items),
    }


# ---- Struct/Enum/Class helpers ----

def struct_field(name, type_annotation, span=None):
    s = span or Span.unknown()
    return {"span": s.to_json(), "name": name, "type_annotation": _to_json(type_annotation)}


def class_field(name, type_annotation, default=None, mutable=False, span=None):
    s = span or Span.unknown()
    result = {"span": s.to_json(), "name": name, "type_annotation": _to_json(type_annotation), "mutable": mutable}
    if default is not None:
        result["default"] = _to_json(default)
    return result


def enum_variant(name, data=None, span=None):
    s = span or Span.unknown()
    result = {"span": s.to_json(), "name": name}
    if data is not None:
        result["data"] = _to_json(data)
    return result


def trait_method(name, params, return_type=None, default_body=None, span=None):
    s = span or Span.unknown()
    result = {
        "span": s.to_json(), "name": name,
        "params": [p.to_json() if hasattr(p, 'to_json') else p for p in params],
        "return_type": _to_json(return_type),
    }
    if default_body is not None:
        result["default_body"] = [_to_json(b) for b in default_body]
    return result


def match_arm(pattern, body, guard=None, span=None):
    s = span or Span.unknown()
    result = {"span": s.to_json(), "pattern": _to_json(pattern), "body": [_to_json(b) for b in body]}
    if guard is not None:
        result["guard"] = _to_json(guard)
    return result


# ---- Pattern builders ----

def pattern_ident(name, span=None):
    s = span or Span.unknown()
    return {"node": "Ident", "span": s.to_json(), "name": name}


def pattern_lit(kind, value, span=None):
    s = span or Span.unknown()
    return {"node": "Lit", "span": s.to_json(), "value": {"kind": kind, "value": value}}


def pattern_wildcard(span=None):
    s = span or Span.unknown()
    return {"node": "Wildcard", "span": s.to_json()}


def pattern_guard(pattern, condition, span=None):
    s = span or Span.unknown()
    return {"node": "Guard", "span": s.to_json(), "pattern": _to_json(pattern), "condition": _to_json(condition)}


# ---- Expression builders ----

def expr_literal(kind, value, span=None):
    s = span or Span.unknown()
    return {"node": "Literal", "span": s.to_json(), "value": {"kind": kind, "value": value}}


def expr_ident(name, span=None):
    s = span or Span.unknown()
    return {"node": "Ident", "span": s.to_json(), "name": name}


def expr_binary(left, op, right, span=None):
    s = span or Span.unknown()
    mapped_op = _BINOP_MAP.get(op, op)
    return {"node": "BinaryOp", "span": s.to_json(), "left": _to_json(left), "op": mapped_op, "right": _to_json(right)}


def expr_call(func, args, span=None):
    s = span or Span.unknown()
    return {"node": "Call", "span": s.to_json(), "func": _to_json(func), "args": [_to_json(a) for a in args]}


def expr_list(elements, span=None):
    s = span or Span.unknown()
    return {"node": "ListLiteral", "span": s.to_json(), "elements": [_to_json(e) for e in elements]}


def expr_dict(entries, span=None):
    s = span or Span.unknown()
    return {"node": "DictLiteral", "span": s.to_json(), "entries": [[_to_json(k), _to_json(v)] for k, v in entries]}


def expr_set(elements, span=None):
    s = span or Span.unknown()
    return {"node": "SetLiteral", "span": s.to_json(), "elements": [_to_json(e) for e in elements]}


def expr_tuple(elements, span=None):
    s = span or Span.unknown()
    return {"node": "TupleLiteral", "span": s.to_json(), "elements": [_to_json(e) for e in elements]}


def expr_if(condition, then_expr, else_expr, span=None):
    s = span or Span.unknown()
    return {"node": "IfExpr", "span": s.to_json(), "condition": _to_json(condition),
            "then_expr": _to_json(then_expr), "else_expr": _to_json(else_expr)}


def expr_method_call(receiver, method, args, span=None):
    s = span or Span.unknown()
    return {"node": "MethodCall", "span": s.to_json(), "receiver": _to_json(receiver),
            "method": method, "args": [_to_json(a) for a in args]}


def expr_attribute(target, name, span=None):
    s = span or Span.unknown()
    return {"node": "Attribute", "span": s.to_json(), "target": _to_json(target), "name": name}


def expr_lambda(params, body, return_type=None, span=None):
    s = span or Span.unknown()
    return {"node": "Lambda", "span": s.to_json(), "params": list(params),
            "return_type": _to_json(return_type), "body": _to_json(body)}


# ---- Type builders ----

def type_named(name, span=None):
    s = span or Span.unknown()
    return {"node": "Named", "span": s.to_json(), "name": name}


def type_optional(inner, span=None):
    s = span or Span.unknown()
    return {"node": "Optional", "span": s.to_json(), "inner": _to_json(inner)}


def type_list(inner, span=None):
    s = span or Span.unknown()
    return {"node": "List", "span": s.to_json(), "inner": _to_json(inner)}


def type_dict(key, value, span=None):
    s = span or Span.unknown()
    return {"node": "Dict", "span": s.to_json(), "key": _to_json(key), "value": _to_json(value)}


def type_generic(base, args, span=None):
    s = span or Span.unknown()
    return {"node": "Generic", "span": s.to_json(), "base": base, "args": [_to_json(a) for a in args]}


def type_fn(params, return_type, span=None):
    s = span or Span.unknown()
    return {"node": "FnType", "span": s.to_json(), "params": [_to_json(p) for p in params], "return_type": _to_json(return_type)}


def type_tuple(types, span=None):
    s = span or Span.unknown()
    return {"node": "Tuple", "span": s.to_json(), "types": [_to_json(t) for t in types]}


# ---- Conversion helper ----

def _to_json(obj):
    """Convert an object to JSON dict, handling both dicts and objects with to_json()."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, 'to_json'):
        return obj.to_json()
    return obj


def ast_to_json(module):
    """Convert a Module to JSON-serializable dict."""
    if isinstance(module, Module):
        return module.to_json()
    if hasattr(module, 'to_json'):
        return module.to_json()
    return module