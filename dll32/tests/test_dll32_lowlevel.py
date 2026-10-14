"""底层 DLL 调用测试"""
import os as _os
import sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
if _os.path.isdir(_os.path.join(_ROOT, 'vools')) and _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
from vools.dll32._core._spawn32 import get_process

proc = get_process()

print('=== 测试 ping ===')
try:
    result = proc.call('ping')
    print('ping result:', repr(result))
except Exception as e:
    print('ping error:', e)

print()
print('=== 测试 list_dlls ===')
try:
    result = proc.call('list_dlls')
    print('list_dlls result:', repr(result))
except Exception as e:
    print('list_dlls error:', e)

print()
print('=== 测试 Base64Encode_UTF8 ===')
try:
    result = proc.call('call_dll', ['VB6Plus.dll', 'Base64Encode_UTF8', ['Hello']])
    print('call_dll result:', repr(result))
except Exception as e:
    print('call_dll error:', e)
