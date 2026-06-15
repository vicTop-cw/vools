"""调试 _get_func_info"""
import sys
sys.path.insert(0, '.')

from vools.decorators.curry_core import _get_func_info

def process(a, b, c):
    return a + b + c

info = _get_func_info(process)
print("_get_func_info 结果:")
print("  sig:", info["sig"])
print("  params:", list(info["params"].keys()))
print("  required_args:", info["required_args"])
print("  f:", info["f"])