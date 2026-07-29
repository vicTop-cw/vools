"""Quick test of Vox parser."""
from voxc.parser import VoxParser
from voxc.lexer import VoxLexer
from voxc.ast_nodes import ast_to_json
import json

source = "val x = 5\nif x > 5:\n    print(\"Big\")\nelse:\n    print(\"Small\")\n"

lexer = VoxLexer()
parser = VoxParser()
tokens = lexer.tokenize(source)
print("Tokens:")
for t in tokens:
    print("  {:12s} {:20s} L{}".format(t.type, t.value, t.line))
print()
module = parser.parse(tokens, "test")
print("AST:")
print(json.dumps(ast_to_json(module), indent=2))