#!/usr/bin/env python
"""
检查所有 .py 文件是否都有 __all__ 变量
"""
import os
import ast
from pathlib import Path


def has_all_list(file_path):
    """检查文件是否有 __all__ 变量"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content)
    except Exception:
        return False
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == '__all__':
                    if isinstance(node.value, ast.List):
                        return True
    return False


def main():
    project_root = Path(__file__).parent
    missing_all = []
    
    for dirpath, _, filenames in os.walk(project_root):
        dirpath = Path(dirpath)
        
        # 跳过某些目录
        if 'tests' in dirpath.parts:
            continue
        if '.git' in dirpath.parts:
            continue
        if '__pycache__' in dirpath.parts:
            continue
        if 'checkpoint' in str(dirpath).lower():
            continue
        
        for filename in filenames:
            if filename.endswith('.py'):
                file_path = dirpath / filename
                if not has_all_list(file_path):
                    missing_all.append(str(file_path.relative_to(project_root)))
    
    print("=" * 80)
    print("检查 __all__ 变量")
    print("=" * 80)
    
    if not missing_all:
        print("[OK] 所有文件都有 __all__ 变量")
        return
    
    print(f"[WARN] 发现 {len(missing_all)} 个文件缺少 __all__ 变量：")
    print()
    for file in missing_all:
        print(f"  - {file}")
    
    return missing_all


if __name__ == '__main__':
    main()
