# -*- coding: utf-8 -*-
"""
简单的 pywebview 测试 - 检查后端
"""

import webview
import sys

print("="*60)
print("简单的 pywebview 测试")
print("="*60)

# 创建一个简单的窗口
print("\n创建窗口...")
window = webview.create_window(
    'Test Window',
    html='<h1>Test</h1><p>If you see this, it works!</p>',
    width=400,
    height=300
)

print(f"窗口创建成功")
print(f"窗口对象: {window}")

print("\n启动窗口...")
print("注意: 窗口应该弹出，请查看窗口内容")
print("关闭窗口后程序将退出\n")

# 启动
webview.start()

print("\n窗口已关闭")
