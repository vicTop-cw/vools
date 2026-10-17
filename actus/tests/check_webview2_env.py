# -*- coding: utf-8 -*-
"""
检查 WebView2 环境
"""

import sys
import subprocess

print("="*60)
print("检查 WebView2 环境")
print("="*60)

# 检查 pythonnet
print("\n1. 检查 pythonnet...")
try:
    import clr
    print("   ✓ pythonnet 已安装")
except ImportError:
    print("   ✗ pythonnet 未安装")

# 检查 pywebview
print("\n2. 检查 pywebview...")
try:
    import webview
    print("   ✓ pywebview 已安装")
except ImportError:
    print("   ✗ pywebview 未安装")

# 检查 WebView2 运行时
print("\n3. 检查 WebView2 运行时...")
print("   尝试加载 WebView2...")

try:
    import clr
    from System import Environment
    
    # 检查注册表中的 WebView2 运行时
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")
        version, _ = winreg.QueryValueEx(key, "pv")
        winreg.CloseKey(key)
        print(f"   ✓ WebView2 运行时已安装: {version}")
    except FileNotFoundError:
        print("   ✗ WebView2 运行时未找到")
        
except Exception as e:
    print(f"   ✗ 检查失败: {e}")

# 检查 Windows 版本
print("\n4. 检查 Windows 版本...")
import platform
print(f"   Windows: {platform.version()}")
print(f"   版本: {platform.win32_ver()}")

# 尝试简单的 WebView2 测试
print("\n5. 尝试简单的 WebView2 测试...")
try:
    import clr
    clr.AddReference('Microsoft.Web.WebView2.WinForms')
    from Microsoft.Web.WebView2.WinForms import WebView2
    from System.Windows.Forms import Form, Application
    
    form = Form()
    form.Text = "Test"
    form.Width = 400
    form.Height = 300
    
    webview = WebView2()
    webview.Dock = 5  # Fill
    
    form.Controls.Add(webview)
    
    print("   ✓ WebView2 控件创建成功")
    
    # 尝试初始化
    print("   尝试初始化 WebView2...")
    webview.EnsureCoreWebView2Async(None)
    print("   ✓ WebView2 初始化成功")
    
except Exception as e:
    print(f"   ✗ WebView2 测试失败: {e}")

print("\n" + "="*60)
print("检查完成")
print("="*60)
