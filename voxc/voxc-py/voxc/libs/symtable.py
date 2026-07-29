"""Symbol table for the Vox compiler.

Tracks variable / function / type definitions across lexical scopes,
supports self-reference detection for automatic Box wrapping, generic
type parameters, and import module registration.

Python 3.6+ compatible.  Uses string constants for SymbolKind so the
table is trivially JSON-serializable.
"""


# ---------------------------------------------------------------------------
# SymbolKind — string constants (Enum-like, 3.6 friendly)
# ---------------------------------------------------------------------------

class SymbolKind(object):
    """String constants identifying the kind of a Symbol."""
    VARIABLE = "VARIABLE"
    FUNCTION = "FUNCTION"
    STRUCT = "STRUCT"
    ENUM = "ENUM"
    CLASS = "CLASS"
    TRAIT = "TRAIT"
    TYPE_ALIAS = "TYPE_ALIAS"
    GENERIC_PARAM = "GENERIC_PARAM"
    MODULE = "MODULE"
    IMPORT = "IMPORT"


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class VoxSemanticError(Exception):
    """Raised on semantic errors: duplicate definitions, undefined
    references, illegal scope operations, etc."""
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _type_to_dict(t):
    """Coerce a type annotation to a JSON-friendly form."""
    if t is None:
        return None
    if isinstance(t, dict):
        return t
    if hasattr(t, "to_json"):
        return t.to_json()
    if hasattr(t, "to_dict"):
        return t.to_dict()
    return t


def _span_to_dict(span):
    """Coerce a span to a JSON-friendly form (mirrors ast_nodes.Span)."""
    if span is None:
        return None
    if hasattr(span, "to_json"):
        return span.to_json()
    if hasattr(span, "to_dict"):
        return span.to_dict()
    return span


def _extract_type_names(type_annotation):
    """Walk a type annotation and collect all referenced type names.

    Handles plain strings (e.g. ``"Node?"``, ``"List<Node>"``) and the
    dict form produced by ``voxc.ast_nodes`` type builders
    (``type_named``, ``type_optional``, ``type_generic``, ...).
    """
    names = []
    if type_annotation is None:
        return names
    t = _type_to_dict(type_annotation)
    if isinstance(t, str):
        names.append(t)
        return names
    if not isinstance(t, dict):
        return names
    node = t.get("node")
    if node == "Named":
        if "name" in t:
            names.append(t["name"])
    elif node == "Optional":
        names.extend(_extract_type_names(t.get("inner")))
    elif node == "List":
        names.extend(_extract_type_names(t.get("inner")))
    elif node == "Generic":
        if "base" in t:
            names.append(t["base"])
        for arg in t.get("args", []) or []:
            names.extend(_extract_type_names(arg))
    elif node == "Dict":
        names.extend(_extract_type_names(t.get("key")))
        names.extend(_extract_type_names(t.get("value")))
    elif node == "Tuple":
        for ty in t.get("types", []) or []:
            names.extend(_extract_type_names(ty))
    elif node == "FnType":
        for p in t.get("params", []) or []:
            names.extend(_extract_type_names(p))
        names.extend(_extract_type_names(t.get("return_type")))
    else:
        # Fallback: recursively harvest any uppercased string value or
        # any nested dict that looks like a type.
        for v in t.values():
            if isinstance(v, str) and v and v[0].isupper():
                names.append(v)
            elif isinstance(v, dict):
                names.extend(_extract_type_names(v))
    return names


def _unpack_field(field):
    """Extract ``(name, type_annotation)`` from a field representation.

    Accepts:
      * dict with ``name`` / ``type_annotation`` keys (ast_nodes form)
      * ``(name, type)`` tuple/list
      * objects exposing ``.name`` and ``.type_annotation``
    """
    if field is None:
        return None, None
    if isinstance(field, dict):
        return field.get("name"), field.get("type_annotation")
    if isinstance(field, (tuple, list)):
        if len(field) >= 2:
            return field[0], field[1]
        if len(field) == 1:
            return field[0], None
        return None, None
    if hasattr(field, "name") and hasattr(field, "type_annotation"):
        return field.name, field.type_annotation
    return None, None


# ---------------------------------------------------------------------------
# Symbol
# ---------------------------------------------------------------------------

