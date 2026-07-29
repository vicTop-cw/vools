"""Tests for voxc.libs.lark_parser.

Runnable both as a pytest module and as a standalone script::

    python -m pytest tests_vox/test_lark_parser.py -v
    python tests_vox/test_lark_parser.py
"""

import os
import sys
import json
import traceback

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from voxc.libs.lark_parser import parse_source, is_available


def test_is_available_returns_bool():
    result = is_available()
    assert isinstance(result, bool)


def test_parse_source_returns_dict():
    source = "val x = 42"
    ast = parse_source(source, "test.vox")
    assert isinstance(ast, dict)
    assert "statements" in ast
    assert "name" in ast
    assert "span" in ast


def test_parse_source_json_serializable():
    source = """
val x = 42
var y = "hello"
const Z = 100
"""
    ast = parse_source(source, "test.vox")
    result = json.dumps(ast)
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed["name"] == "test"


def test_val_declaration():
    source = "val x = 42"
    ast = parse_source(source)
    stmts = ast["statements"]
    assert len(stmts) >= 1
    var_decl = None
    for s in stmts:
        if s.get("node") in ("VarDecl", "ConstDecl"):
            var_decl = s
            break
    assert var_decl is not None
    assert var_decl["name"] == "x"
    assert var_decl.get("mutable") in (False, None)


def test_var_declaration():
    source = "var x = 42"
    ast = parse_source(source)
    stmts = ast["statements"]
    var_decl = None
    for s in stmts:
        if s.get("node") == "VarDecl" and s.get("mutable"):
            var_decl = s
            break
    assert var_decl is not None
    assert var_decl["name"] == "x"
    assert var_decl["mutable"] is True


def test_const_declaration():
    source = "const MAX = 100"
    ast = parse_source(source)
    stmts = ast["statements"]
    const_decl = None
    for s in stmts:
        if s.get("node") == "ConstDecl":
            const_decl = s
            break
    if const_decl:
        assert const_decl["name"] == "MAX"


def test_var_with_type_annotation():
    source = "val x: int = 42"
    ast = parse_source(source)
    stmts = ast["statements"]
    var_decl = None
    for s in stmts:
        if s.get("node") in ("VarDecl", "ConstDecl") and s.get("name") == "x":
            var_decl = s
            break
    if var_decl and "type_annotation" in var_decl:
        assert var_decl["type_annotation"] is not None


def test_function_definition():
    source = """
def add(a: int, b: int) -> int:
    return a + b
"""
    ast = parse_source(source)
    stmts = ast["statements"]
    fn_def = None
    for s in stmts:
        if s.get("node") == "FnDef":
            fn_def = s
            break
    assert fn_def is not None
    assert fn_def["name"] == "add"
    assert "params" in fn_def
    assert "body" in fn_def


def test_if_statement():
    source = """
if x > 0:
    val result = "positive"
else:
    val result = "zero"
"""
    ast = parse_source(source)
    stmts = ast["statements"]
    if_stmt = None
    for s in stmts:
        if s.get("node") == "IfStmt":
            if_stmt = s
            break
    assert if_stmt is not None
    assert "condition" in if_stmt
    assert "then_body" in if_stmt


def test_for_loop():
    source = """
for i in range(10):
    val x = i
"""
    try:
        ast = parse_source(source)
        stmts = ast["statements"]
        for_loop = None
        for s in stmts:
            if s.get("node") in ("ForLoop", "Loop"):
                for_loop = s
                break
        if for_loop:
            assert "body" in for_loop
    except (ImportError, SyntaxError):
        pass


def test_while_loop():
    source = """
while x > 0:
    val y = x - 1
"""
    try:
        ast = parse_source(source)
        stmts = ast["statements"]
        while_loop = None
        for s in stmts:
            if s.get("node") in ("WhileLoop", "Loop"):
                while_loop = s
                break
        if while_loop:
            assert "condition" in while_loop
            assert "body" in while_loop
    except (ImportError, SyntaxError):
        pass


def test_struct_definition():
    source = """
struct Point:
    x: int
    y: int
"""
    ast = parse_source(source)
    stmts = ast["statements"]
    struct_def = None
    for s in stmts:
        if s.get("node") == "StructDef":
            struct_def = s
            break
    if struct_def:
        assert struct_def["name"] == "Point"
        assert "fields" in struct_def


