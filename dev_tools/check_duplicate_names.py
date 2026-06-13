#!/usr/bin/env python
"""
检查 vools 项目中同名不同义的公开对象
"""
import os
import sys
import ast
from collections import defaultdict
from pathlib import Path


def find_all_py_files(root: Path) -> list[Path]:
    """找到所有 .py 文件"""
    py_files = []
    for dirpath, _, filenames in os.walk(root):
        dirpath = Path(dirpath)
        if 'tests' in dirpath.parts:
            continue  # 跳过测试目录
        for filename in filenames:
            if filename.endswith('.py') and not filename.startswith('_'):
                py_files.append(dirpath / filename)
    return py_files


def parse_all_lists(file: Path) -> list[str]:
    """解析文件中的 __all__ 列表"""
    try:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content)
    except Exception as e:
        print(f"Warning: Cannot parse {file}: {e}")
        return []
    
    all_names = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == '__all__':
                    if isinstance(node.value, ast.List):
                        for elem in node.value.elts:
                            if isinstance(elem, ast.Constant) and isinstance(elem.value, str):
                                all_names.append(elem.value)
                            elif isinstance(elem, ast.Str):  # Python 3.7-
                                all_names.append(elem.s)
    return all_names


def main():
    project_root = Path(__file__).parent
    py_files = find_all_py_files(project_root / 'vools')
    
    # 收集所有公开对象的来源
    name_sources = defaultdict(list)
    
    for file in py_files:
        relative_path = file.relative_to(project_root)
        all_names = parse_all_lists(file)
        if all_names:
            for name in all_names:
                name_sources[name].append(str(relative_path))
    
    # 找出重复的名字
    print("=" * 80)
    print("检查同名不同义的公开对象")
    print("=" * 80)
    
    duplicates = {name: sources for name, sources in name_sources.items() if len(sources) > 1}
    
    if not duplicates:
        print("[OK] 没有发现同名不同义的公开对象")
        return
    
    print(f"[WARN] 发现 {len(duplicates)} 个同名对象来自不同模块：\n")
    
    for name, sources in sorted(duplicates.items()):
        print(f"{name}:")
        for source in sources:
            print(f"  - {source}")
        print()
    
    # 按来源分组
    print("=" * 80)
    print("详细分析：")
    print("=" * 80)
    
    for name in sorted(duplicates.keys()):
        print(f"\n分析: {name}")
        for source in duplicates[name]:
            print(f"  来源: {source}")
            
            # 尝试导入看看
            try:
                module_path = source.replace('.py', '').replace(os.sep, '.')
                if module_path.startswith('vools.'):
                    module = __import__(module_path, fromlist=[''])
                    obj = getattr(module, name, None)
                    if obj is not None:
                        print(f"    类型: {type(obj).__name__}")
                        if hasattr(obj, '__doc__') and obj.__doc__:
                            doc = obj.__doc__.strip().split('\n')[0][:80]
                            print(f"    文档: {doc}...")
            except Exception as e:
                print(f"    警告: 无法导入 - {e}")


if __name__ == '__main__':
    main()
