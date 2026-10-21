# -*- coding: utf-8 -*-
"""
检查 HTML 文件生成
"""
# 仓库根（由本测试文件位置推导，可移植；原为绝对路径硬编码）
import os
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import sys

import importlib.util
import os

# 导入 webview2
spec = importlib.util.spec_from_file_location(
    'webview2',
    os.path.join(_REPO_ROOT, 'bridges', 'vools', 'bridge', 'md', 'webview2.py')
)

import importlib.util as iu


spec_dirs = iu.spec_from_file_location('directives', os.path.join(_REPO_ROOT, 'bridges', 'vools', 'bridge', 'md', 'directives.py'))
dirs_mod = iu.module_from_spec(spec_dirs)
spec_dirs.loader.exec_module(dirs_mod)

spec_cfg = iu.spec_from_file_location('config', os.path.join(_REPO_ROOT, 'bridges', 'vools', 'bridge', 'md', 'config.py'))
cfg_mod = iu.module_from_spec(spec_cfg)
spec_cfg.loader.exec_module(cfg_mod)

webview2 = iu.module_from_spec(spec)
spec.loader.exec_module(webview2)

render_webview2 = webview2.render_webview2
WebView2Config = webview2.WebView2Config


# 测试 HTML 生成
html = '<h1>Test</h1>'
config = WebView2Config(
    title="Test",
    width=400,
    height=600,
    blocking=False,
    devtools=False
)

manager = webview2.WebView2Manager()
html_path = manager.generate_html(html, config, 'test')

print("="*60)
print("检查 HTML 文件生成")
print("="*60)

print(f"\nHTML 文件路径: {html_path}")
print(f"文件存在: {os.path.exists(html_path)}")

if os.path.exists(html_path):
    print(f"文件大小: {os.path.getsize(html_path)} 字节")
    
    # 读取内容
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"\n内容预览 (前 500 字符):")
    print(content[:500])
    
    # 检查关键内容
    print(f"\n关键内容检查:")
    print(f"  - DOCTYPE: {'✓' if '<!DOCTYPE html>' in content else '✗'}")
    print(f"  - <html>: {'✓' if '<html>' in content else '✗'}")
    print(f"  - <style>: {'✓' if '<style>' in content else '✗'}")
    print(f"  - <script>: {'✓' if '<script>' in content else '✗'}")
    print(f"  - sendToPython: {'✓' if 'sendToPython' in content else '✗'}")
else:
    print("✗ 文件不存在！")

# 检查 URL 格式
print(f"\nURL 格式检查:")
url = f"file:///{html_path.replace(os.sep, '/')}"
print(f"  URL: {url}")
print(f"  格式: {'✓' if url.startswith('file:///') else '✗'}")

# 检查路径分隔符
print(f"\n路径分隔符:")
print(f"  os.sep: {os.sep}")
print(f"  替换后的路径: {html_path.replace(os.sep, '/')}")
