"""诊断：pytest 收集环境下 vools 解析路径"""
import sys
import vools

print('DIAG vools.__file__:', vools.__file__)
print('DIAG vools.__path__:', list(vools.__path__))
print('DIAG sys.path[:5]:', sys.path[:5])

import importlib
try:
    m = importlib.import_module('vools.bridge.freebasic')
    print('DIAG import_module OK:', m.__file__)
except Exception as e:
    print('DIAG import_module FAIL:', type(e).__name__, str(e)[:150])

def test_diag():
    assert True
