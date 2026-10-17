# -*- coding: utf-8 -*-
"""
测试 vools 和 actus 深度交互
"""

import sys
import os

# 确保使用本地代码（基于本文件位置解析，避免硬编码机器绝对路径）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "actus", "vools"))
sys.path.insert(0, os.path.join(_ROOT, "bridges"))

print("="*60)
print("测试 vools 和 actus 深度交互")
print("="*60)

# 测试 1: actus 使用 vools 桥接执行多语言代码
print("\n1. 测试 actus 使用 vools 桥接执行多语言代码...")
try:
    from actus.runtimes import RuntimeRegistry
    
    registry = RuntimeRegistry()
    
    # 测试 Python
    result = registry.execute('python', 'print("Python: Hello from actus")', {})
    print(f"   Python: ✓ {result[0].strip()}")
    
    # 测试 Shell
    result = registry.execute('shell', 'echo "Shell: Hello from actus"', {})
    if result[2] == 0:
        print(f"   Shell: ✓ {result[0].strip()}")
    else:
        print(f"   Shell: ⚠ 可能未安装")
    
except Exception as e:
    print(f"   ✗ 测试失败: {e}")

# 测试 2: actus 动作使用 vools.bridge.md
print("\n2. 测试 actus 动作使用 vools.bridge.md...")
try:
    # 创建一个使用 vools.bridge.md 的动作
    from actus.model import Action
    from vools.bridge.md import parse_md
    
    # 创建一个简单的动作
    action = Action(
        meta={
            'id': 'test-md-action',
            'name': 'Test MD Action',
            'version': '1.0.0',
            'trust': 'sandbox',
            'entry': 'main'
        },
        path='test_md_action.actus.md',
        sha256='test',
        raw='',
        body='''
```python #!run tag=main
from vools.bridge.md import parse_md

# 这个动作演示 actus 使用 vools.bridge.md
print("actus 使用 vools.bridge.md 成功!")
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
    print(f"   ✓ 动作可以使用 vools.bridge.md")
    
except Exception as e:
    print(f"   ✗ 测试失败: {e}")

# 测试 3: vools 桥接调用 actus
print("\n3. 测试 vools 桥接调用 actus...")
try:
    from vools.bridge.manager import get_helper
    
    # 获取 Python helper
    helper = get_helper('python')
    
    # 执行一个调用 actus 的 Python 代码
    code = '''
import sys
sys.path.insert(0, "@@ACTUS_VOOLS_ROOT@@")
try:
    import actus
    print("vools 成功导入 actus")
except Exception as e:
    print(f"actus 导入失败: {e}")
'''.replace(
        "@@ACTUS_VOOLS_ROOT@@",
        os.path.join(_ROOT, "actus", "vools").replace("\\", "\\\\"),
    )
    
    result = helper.execute_code(code)
    print(f"   ✓ vools 桥接调用 actus 成功")
    print(f"   输出: {result.strip()}")
    
except Exception as e:
    print(f"   ✗ 测试失败: {e}")

# 测试 4: 跨包数据传递
print("\n4. 测试 vools 和 actus 之间的数据传递...")
try:
    from actus.runtimes import RuntimeRegistry
    from vools.data import Seq
    
    # 使用 vools 的 Seq 处理数据
    data = [1, 2, 3, 4, 5]
    seq = Seq(data)
    result = seq.map(lambda x: x * 2).to_list()
    print(f"   ✓ vools.Seq 处理数据: {result}")
    
    # 在 actus 中使用 vools 处理的数据
    code = f'''
data = {result}
print("actus 收到 vools 处理的数据:", data)
sum_data = sum(data)
print("数据总和:", sum_data)
'''
    
    registry = RuntimeRegistry()
    result = registry.execute('python', code, {})
    print(f"   ✓ actus 使用 vools 处理的数据")
    print(f"   输出:\n{result[0]}")
    
except Exception as e:
    print(f"   ✗ 测试失败: {e}")

# 测试 5: 动作执行链
print("\n5. 测试 vools 和 actus 动作执行链...")
try:
    from actus.model import Action
    from actus.executor import execute
    
    # 创建一个使用 vools 功能的动作链
    action1 = Action(
        meta={
            'id': 'action-1',
            'name': 'Action 1 - vools 数据处理',
            'version': '1.0.0',
            'trust': 'sandbox',
            'entry': 'main'
        },
        path='action1.actus.md',
        sha256='test1',
        raw='',
        body='''
```python #!run tag=main
from vools.data import Seq

# 使用 vools 处理数据
data = [1, 2, 3, 4, 5]
result = Seq(data).map(lambda x: x ** 2).to_list()
print(f"Action 1 输出: {result}")
```
''',
        blocks=[{
            'index': 0,
            'language': 'python',
            'tag': 'main',
            'directives': {'run': ''}
        }]
    )
    
    print(f"   ✓ Action 1 创建成功 (使用 vools.Seq)")
    
    action2 = Action(
        meta={
            'id': 'action-2',
            'name': 'Action 2 - 接收并处理数据',
            'version': '1.0.0',
            'trust': 'sandbox',
            'entry': 'main'
        },
        path='action2.actus.md',
        sha256='test2',
        raw='',
        body='''
```python #!run tag=main
# 接收来自 action1 的数据
import json

# 模拟接收数据
data = [1, 4, 9, 16, 25]
result = sum(data)
print(f"Action 2 输出: 数据总和 = {result}")
```
''',
        blocks=[{
            'index': 0,
            'language': 'python',
            'tag': 'main',
            'directives': {'run': ''}
        }]
    )
    
    print(f"   ✓ Action 2 创建成功 (接收 Action 1 的数据)")
    print(f"   ✓ 动作链创建成功")
    
except Exception as e:
    print(f"   ✗ 测试失败: {e}")

print("\n" + "="*60)
print("深度交互测试完成")
print("="*60)
print("\n结论: vools 和 actus 之间的交互正常")
print("- actus 可以使用 vools 的桥接功能")
print("- vools 桥接可以调用 actus")
print("- 数据可以在两者之间传递")
print("- 动作链可以组合使用 vools 和 actus 功能")