class Symbol(object):
    """A single named entry in the symbol table."""

    def __init__(self, name, kind, type_annotation=None, span=None,
                 mutable=False, is_public=False, is_owned=False, attributes=None):
        self.name = name
        self.kind = kind
        self.type_annotation = type_annotation
        self.span = span
        self.mutable = mutable
        self.is_public = is_public
        self.is_owned = is_owned
        self.attributes = dict(attributes) if attributes else {}

    def to_dict(self):
        return {
            "name": self.name,
            "kind": self.kind,
            "type_annotation": _type_to_dict(self.type_annotation),
            "span": _span_to_dict(self.span),
            "mutable": self.mutable,
            "is_public": self.is_public,
            "is_owned": self.is_owned,
            "attributes": dict(self.attributes),
        }

    @staticmethod
    def from_dict(d):
        if d is None:
            return None
        return Symbol(
            name=d.get("name"),
            kind=d.get("kind"),
            type_annotation=d.get("type_annotation"),
            span=d.get("span"),
            mutable=d.get("mutable", False),
            is_public=d.get("is_public", False),
            is_owned=d.get("is_owned", False),
            attributes=d.get("attributes", {}) or {},
        )

    def __repr__(self):
        return "Symbol(name={!r}, kind={!r}, type={!r})".format(
            self.name, self.kind, self.type_annotation)


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

class Scope(object):
    """A lexical scope. Forms a tree rooted at the global scope."""

    def __init__(self, name, parent=None, scope_level=0):
        self.name = name
        self.parent = parent
        self.children = []
        self.symbols = {}
        self.scope_level = scope_level

    def define(self, name, kind, **kwargs):
        """Define a new symbol in this scope. Raises VoxSemanticError if
        a symbol with the same name already exists locally."""
        if name in self.symbols:
            existing = self.symbols[name]
            raise VoxSemanticError(
                "duplicate definition of '{}' in scope '{}' "
                "(existing kind: {})".format(name, self.name, existing.kind)
            )
        sym = Symbol(name, kind, **kwargs)
        self.symbols[name] = sym
        return sym

    def lookup(self, name):
        """Walk up the scope chain and return the first matching Symbol,
        or None."""
        if name in self.symbols:
            return self.symbols[name]
        if self.parent is not None:
            return self.parent.lookup(name)
        return None

    def lookup_local(self, name):
        """Return the Symbol if defined in this scope only, else None."""
        return self.symbols.get(name)

    def enter_scope(self, name=""):
        """Create, attach, and return a child scope."""
        child = Scope(name, parent=self, scope_level=self.scope_level + 1)
        self.children.append(child)
        return child

    def exit_scope(self):
        """Return the parent scope (does not mutate the tree)."""
        return self.parent

    def all_symbols(self):
        """Return all Symbols defined directly in this scope."""
        return list(self.symbols.values())

    def all_scopes(self):
        """Depth-first traversal of this scope and all descendants."""
        result = [self]
        for child in self.children:
            result.extend(child.all_scopes())
        return result

    def to_dict(self):
        return {
            "name": self.name,
            "scope_level": self.scope_level,
            "symbols": {n: s.to_dict() for n, s in self.symbols.items()},
            "children": [c.to_dict() for c in self.children],
        }

    def __repr__(self):
        return "Scope(name={!r}, level={}, symbols={})".format(
            self.name, self.scope_level, len(self.symbols))


# ---------------------------------------------------------------------------
# SymbolTable — main entry point
# ---------------------------------------------------------------------------

