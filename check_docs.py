#!/usr/bin/env python
"""
检查项目中所有公开对象的文档完整性
"""
import os
import ast
import inspect
from pathlib import Path

def has_docstring(node):
    """检查节点是否有文档字符串"""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        if node.body and isinstance(node.body[0], ast.Expr):
            if isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                return len(node.body[0].value.value.strip()) > 10
    return False

def analyze_file(file_path):
    """分析单个文件的文档情况"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content)
    except Exception as e:
        return []
    
    issues = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if not has_docstring(node):
                issues.append(f"函数 '{node.name}' 缺少或文档过短")
        elif isinstance(node, ast.AsyncFunctionDef):
            if not has_docstring(node):
                issues.append(f"异步函数 '{node.name}' 缺少或文档过短")
        elif isinstance(node, ast.ClassDef):
            if not has_docstring(node):
                issues.append(f"类 '{node.name}' 缺少或文档过短")
    
    return issues

def main():
    project_root = Path(__file__).parent / 'vools'
    all_issues = {}
    
    # 只检查核心模块
    core_modules = [
        'decorators', 'functional', 'vic', 'task', 
        'encoding', 'crypto', 'datetime', 'oop', 'data', 'core'
    ]
    
    for module in core_modules:
        module_path = project_root / module
        if not module_path.exists():
            continue
        
        for dirpath, _, filenames in os.walk(module_path):
            dirpath = Path(dirpath)
            
            if '__pycache__' in dirpath.parts:
                continue
            
            for filename in filenames:
                if filename.endswith('.py'):
                    file_path = dirpath / filename
                    issues = analyze_file(file_path)
                    if issues:
                        all_issues[str(file_path.relative_to(project_root))] = issues
    
    print("=" * 80)
    print("文档完整性检查报告")
    print("=" * 80)
    
    if not all_issues:
        print("[OK] 所有文件的公开对象都有足够的文档")
        return
    
    total_issues = sum(len(issues) for issues in all_issues.values())
    print(f"[WARN] 发现 {total_issues} 个文档问题")
    print()
    
    for file, issues in all_issues.items():
        print(f"File: {file}")
        for issue in issues:
            print(f"  - {issue}")
        print()
    
    return all_issues

if __name__ == '__main__':
    main()
