# -*- coding: utf-8 -*-
"""
实际测试 WebView2 渲染 - 弹出窗口
"""

import sys
import importlib.util
import time

# 导入 webview2
spec = importlib.util.spec_from_file_location(
    'webview2',
    r'E:\IDEProjects\AI\vools\bridges\vools\bridge\md\webview2.py'
)

# 先导入依赖
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
WebView2Mode = webview2.WebView2Mode


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
    
    if success:
        print("\n✓ WebView2 窗口已成功弹出！")
        print("模式:", WebView2Mode.NATIVE.value)
    else:
        print("\n✗ WebView2 窗口弹出失败")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
