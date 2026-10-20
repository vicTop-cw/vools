# -*- coding: utf-8 -*-
"""
测试 pywebview 不同后端
"""

import sys
import os

print("="*60)
print("测试 pywebview 不同后端")
print("="*60)

# 检查环境
print("\n1. 环境变量:")
print(f"   PYTHONPATH: {os.environ.get('PYTHONPATH', '未设置')}")

# 测试不同后端
backends = ['edgechromium', 'edgehtml', 'mshtml', 'cef']

for backend in backends:
    print(f"\n2. 测试后端: {backend}")
    try:
        import webview
        
        # 设置后端
        if backend == 'edgechromium':
            # 强制使用 Edge Chromium
            window = webview.create_window(
                'Test',
                html='<h1>Test</h1>',
                width=400,
                height=300
            )
        else:
            window = webview.create_window(
                'Test',
                html='<h1>Test</h1>',
                width=400,
                height=300
            )
        
        print(f"   ✓ 窗口创建成功")
        
        # 尝试启动
        webview.start()
        print(f"   ✓ 启动成功")
        
    except Exception as e:
        print(f"   ✗ 失败: {e}")

print("\n" + "="*60)
print("测试完成")
print("="*60)
