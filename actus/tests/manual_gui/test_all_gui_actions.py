# -*- coding: utf-8 -*-
"""
测试所有基础 GUI 动作 - 实际渲染
"""

import sys
import importlib.util
import time

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
WebView2Mode = webview2.WebView2Mode


def get_action_html(action_name):
    """获取动作的 HTML 内容"""
    actions = {
        'calculator': '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Calculator</title>
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
        <h1>Calculator</h1>
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
</html>''',
        
        'todo-list': '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Todo List</title>
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
        <h1>Todo List</h1>
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
</html>''',
    }
    
    return actions.get(action_name, '')


def test_action(action_name, title, width, height):
    """测试动作"""
    print(f"\n测试 {action_name}...")
    
    html = get_action_html(action_name)
    if not html:
        print(f"✗ 未找到动作: {action_name}")
        return False
    
    result = render_webview2(
        html,
        title=title,
        width=width,
        height=height,
        blocking=False,
        devtools=False
    )
    
    print(f"  结果: {result.status}")
    return result.status == "ok"


def main():
    print("="*60)
    print("测试所有基础 GUI 动作 - 实际渲染")
    print("="*60)
    print("\n注意: 这将弹出 WebView2 窗口")
    print("请查看窗口内容\n")
    
    actions = [
        ('calculator', 'Calculator', 400, 600),
        ('todo-list', 'Todo List', 500, 700),
    ]
    
    results = {}
    for action_name, title, width, height in actions:
        results[action_name] = test_action(action_name, title, width, height)
        time.sleep(1)  # 等待窗口关闭
    
    print(f"\n{'='*60}")
    print("测试结果汇总")
    print(f"{'='*60}")
    
    for name, passed in results.items():
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name}: {status}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\n总计: {passed}/{total} 个动作通过")
    
    if all(results.values()):
        print(f"\n✓ 所有 WebView2 窗口已成功弹出！")
        print(f"模式: {WebView2Mode.NATIVE.value}")
    
    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
