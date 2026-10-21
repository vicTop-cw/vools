# -*- coding: utf-8 -*-
"""
调试 WebView2
"""
# 仓库根（由本测试文件位置推导，可移植；原为绝对路径硬编码）
import os
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


import sys

import importlib.util

# 导入 webview2
spec = importlib.util.spec_from_file_location(
    'webview2',
    os.path.join(_REPO_ROOT, 'bridges', 'vools', 'bridge', 'md', 'webview2.py')
)

# 先导入依赖
import importlib.util as iu


spec_dirs = iu.spec_from_file_location('directives', os.path.join(_REPO_ROOT, 'bridges', 'vools', 'bridge', 'md', 'directives.py'))
dirs_mod = iu.module_from_spec(spec_dirs)
spec_dirs.loader.exec_module(dirs_mod)

spec_cfg = iu.spec_from_file_location('config', os.path.join(_REPO_ROOT, 'bridges', 'vools', 'bridge', 'md', 'config.py'))
cfg_mod = iu.module_from_spec(spec_cfg)
spec_cfg.loader.exec_module(cfg_mod)

webview2 = iu.module_from_spec(spec)
spec.loader.exec_module(webview2)

# 测试 WebView2Config
print("测试 WebView2Config...")
config = webview2.WebView2Config(
    title="Test",
    width=400,
    height=600,
    blocking=False,
    devtools=False
)

print(f"config.theme: {config.theme}")
print(f"type: {type(config.theme)}")

# 测试 _get_theme_styles
manager = webview2.WebView2Manager()
try:
    styles = manager._get_theme_styles(config.theme)
    print(f"✓ _get_theme_styles 成功")
    print(f"  样式长度: {len(styles)}")
except Exception as e:
    import traceback
    print(f"✗ _get_theme_styles 失败: {e}")
    traceback.print_exc()

# 测试 generate_html
try:
    html_path = manager.generate_html('<h1>Test</h1>', config, 'test')
    print(f"✓ generate_html 成功: {html_path}")
except Exception as e:
    import traceback
    print(f"✗ generate_html 失败: {e}")
    traceback.print_exc()
