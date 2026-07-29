"""Vox compiler CLI entry point.

Usage:
    python -m voxc compile input.vox          # Parse + generate AST JSON
    python -m voxc run input.vox              # Parse + compile + run
    python -m voxc ast input.vox              # Parse + dump AST JSON
"""

import argparse
import json
import os
import sys

from voxc.lexer import VoxLexer
from voxc.parser import VoxParser
from voxc.ast_nodes import ast_to_json


def main():
    parser = argparse.ArgumentParser(description="Vox language compiler (Python frontend)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # compile
    compile_parser = subparsers.add_parser("compile", help="Parse .vox and output AST JSON")
    compile_parser.add_argument("input", help="Input .vox file")
    compile_parser.add_argument("-o", "--output", help="Output AST JSON file (default: stdout)")

    # run
    run_parser = subparsers.add_parser("run", help="Parse, compile, and run .vox file")
    run_parser.add_argument("input", help="Input .vox file")

    # ast
    ast_parser = subparsers.add_parser("ast", help="Parse and pretty-print AST JSON")
    ast_parser.add_argument("input", help="Input .vox file")

    args = parser.parse_args()

    if args.command == "compile":
        cmd_compile(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "ast":
        cmd_ast(args)


def parse_file(filepath):
    """Parse a .vox file and return AST JSON string."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    lexer = VoxLexer()
    parser = VoxParser()

    tokens = lexer.tokenize(source)
    ast_module = parser.parse(tokens, source_file=filepath)

    return json.dumps(ast_to_json(ast_module), indent=2, ensure_ascii=False)


def cmd_compile(args):
    """Parse and output AST JSON."""
    ast_json = parse_file(args.input)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(ast_json)
        print(f"AST JSON written to: {args.output}", file=sys.stderr)
    else:
        print(ast_json)


def cmd_run(args):
    """Parse and run via voxc Rust backend."""
    ast_json = parse_file(args.input)

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(ast_json)
        tmp_path = f.name

    try:
        import subprocess
        voxc_exe = os.path.join(os.path.dirname(__file__), "..", "..", "voxc-rs", "target", "release", "voxc.exe")
        voxc_exe = os.path.abspath(voxc_exe)
        result = subprocess.run(
            [voxc_exe, "run", "--input", args.input, "--ast-json", tmp_path],
            capture_output=False,
        )
        sys.exit(result.returncode)
    finally:
        os.unlink(tmp_path)


def cmd_ast(args):
    """Parse and pretty-print AST."""
    ast_json = parse_file(args.input)
    parsed = json.loads(ast_json)
    print(json.dumps(parsed, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()