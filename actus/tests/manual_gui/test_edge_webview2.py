# -*- coding: utf-8 -*-
"""
使用 Edge 内置 WebView2 组件
"""

import sys
import clr
import os

print("="*60)
print("测试 Edge 内置 WebView2 组件")
print("="*60)

# Edge 路径
edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application'
versions = sorted([d for d in os.listdir(edge_path) if os.path.isdir(os.path.join(edge_path, d)) and '.' in d])
latest_version = versions[-1]

print(f"\nEdge 版本: {latest_version}")

# 添加 Edge 路径到程序集搜索路径
edge_webview_path = os.path.join(edge_path, latest_version, 'EBWebView')
print(f"WebView2 路径: {edge_webview_path}")

# 尝试添加路径
clr.AddReference('System')
from System import AppDomain
AppDomain.CurrentDomain.AppendPrivatePath(edge_webview_path)

# 尝试加载 WebView2
print("\n尝试加载 WebView2...")
try:
    clr.AddReference('Microsoft.Web.WebView2.WinForms')
    from Microsoft.Web.WebView2.WinForms import WebView2
    from System.Windows.Forms import Form, Application
    
    print("✓ WebView2 加载成功！")
    
    # 创建简单窗口
    form = Form()
    form.Text = "Test"
    form.Width = 400
    form.Height = 300
    
    webview = WebView2()
    webview.Dock = 5  # Fill
    
    form.Controls.Add(webview)
    
    # 尝试初始化
    print("尝试初始化 WebView2...")
    webview.EnsureCoreWebView2Async(None)
    
    print("✓ WebView2 初始化成功！")
    
    # 显示窗口
    print("显示窗口...")
    Application.Run(form)
    
except Exception as e:
    print(f"✗ 失败: {e}")
    print("\n尝试使用 Edge 的 WebView2...")
    
    try:
        # 直接从 Edge 目录加载
        clr.AddReference(os.path.join(edge_webview_path, 'Microsoft.Web.WebView2.WinForms.dll'))
        print("✗ 仍然失败")
    except Exception as e2:
        print(f"✗ 失败: {e2}")

print("\n" + "="*60)
print("诊断结果")
print("="*60)
print("\nEdge 内置了 WebView2 组件，但 Python 无法直接加载。")
print("需要安装独立的 WebView2 运行时才能被 Python 调用。")
print("\n请安装：https://developer.microsoft.com/en-us/microsoft-edge/webview2/")
