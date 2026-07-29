"""Tests for the Vox symbol table.

Run with:
    cd e:\\IDEProjects\\AI\\vools\\voxc\\voxc-py
    python tests_vox/test_symtable.py
"""

import os
import sys
import traceback

# Allow running as a standalone script by adding the project root
# (the directory containing the `voxc` package) to sys.path.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from voxc.libs.symtable import (  # noqa: E402
    SymbolTable, Symbol, Scope, SymbolKind, VoxSemanticError,
)
from voxc.ast_nodes import type_optional, type_named  # noqa: E402


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_basic_define_lookup():
    st = SymbolTable()
    st.define("x", SymbolKind.VARIABLE, type_annotation="int")
    sym = st.lookup("x")
    assert sym is not None, "expected to find x"
    assert sym.name == "x"
    assert sym.kind == SymbolKind.VARIABLE
    assert sym.type_annotation == "int"
    # Unregistered symbol -> None
    assert st.lookup("does_not_exist") is None
    print("test_basic_define_lookup: OK")


def test_nested_scope_inner_sees_outer():
    st = SymbolTable()
    st.define("outer", SymbolKind.VARIABLE, type_annotation="int")
    st.push_scope("function_body")
    st.define("inner", SymbolKind.VARIABLE, type_annotation="string")

    # Inside inner scope: both visible
    assert st.lookup("inner") is not None
    assert st.lookup("outer") is not None

    st.pop_scope()

    # Back at outer: inner is no longer reachable
    assert st.lookup("inner") is None, "outer scope should not see inner"
    assert st.lookup("outer") is not None
    print("test_nested_scope_inner_sees_outer: OK")


def test_duplicate_definition_raises():
    st = SymbolTable()
    st.define("x", SymbolKind.VARIABLE, type_annotation="int")
    try:
        st.define("x", SymbolKind.VARIABLE, type_annotation="int")
    except VoxSemanticError:
        print("test_duplicate_definition_raises: OK")
        return
    raise AssertionError("expected VoxSemanticError on duplicate definition")


def test_duplicate_in_different_scopes_allowed():
    st = SymbolTable()
    st.define("x", SymbolKind.VARIABLE, type_annotation="int")
    st.push_scope("inner")
    # Shadowing in inner scope is legal
    st.define("x", SymbolKind.VARIABLE, type_annotation="string")
    sym = st.lookup("x")
    assert sym is not None
    assert sym.type_annotation == "string"
    st.pop_scope()
    sym = st.lookup("x")
    assert sym.type_annotation == "int"
    print("test_duplicate_in_different_scopes_allowed: OK")


def test_self_reference_detection_optional_dict():
    st = SymbolTable()
    # struct Node { value: int, next: Node? }
    # Build the Optional[Node] type using ast_nodes helpers to ensure
    # the dict form ({"node": "Optional", "inner": {"node": "Named", "name": "Node"}}) is recognised.
    fields = [
        {"name": "value", "type_annotation": "int"},
        {"name": "next", "type_annotation": type_optional(type_named("Node"))},
    ]
    self_refs = st.check_self_reference("Node", fields)
    assert "next" in self_refs, "expected next to be detected as self-referential, got {}".format(self_refs)
    assert "value" not in self_refs
    print("test_self_reference_detection_optional_dict: OK -> {}".format(self_refs))


def test_self_reference_string_form():
    st = SymbolTable()
    # string form: "Node?" or "List<Node>"
    fields = [("next", "Node?"), ("children", "List<Node>")]
    self_refs = st.check_self_reference("Node", fields)
    assert "next" in self_refs
    assert "children" in self_refs
    print("test_self_reference_string_form: OK -> {}".format(self_refs))


def test_self_reference_no_false_positive():
    st = SymbolTable()
    fields = [
        {"name": "a", "type_annotation": "int"},
        {"name": "b", "type_annotation": type_optional(type_named("Other"))},
    ]
    self_refs = st.check_self_reference("Node", fields)
    assert self_refs == [], "expected no self-references, got {}".format(self_refs)
    print("test_self_reference_no_false_positive: OK")


def test_smart_pointer_mapping():
    st = SymbolTable()
    assert st.get_smart_pointer_hint("field", None) == "Box"
    assert st.get_smart_pointer_hint("field", "@default") == "Box"
    assert st.get_smart_pointer_hint("field", "@arc") == "Arc<Mutex>"
    assert st.get_smart_pointer_hint("field", "@rc") == "Rc<RefCell>"
    assert st.get_smart_pointer_hint("field", "@raw") == "*mut"
    # Unknown -> default Box
    assert st.get_smart_pointer_hint("field", "@unknown") == "Box"
    print("test_smart_pointer_mapping: OK")


def test_module_registration():
    st = SymbolTable()
    mod_symbols = [
        Symbol("foo", SymbolKind.FUNCTION, type_annotation="fn() -> int"),
        Symbol("Bar", SymbolKind.STRUCT, type_annotation="Bar"),
    ]
    st.register_module("utils", mod_symbols)
    sym = st.lookup("utils")
    assert sym is not None, "module 'utils' should be registered"
    assert sym.kind == SymbolKind.MODULE
    assert sym.type_annotation == "module"
    imported = sym.attributes.get("imported_symbols")
    assert isinstance(imported, list)
    assert len(imported) == 2
    names = sorted(s["name"] for s in imported)
    assert names == ["Bar", "foo"], names
    print("test_module_registration: OK")