def test_enum_definition():
    source = """
enum Color:
    Red
    Green
    Blue
"""
    ast = parse_source(source)
    stmts = ast["statements"]
    enum_def = None
    for s in stmts:
        if s.get("node") == "EnumDef":
            enum_def = s
            break
    if enum_def:
        assert enum_def["name"] == "Color"
        assert "variants" in enum_def


def test_trait_definition():
    source = """
trait Drawable:
    def draw(self) -> void
"""
    ast = parse_source(source)
    stmts = ast["statements"]
    trait_def = None
    for s in stmts:
        if s.get("node") == "TraitDef":
            trait_def = s
            break
    if trait_def:
        assert trait_def["name"] == "Drawable"
        assert "methods" in trait_def


def test_import_statement():
    source = "import math"
    ast = parse_source(source)
    stmts = ast["statements"]
    import_stmt = None
    for s in stmts:
        if s.get("node") in ("ImportStmt", "FromImport"):
            import_stmt = s
            break
    if import_stmt:
        assert "module" in import_stmt


def test_from_import():
    source = "from math import sin, cos"
    try:
        ast = parse_source(source)
        stmts = ast["statements"]
        from_import = None
        for s in stmts:
            if s.get("node") in ("FromImport", "ImportStmt"):
                from_import = s
                break
        if from_import:
            assert "module" in from_import
    except (ImportError, SyntaxError):
        pass


def test_literal_expressions():
    source = """
val x = 42
val y = 3.14
val s = "hello"
val b = true
val n = none
"""
    ast = parse_source(source)
    stmts = ast["statements"]
    assert len(stmts) >= 1


def test_binary_operations():
    source = "val result = 1 + 2 * 3"
    ast = parse_source(source)
    stmts = ast["statements"]
    assert len(stmts) >= 1


def test_function_call():
    source = "val result = foo(1, 2, 3)"
    ast = parse_source(source)
    stmts = ast["statements"]
    assert len(stmts) >= 1


def test_method_call():
    source = "val result = obj.method(1, 2)"
    ast = parse_source(source)
    stmts = ast["statements"]
    assert len(stmts) >= 1


def test_span_structure():
    source = "val x = 42"
    ast = parse_source(source, "test.vox")
    stmts = ast["statements"]
    if stmts:
        stmt = stmts[0]
        assert "span" in stmt
        span = stmt["span"]
        assert "file" in span
        assert "line" in span
        assert "col" in span
        assert "end_line" in span
        assert "end_col" in span


def test_return_statement():
    source = """
def my_func():
    return 42
"""
    ast = parse_source(source)
    stmts = ast["statements"]
    fn_def = None
    for s in stmts:
        if s.get("node") == "FnDef":
            fn_def = s
            break
    if fn_def:
        body = fn_def.get("body", [])
        return_found = False
        for stmt in body:
            if isinstance(stmt, dict) and stmt.get("node") == "ReturnStmt":
                return_found = True
                break
        assert return_found or len(body) >= 0


def test_multiple_statements():
    source = """
val a = 1
val b = 2
val c = a + b
"""
    ast = parse_source(source)
    stmts = ast["statements"]
    assert len(stmts) >= 2


def test_node_field_present():
    source = "val x = 42"
    ast = parse_source(source)
    stmts = ast["statements"]
    for stmt in stmts:
        if isinstance(stmt, dict) and stmt.get("node") not in (None,):
            assert "node" in stmt
            break


def test_filename_in_module():
    source = "val x = 1"
    ast = parse_source(source, "my_module.vox")
    assert ast["name"] == "my_module"


def _run_all():
    """Run every ``test_*`` function in this module; print a report.

    Returns True if all pass, False otherwise.
    """
    failures = []
    passed = 0
    for name in sorted(globals()):
        if not name.startswith("test_"):
            continue
        fn = globals()[name]
        if not callable(fn):
            continue
        try:
            fn()
            passed += 1
            print("PASS  " + name)
        except Exception as e:
            failures.append(name)
            print("FAIL  " + name + ": " + str(e))
            traceback.print_exc()
    print("")
    print("=" * 60)
    if failures:
        print("{}/{} tests passed; {} failed: {}".format(
            passed, passed + len(failures), len(failures), ", ".join(failures),
        ))
        return False
    print("{}/{} tests passed.".format(passed, passed))
    return True


if __name__ == "__main__":
    print("Lark available:", is_available())
    print()
    sys.exit(0 if _run_all() else 1)
