# -*- coding: utf-8 -*-
"""
测试 WebView2 动作 - 使用 md runner
"""
# 仓库根（由本测试文件位置推导，可移植；原为绝对路径硬编码）
import os
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


import sys

import os
import json


# 添加 bridges 目录到路径
bridges_dir = os.path.join(_REPO_ROOT, 'bridges')
sys.path.insert(0, bridges_dir)

# 导入 md runner
from vools.bridge.md import run_md

# 测试计算器动作
print("="*60)
print("测试 Calculator 动作")
print("="*60)

calculator_md = os.path.join(_REPO_ROOT, 'actus', 'vools', 'actus', 'actions', 'basics', 'calculator.actus.schema.md')

if os.path.exists(calculator_md):
    print(f"✓ 动作文件存在: {calculator_md}")
    
    try:
        # 解析 md 文件
        from vools.bridge.md import parse_md
        parsed = parse_md(calculator_md)
        print(f"✓ 解析成功")
        print(f"  块数量: {len(parsed.blocks)}")
        
        for i, block in enumerate(parsed.blocks):
            print(f"\n  块 {i}:")
            print(f"    语言: {block.language}")
            print(f"    指令: {block.directives}")
            print(f"    内容预览: {block.content[:100]}...")
        
    except Exception as e:
        import traceback
        print(f"✗ 解析失败: {e}")
        traceback.print_exc()
else:
    print(f"✗ 动作文件不存在: {calculator_md}")

# 测试待办事项动作
print("\n" + "="*60)
print("测试 Todo List 动作")
print("="*60)

todo_md = os.path.join(_REPO_ROOT, 'actus', 'vools', 'actus', 'actions', 'basics', 'todo-list.actus.schema.md')

if os.path.exists(todo_md):
    print(f"✓ 动作文件存在: {todo_md}")
    
    try:
        from vools.bridge.md import parse_md
        parsed = parse_md(todo_md)
        print(f"✓ 解析成功")
        print(f"  块数量: {len(parsed.blocks)}")
        
        for i, block in enumerate(parsed.blocks):
            print(f"\n  块 {i}:")
            print(f"    语言: {block.language}")
            print(f"    指令: {block.directives}")
            print(f"    内容预览: {block.content[:100]}...")
    except Exception as e:
        import traceback
        print(f"✗ 解析失败: {e}")
        traceback.print_exc()
else:
    print(f"✗ 动作文件不存在: {todo_md}")

print("\n" + "="*60)
print("测试完成")
print("="*60)
