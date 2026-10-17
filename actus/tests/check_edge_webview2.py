# -*- coding: utf-8 -*-
"""
检查 Edge WebView2 组件
"""

import sys
import clr

print("="*60)
print("检查 Edge WebView2 组件")
print("="*60)

# 检查 Edge 版本
print("\n1. 检查 Edge 浏览器...")
try:
    import subprocess
    result = subprocess.run(
        [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', '--version'],
        capture_output=True,
        text=True
    )
    print(f"   Edge 版本: {result.stdout.strip()}")
except Exception as e:
    print(f"   ✗ 检查失败: {e}")

# 尝试从 Edge 加载 WebView2
print("\n2. 尝试从 Edge 目录加载 WebView2...")

edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application'

import os
if os.path.exists(edge_path):
    # 查找版本目录
    versions = [d for d in os.listdir(edge_path) if os.path.isdir(os.path.join(edge_path, d)) and '.' in d]
    if versions:
        latest_version = sorted(versions)[-1]
        print(f"   最新版本: {latest_version}")
        
        # 尝试加载 WebView2
        edge_webview_path = os.path.join(edge_path, latest_version, 'EBWebView')
        print(f"   WebView2 路径: {edge_webview_path}")
        print(f"   路径存在: {os.path.exists(edge_webview_path)}")

print("\n" + "="*60)
print("诊断结果")
print("="*60)
print("\nWebView2 运行时未独立安装。")
print("Edge 浏览器内置了 WebView2 组件，但需要单独安装运行时才能被 Python 调用。")
print("\n请重新安装 WebView2 运行时：")
print("https://developer.microsoft.com/en-us/microsoft-edge/webview2/")
