import sys
sys.path.insert(0, '.')
import ast

# 检查 codec.py 是否有语法错误
try:
    ast.parse(open('vools/serialize/codec.py', encoding='utf-8').read())
    print('codec.py 语法正确')
except SyntaxError as e:
    print(f'语法错误: {e}')

# 检查 _is_allowed_module 函数
from vools.serialize.codec import _is_allowed_module
print(f'_is_allowed_module(datetime): {_is_allowed_module("datetime")}')
print(f'_is_allowed_module(os): {_is_allowed_module("os")}')
print(f'_is_allowed_module(vools.data): {_is_allowed_module("vools.data")}')
print(f'_is_allowed_module(subprocess): {_is_allowed_module("subprocess")}')
print(f'_is_allowed_module(builtins): {_is_allowed_module("builtins")}')
