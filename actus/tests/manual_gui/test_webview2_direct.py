# -*- coding: utf-8 -*-
"""
实际测试 WebView2 渲染 - 弹出窗口（直接导入）
"""
# 仓库根（由本测试文件位置推导，可移植；原为绝对路径硬编码）
import os
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


import sys

import os
import importlib.util


# 直接导入 webview2.py
spec = importlib.util.spec_from_file_location(
    "webview2",
    os.path.join(_REPO_ROOT, 'bridges', 'vools', 'bridge', 'md', 'webview2.py')
)
webview2_module = importlib.util.module_from_spec(spec)

# 需要先导入依赖
# 1. 导入 directives
spec_dirs = importlib.util.spec_from_file_location(
    "directives",
    os.path.join(_REPO_ROOT, 'bridges', 'vools', 'bridge', 'md', 'directives.py')
)
directories_module = importlib.util.module_from_spec(spec_dirs)
spec_dirs.loader.exec_module(directories_module)
sys.modules['vools.bridge.md.directives'] = directories_module

# 2. 导入 config
spec_config = importlib.util.spec_from_file_location(
    "config",
    os.path.join(_REPO_ROOT, 'bridges', 'vools', 'bridge', 'md', 'config.py')
)
config_module = importlib.util.module_from_spec(spec_config)
spec_config.loader.exec_module(config_module)
sys.modules['vools.bridge.md.config'] = config_module

# 3. 执行 webview2
spec.loader.exec_module(webview2_module)

render_webview2 = webview2_module.render_webview2
WebView2Mode = webview2_module.WebView2Mode


def test_calculator():
    """测试计算器 WebView2"""
    html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Test Calculator</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .calculator {
            background: white;
            border-radius: 24px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { color: #333; margin-bottom: 20px; }
        button {
            padding: 15px 30px;
            font-size: 18px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="calculator">
        <h1>Calculator Test</h1>
        <button onclick="sendToPython('clicked')">Click Me</button>
    </div>
    <script>
        function sendToPython(msg) {
            if (window.chrome && window.chrome.webview) {
                window.chrome.webview.postMessage({ type: 'event', data: msg });
            }
        }
    </script>
</body>
</html>'''
    
    print("测试 Calculator WebView2 渲染...")
    result = render_webview2(
        html,
        title="Calculator Test",
        width=400,
        height=600,
        blocking=False,
        devtools=False
    )
    print(f"结果: {result.status}")
    if result.error:
        print(f"错误: {result.error}")
    return result.status == "ok"


def main():
    print("="*60)
    print("实际测试 WebView2 渲染")
    print("="*60)
    print("\n注意: 这将弹出 WebView2 窗口")
    print("请查看窗口内容\n")
    
    success = test_calculator()
    
    print(f"\n{'='*60}")
    print("测试结果")
    print(f"{'='*60}")
    print(f"Calculator: {'✓ 通过' if success else '✗ 失败'}")
    
    print("\n如果窗口成功弹出，说明 WebView2 工作正常！")
    print("模式:", WebView2Mode.NATIVE.value)
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
