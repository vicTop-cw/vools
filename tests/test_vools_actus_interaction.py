# -*- coding: utf-8 -*-
"""
测试 vools 和 actus 之间的交互
"""

import sys
import os

# 确保使用本地代码
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus\vools')
sys.path.insert(0, r'E:\IDEProjects\AI\vools\bridges')

print("="*60)
print("测试 vools 和 actus 之间的交互")
print("="*60)

# 1. 测试 vools 基础功能
print("\n1. 测试 vools 基础功能...")
try:
    import vools
    print(f"   ✓ vools 导入成功: {vools.__version__}")
    
    # 测试 vools 核心功能
    from vools.functional import curry, _
    print(f"   ✓ vools.functional 可用")
    
    from vools.data import Seq
    print(f"   ✓ vools.data 可用")
    
except Exception as e:
    print(f"   ✗ vools 测试失败: {e}")

# 2. 测试 actus 基础功能
print("\n2. 测试 actus 基础功能...")
try:
    import actus
    print(f"   ✓ actus 导入成功")
    
    # 测试 actus 核心功能
    from actus import Action, parse_cfg
    print(f"   ✓ actus.model 可用")
    
    from actus.executor import execute
    print(f"   ✓ actus.executor 可用")
    
except Exception as e:
    print(f"   ✗ actus 测试失败: {e}")

# 3. 测试 actus 调用 vools 的 bridge 功能
print("\n3. 测试 actus 调用 vools 的 bridge 功能...")
try:
    from vools.bridge.manager import get_helper
    print(f"   ✓ vools.bridge.manager 可用")
    
    # 获取 Python helper
    helper = get_helper('python')
    print(f"   ✓ 获取 Python helper 成功")
    print(f"   ✓ Python 可用: {helper.is_available()}")
    
except Exception as e:
    print(f"   ✗ 测试失败: {e}")

# 4. 测试 vools.bridge.md 功能
print("\n4. 测试 vools.bridge.md 功能...")
try:
    from vools.bridge.md import parse_md, run_md
    print(f"   ✓ vools.bridge.md 可用")
    
    # 测试解析 md 文件
    test_md = r'E:\IDEProjects\AI\vools\actions\convert-file-to-markdown.actus.schema.md'
    if os.path.exists(test_md):
        parsed = parse_md(test_md)
        print(f"   ✓ MD 解析成功: {len(parsed.blocks)} 个块")
    else:
        print(f"   ⚠ 测试文件不存在: {test_md}")
    
except Exception as e:
    print(f"   ✗ 测试失败: {e}")

# 5. 测试 actus 使用 vools.bridge.md
print("\n5. 测试 actus 使用 vools.bridge.md...")
try:
    # actus 的 runtimes.py 应该能调用 vools.bridge.md
    from actus.runtimes import RuntimeRegistry
    print(f"   ✓ actus.runtimes 可用")
    
    registry = RuntimeRegistry()
    print(f"   ✓ RuntimeRegistry 创建成功")
    
    # 测试执行 Python 代码
    result = registry.execute('python', 'print("Hello from actus + vools")', {})
    print(f"   ✓ Python 代码执行成功")
    print(f"   输出: {result[0].strip()}")
    
except Exception as e:
    print(f"   ✗ 测试失败: {e}")

# 6. 测试 actus 动作调用 vools 桥接
print("\n6. 测试 actus 动作调用 vools 桥接...")
try:
    # 创建一个简单的动作
    from actus.model import Action
    
    action = Action(
        meta={
            'id': 'test-action',
            'name': 'Test Action',
            'version': '1.0.0',
            'trust': 'sandbox',
            'entry': 'main'
        },
        path='test.actus.md',
        sha256='test',
        raw='',
        body='''
```python #!run tag=main
import vools
result = vools.functional.curry(lambda x, y: x + y, 10)(5)
print(f"Result: {result}")
```
''',
        blocks=[{
            'index': 0,
            'language': 'python',
            'tag': 'main',
            'directives': {'run': ''}
        }]
    )
    
    print(f"   ✓ Action 创建成功: {action.id}")
    
except Exception as e:
    print(f"   ✗ 测试失败: {e}")

print("\n" + "="*60)
print("交互测试完成")
print("="*60)
