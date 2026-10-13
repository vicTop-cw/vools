# -*- coding: utf-8 -*-
"""
测试 WebView2 动作 - 只运行 WebView2 块
"""

import sys
import os
import time

# 添加 bridges 目录到路径
bridges_dir = r'E:\IDEProjects\AI\vools\bridges'
sys.path.insert(0, bridges_dir)

from vools.bridge.md import parse_md


def extract_webview2_blocks(md_path):
    """从 md 文件中提取 WebView2 块"""
    print(f"\n解析: {md_path}")
    
    if not os.path.exists(md_path):
        print(f"✗ 文件不存在")
        return []
    
    try:
        parsed = parse_md(md_path)
        webview2_blocks = []
        
        for block in parsed.blocks:
            if 'webview2' in block.language.lower():
                webview2_blocks.append({
                    'language': block.language,
                    'content': block.content,
                    'directives': block.directives
                })
        
        print(f"✓ 找到 {len(webview2_blocks)} 个 WebView2 块")
        return webview2_blocks
    
    except Exception as e:
        print(f"✗ 解析失败: {e}")
        return []


def test_webview2_rendering():
    """测试 WebView2 渲染"""
    print("="*60)
    print("测试 WebView2 动作渲染")
    print("="*60)
    
    actions = [
        (r'E:\IDEProjects\AI\vools\actus\vools\actus\actions\basics\calculator.actus.schema.md', 'Calculator'),
        (r'E:\IDEProjects\AI\vools\actus\vools\actus\actions\basics\todo-list.actus.schema.md', 'Todo List'),
        (r'E:\IDEProjects\AI\vools\actus\vools\actus\actions\basics\text-editor.actus.schema.md', 'Text Editor'),
        (r'E:\IDEProjects\AI\vools\actus\vools\actus\actions\basics\image-viewer.actus.schema.md', 'Image Viewer'),
    ]
    
    results = {}
    
    for md_path, action_name in actions:
        print(f"\n{'='*60}")
        print(f"测试 {action_name}")
        print(f"{'='*60}")
        
        blocks = extract_webview2_blocks(md_path)
        
        if blocks:
            for i, block in enumerate(blocks):
                print(f"\nWebView2 块 {i}:")
                print(f"  语言: {block['language']}")
                print(f"  内容长度: {len(block['content'])} 字符")
                
                # 检查关键特性
                features = []
                if '<!DOCTYPE html>' in block['content']:
                    features.append('HTML5')
                if '<style>' in block['content']:
                    features.append('CSS')
                if '<script>' in block['content']:
                    features.append('JavaScript')
                if 'gradient' in block['content'].lower():
                    features.append('渐变背景')
                
                if features:
                    print(f"  特性: {', '.join(features)}")
            
            results[action_name] = True
        else:
            results[action_name] = False
    
    print(f"\n{'='*60}")
    print("测试结果汇总")
    print(f"{'='*60}")
    
    for name, passed in results.items():
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name}: {status}")
    
    return all(results.values())


if __name__ == "__main__":
    success = test_webview2_rendering()
    print("\n注意: 这些测试只验证了解析和内容，")
    print("实际 WebView2 窗口渲染需要在运行时执行。")
    sys.exit(0 if success else 1)