def test_module_registration_accepts_dicts():
    st = SymbolTable()
    mod_symbols = [
        {"name": "baz", "kind": SymbolKind.VARIABLE, "type_annotation": "int"},
    ]
    st.register_module("m", mod_symbols)
    sym = st.lookup("m")
    assert sym is not None
    assert sym.attributes["import_count"] == 1
    print("test_module_registration_accepts_dicts: OK")


def test_to_dict_serialization():
    st = SymbolTable()
    st.define("x", SymbolKind.VARIABLE, type_annotation="int", mutable=True)
    d = st.to_dict()
    assert "global_scope" in d
    gs = d["global_scope"]
    assert "symbols" in gs
    assert "x" in gs["symbols"]
    x_dict = gs["symbols"]["x"]
    assert x_dict["kind"] == SymbolKind.VARIABLE
    assert x_dict["mutable"] is True

    # Symbol round-trip
    s = Symbol("y", SymbolKind.VARIABLE, type_annotation="string",
               attributes={"meta": 1})
    s2 = Symbol.from_dict(s.to_dict())
    assert s2.name == "y"
    assert s2.kind == SymbolKind.VARIABLE
    assert s2.type_annotation == "string"
    assert s2.attributes == {"meta": 1}
    print("test_to_dict_serialization: OK")


def test_predefined_types_exist():
    st = SymbolTable()
    expected = ["int", "float", "string", "bool", "void", "none",
                "true", "false",
                "Option", "Result", "List", "Dict", "Tuple",
                "Vec", "HashMap", "HashSet"]
    missing = [n for n in expected if st.lookup(n) is None]
    assert not missing, "predefined symbols missing: {}".format(missing)
    # true/false should be VARIABLEs, primitive types should be TYPE_ALIAS
    assert st.lookup("true").kind == SymbolKind.VARIABLE
    assert st.lookup("int").kind == SymbolKind.TYPE_ALIAS
    assert st.lookup("Option").kind == SymbolKind.TYPE_ALIAS
    print("test_predefined_types_exist: OK ({} builtins)".format(len(expected)))


def test_scope_dfs_traversal():
    st = SymbolTable()
    st.push_scope("fn1")
    st.pop_scope()
    st.push_scope("fn2")
    st.pop_scope()
    scopes = st.global_scope.all_scopes()
    # 1 global + 2 children
    assert len(scopes) == 3, "expected 3 scopes, got {}".format(len(scopes))
    print("test_scope_dfs_traversal: OK ({} scopes)".format(len(scopes)))


def test_lookup_local_does_not_walk_up():
    st = SymbolTable()
    st.define("outer", SymbolKind.VARIABLE, type_annotation="int")
    st.push_scope("inner")
    st.define("inner_var", SymbolKind.VARIABLE, type_annotation="int")
    # local lookup should NOT find outer
    assert st.lookup_local("outer") is None
    # full lookup should
    assert st.lookup("outer") is not None
    # local lookup finds inner_var
    assert st.lookup_local("inner_var") is not None
    st.pop_scope()
    print("test_lookup_local_does_not_walk_up: OK")


def test_pop_global_raises():
    st = SymbolTable()
    try:
        st.pop_scope()
    except VoxSemanticError:
        print("test_pop_global_raises: OK")
        return
    raise AssertionError("expected VoxSemanticError when popping global scope")


def test_scope_enter_exit_returns_parent():
    parent = Scope("parent", parent=None, scope_level=0)
    child = parent.enter_scope("child")
    assert child.parent is parent
    assert child.scope_level == 1
    assert child.exit_scope() is parent
    assert parent.children[0] is child
    print("test_scope_enter_exit_returns_parent: OK")


def test_repr_does_not_crash():
    st = SymbolTable()
    st.define("x", SymbolKind.VARIABLE, type_annotation="int")
    st.push_scope("fn")
    st.define("y", SymbolKind.VARIABLE, type_annotation="string")
    st.pop_scope()
    text = repr(st)
    assert "global" in text
    assert "fn" in text
    print("test_repr_does_not_crash: OK")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    tests = [
        test_basic_define_lookup,
        test_nested_scope_inner_sees_outer,
        test_duplicate_definition_raises,
        test_duplicate_in_different_scopes_allowed,
        test_self_reference_detection_optional_dict,
        test_self_reference_string_form,
        test_self_reference_no_false_positive,
        test_smart_pointer_mapping,
        test_module_registration,
        test_module_registration_accepts_dicts,
        test_to_dict_serialization,
        test_predefined_types_exist,
        test_scope_dfs_traversal,
        test_lookup_local_does_not_walk_up,
        test_pop_global_raises,
        test_scope_enter_exit_returns_parent,
        test_repr_does_not_crash,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL {}: {}: {}".format(t.__name__, type(e).__name__, e))
            traceback.print_exc()
    total = len(tests)
    passed = total - failed
    print("")
    print("=" * 60)
    print("{}/{} tests passed".format(passed, total))
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
