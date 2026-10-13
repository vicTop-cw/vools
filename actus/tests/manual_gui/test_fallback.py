# -*- coding: utf-8 -*-
"""
测试浏览器 fallback 功能
"""

import sys
import importlib.util
import os

# 导入 webview2
spec = importlib.util.spec_from_file_location(
    'webview2',
    r'E:\IDEProjects\AI\vools\bridges\vools\bridge\md\webview2.py'
)

import importlib.util as iu

spec_dirs = iu.spec_from_file_location('directives', r'E:\IDEProjects\AI\vools\bridges\vools\bridge\md\directives.py')
dirs_mod = iu.module_from_spec(spec_dirs)
spec_dirs.loader.exec_module(dirs_mod)

spec_cfg = iu.spec_from_file_location('config', r'E:\IDEProjects\AI\vools\bridges\vools\bridge\md\config.py')
cfg_mod = iu.module_from_spec(spec_cfg)
spec_cfg.loader.exec_module(cfg_mod)

webview2 = iu.module_from_spec(spec)
spec.loader.exec_module(webview2)

render_webview2 = webview2.render_webview2


# 测试
print("="*60)
print("测试浏览器 fallback 功能")
print("="*60)

html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Test</title>
    <style>
        body { font-family: sans-serif; margin: 20px; }
        h1 { color: #667eea; }
    </style>
</head>
<body>
    <h1>Test</h1>
    <p>If you see this, browser fallback works!</p>
</body>
</html>'''

print("\n测试 WebView2 渲染...")
print("注意: 如果 WebView2 失败，会自动使用默认浏览器打开")

result = render_webview2(
    html,
    title="Test",
    width=400,
    height=600,
    blocking=True,  # 使用阻塞模式
    devtools=False
)

print(f"\n结果: {result.status}")
print(f"模式: {result.mode}")
if result.error:
    print(f"错误: {result.error}")

print("\n" + "="*60)
print("测试完成")
print("="*60)
