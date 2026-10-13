# -*- coding: utf-8 -*-
"""
实际测试 WebView2 渲染 - 弹出窗口
"""

import sys
import os

# 添加 bridges 目录到路径
bridges_dir = r'E:\IDEProjects\AI\vools\bridges'
sys.path.insert(0, bridges_dir)

from vools.bridge.md import webview2

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
    return result.status == "ok"


def test_todo_list():
    """测试待办事项 WebView2"""
    html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Test Todo List</title>
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
        .app {
            background: white;
            border-radius: 24px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 400px;
        }
        h1 { color: #333; margin-bottom: 20px; }
        input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        button {
            padding: 12px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="app">
        <h1>Todo List Test</h1>
        <input type="text" placeholder="Add a task..." id="taskInput">
        <button onclick="addTask()">Add</button>
    </div>
    <script>
        function addTask() {
            var input = document.getElementById('taskInput');
            if (input.value) {
                sendToPython('added', input.value);
                input.value = '';
            }
        }
        function sendToPython(type, data) {
            if (window.chrome && window.chrome.webview) {
                window.chrome.webview.postMessage({ type: type, data: data });
            }
        }
    </script>
</body>
</html>'''
    
    print("测试 Todo List WebView2 渲染...")
    result = render_webview2(
        html,
        title="Todo List Test",
        width=500,
        height=700,
        blocking=False,
        devtools=False
    )
    print(f"结果: {result.status}")
    return result.status == "ok"


def main():
    print("="*60)
    print("实际测试 WebView2 渲染")
    print("="*60)
    print("\n注意: 这将弹出 WebView2 窗口")
    print("请查看窗口内容\n")
    
    results = {
        "Calculator": test_calculator(),
        "Todo List": test_todo_list(),
    }
    
    print(f"\n{'='*60}")
    print("测试结果")
    print(f"{'='*60}")
    
    for name, passed in results.items():
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name}: {status}")
    
    print("\n如果窗口成功弹出，说明 WebView2 工作正常！")
    print("模式:", WebView2Mode.NATIVE.value)
    
    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