class SymbolTable(object):
    """Top-level symbol table manager with built-in type registration,
    self-reference detection, and smart-pointer hint mapping."""

    # decorator -> Rust smart pointer string
    _SMART_PTR_MAP = {
        None: "Box",
        "@default": "Box",
        "@arc": "Arc<Mutex>",
        "@rc": "Rc<RefCell>",
        "@raw": "*mut",
    }

    def __init__(self):
        self.global_scope = Scope("global", parent=None, scope_level=0)
        self.current_scope = self.global_scope
        self._register_builtins()

    # ---- builtin registration -------------------------------------------

    def _register_builtins(self):
        # Primitive types
        for tname in ("int", "float", "string", "bool", "void", "none"):
            self.global_scope.define(
                tname, SymbolKind.TYPE_ALIAS,
                type_annotation=tname, is_public=True,
            )
        # Boolean literal constants
        for lname in ("true", "false"):
            self.global_scope.define(
                lname, SymbolKind.VARIABLE,
                type_annotation="bool", is_public=True,
            )
        # Generic type constructors
        for ctor in ("Option", "Result", "List", "Dict", "Tuple",
                     "Vec", "HashMap", "HashSet"):
            self.global_scope.define(
                ctor, SymbolKind.TYPE_ALIAS,
                type_annotation=ctor, is_public=True,
            )

    # ---- core pass-through API ------------------------------------------

    def define(self, name, kind, **kwargs):
        """Define a symbol in the current scope."""
        return self.current_scope.define(name, kind, **kwargs)

    def lookup(self, name):
        """Look up a symbol from the current scope upward."""
        return self.current_scope.lookup(name)

    def lookup_local(self, name):
        """Look up a symbol only in the current scope."""
        return self.current_scope.lookup_local(name)

    def push_scope(self, name=""):
        """Enter a new child scope and make it the current scope."""
        self.current_scope = self.current_scope.enter_scope(name)
        return self.current_scope

    def pop_scope(self):
        """Exit the current scope, returning to its parent."""
        if self.current_scope.parent is None:
            raise VoxSemanticError("cannot pop the global scope")
        prev = self.current_scope
        self.current_scope = self.current_scope.parent
        return prev

    # ---- module / import registration -----------------------------------

    def register_module(self, name, symbols):
        """Register an imported module and its exported symbols.

        A MODULE symbol is defined in the current scope; the module's
        symbols are normalized and stored on the module Symbol's
        ``attributes['imported_symbols']`` list (as dicts).

        ``symbols`` may be:
          * a list of Symbol objects
          * a list of dicts (Symbol.to_dict form)
          * a dict mapping name -> Symbol
          * None / empty
        """
        normalized = []
        if isinstance(symbols, dict):
            iterable = symbols.values()
        else:
            iterable = symbols or []
        for s in iterable:
            if isinstance(s, Symbol):
                normalized.append(s)
            elif isinstance(s, dict):
                normalized.append(Symbol.from_dict(s))
        return self.current_scope.define(
            name, SymbolKind.MODULE,
            type_annotation="module",
            is_public=True,
            attributes={
                "imported_symbols": [s.to_dict() for s in normalized],
                "import_count": len(normalized),
            },
        )

    # ---- self-reference detection ---------------------------------------

    def check_self_reference(self, struct_name, fields):
        """Return the list of field names whose type annotation
        references ``struct_name`` (directly or via wrapper types such
        as Optional/List/Generic)."""
        self_refs = []
        for field in fields or []:
            fname, ftype = _unpack_field(field)
            if fname is None:
                continue
            referenced = _extract_type_names(ftype)
            matched = False
            for ref in referenced:
                if ref == struct_name:
                    matched = True
                    break
                # Substring match handles string-form types like
                # "Node?", "List<Node>", "Option<Node>".
                if isinstance(ref, str) and struct_name in ref:
                    matched = True
                    break
            if matched:
                self_refs.append(fname)
        return self_refs

    # ---- smart pointer hints --------------------------------------------

    def get_smart_pointer_hint(self, field_name, decorator):
        """Map a Vox decorator to the Rust smart-pointer type that
        should wrap a self-referential field.

        - None / "@default" -> "Box"
        - "@arc"             -> "Arc<Mutex>"
        - "@rc"              -> "Rc<RefCell>"
        - "@raw"             -> "*mut"

        Unknown decorators fall back to "Box".
        """
        key = decorator
        if isinstance(key, str):
            key = key.strip()
        return self._SMART_PTR_MAP.get(key, "Box")

    # ---- serialization --------------------------------------------------

    def to_dict(self):
        return {
            "global_scope": self.global_scope.to_dict(),
            "current_scope_path": self._scope_path(self.current_scope),
        }

    def _scope_path(self, scope):
        path = []
        s = scope
        while s is not None:
            path.append(s.name)
            s = s.parent
        path.reverse()
        return path

    # ---- pretty printing ------------------------------------------------

    def __repr__(self):
        lines = []
        self._render_scope(self.global_scope, lines, 0)
        return "\n".join(lines)

    def _render_scope(self, scope, lines, depth):
        indent = "  " * depth
        lines.append("{}scope '{}' (level={}):".format(
            indent, scope.name, scope.scope_level))
        for sym in scope.symbols.values():
            lines.append("{}  - {}".format(indent, sym))
        for child in scope.children:
            self._render_scope(child, lines, depth + 1)
