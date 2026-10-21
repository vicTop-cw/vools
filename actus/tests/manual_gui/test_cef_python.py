# -*- coding: utf-8 -*-
"""
使用 CEF Python 渲染 GUI
"""
# 仓库根（由本测试文件位置推导，可移植；原为绝对路径硬编码）
import os
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


import sys

import os


# 添加路径
sys.path.insert(0, os.path.join(_REPO_ROOT, 'bridges'))

from cefpython3 import cefpython as cef


def test_cef_python():
    """测试 CEF Python"""
    print("="*60)
    print("测试 CEF Python")
    print("="*60)
    
    # HTML 内容
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
    <h1>CEF Python Test</h1>
    <p>If you see this, CEF Python works!</p>
</body>
</html>'''
    
    # 保存为临时文件
    temp_dir = os.path.join(tempfile.gettempdir(), "vools_test")
    os.makedirs(temp_dir, exist_ok=True)
    html_path = os.path.join(temp_dir, "test.html")
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\nHTML 文件: {html_path}")
    
    # 初始化 CEF
    print("\n初始化 CEF...")
    settings = {
        "windowless_rendering_enabled": False,
    }
    
    try:
        cef.Initialize(settings)
        print("✓ CEF 初始化成功")
        
        # 创建浏览器窗口
        print("创建浏览器窗口...")
        window_info = cef.WindowInfo()
        window_info.SetAsChild(0)  # 创建为子窗口
        
        browser = cef.CreateBrowserSync(
            url=f"file:///{html_path}",
            window_info=window_info,
            window_title="Test"
        )
        
        print("✓ 浏览器窗口创建成功")
        
        # 运行消息循环
        print("\n运行消息循环...")
        print("注意: 窗口应该弹出，请查看窗口内容")
        print("关闭窗口后程序将退出\n")
        
        cef.MessageLoop()
        cef.Shutdown()
        
        print("\n✓ 测试完成")
        return True
        
    except Exception as e:
        import traceback
        print(f"\n✗ 失败: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import tempfile
    success = test_cef_python()
    sys.exit(0 if success else 1)
