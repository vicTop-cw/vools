# -*- coding: utf-8 -*-
"""
测试 WebView2 动作 - 实际执行并显示 GUI
"""

import sys
import os
import time

# 添加 bridges 目录到路径
bridges_dir = r'E:\IDEProjects\AI\vools\bridges'
sys.path.insert(0, bridges_dir)

from vools.bridge.md import run_md


def run_action_test(md_path, action_name, timeout=10):
    """实际运行动作并显示 GUI"""
    print(f"\n{'='*60}")
    print(f"运行 {action_name} 动作")
    print(f"{'='*60}")
    
    if not os.path.exists(md_path):
        print(f"✗ 动作文件不存在: {md_path}")
        return False
    
    print(f"✓ 动作文件: {md_path}")
    print(f"正在启动 WebView2 窗口...")
    
    try:
        # 运行 md 文件（这会弹出 WebView2 窗口）
        result = run_md(md_path, force=True)
        
        if result and 'blocks' in result:
            for block in result['blocks']:
                if block.get('status') == 'ok':
                    print(f"\n✓ 块执行成功")
                    print(f"  语言: {block.get('language', 'unknown')}")
                    
                    if block.get('stdout'):
                        stdout = block.get('stdout', '')
                        if len(stdout) > 200:
                            print(f"  输出: {stdout[:200]}...")
                        else:
                            print(f"  输出: {stdout}")
                    
                    if block.get('mode'):
                        print(f"  模式: {block.get('mode')}")
                    
                    # 检查是否有 webview2 输出
                    if 'webview2' in block.get('language', '').lower() or 'html_path' in block:
                        print(f"  ✓ WebView2 已启动!")
                        if block.get('html_path'):
                            print(f"  HTML 文件: {block.get('html_path')}")
                
                elif block.get('status') == 'error':
                    print(f"\n✗ 块执行失败")
                    print(f"  语言: {block.get('language', 'unknown')}")
                    print(f"  错误: {block.get('error', 'Unknown error')}")
            
            return True
        else:
            print(f"✗ 运行失败: {result}")
            return False
            
    except Exception as e:
        import traceback
        print(f"✗ 执行异常: {e}")
        traceback.print_exc()
        return False


def main():
    print("="*60)
    print("测试 vools-actus 基础 GUI 动作 - 实际执行")
    print("="*60)
    print("\n注意: 这将弹出 WebView2 窗口，请查看窗口内容")
    print("窗口会自动关闭后继续测试下一个动作\n")
    
    actions = [
        (r'E:\IDEProjects\AI\vools\actus\vools\actus\actions\basics\calculator.actus.schema.md', 'Calculator'),
        (r'E:\IDEProjects\AI\vools\actus\vools\actus\actions\basics\todo-list.actus.schema.md', 'Todo List'),
        (r'E:\IDEProjects\AI\vools\actus\vools\actus\actions\basics\text-editor.actus.schema.md', 'Text Editor'),
        (r'E:\IDEProjects\AI\vools\actus\vools\actus\actions\basics\image-viewer.actus.schema.md', 'Image Viewer'),
    ]
    
    results = {}
    for md_path, action_name in actions:
        success = run_action_test(md_path, action_name)
        results[action_name] = success
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
    
    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
