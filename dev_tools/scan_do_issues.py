"""
扫描 vools/ 下所有类，生成 do 方法问题报告。
用法: python dev_tools/scan_do_issues.py
"""
import ast
import os
import sys
from typing import List, Tuple

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'vools')

issues: List[Tuple[str, str, str]] = []  # (file, class, issue_type)

def has_slots(tree: ast.Module, class_name: str) -> bool:
    """检查类或其父类是否定义了 __slots__"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == '__slots__':
                            return True
    return False

def is_enum_class(tree: ast.Module, class_name: str) -> bool:
    """检查类是否继承自 Enum"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for base in node.bases:
                if isinstance(base, ast.Attribute) and base.attr == 'Enum':
                    return True
                if isinstance(base, ast.Name) and base.id == 'Enum':
                    return True
    return False

def is_dataclass(tree: ast.Module, class_name: str) -> bool:
    """检查类是否有 @dataclass 装饰器"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == 'dataclass':
                    return True
                if isinstance(decorator, ast.Attribute) and decorator.attr == 'dataclass':
                    return True
    return False

def class_has_do(tree: ast.Module, class_name: str) -> bool:
    """检查类是否定义了 do 方法"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == 'do':
                    return True
    return False

def scan_file(filepath: str):
    """扫描单个文件，记录问题"""
    relpath = os.path.relpath(filepath, os.path.join(BASE, '..'))
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except SyntaxError:
        print(f"  SYNTAX ERROR: {relpath}")
        return

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        cls = node.name
        is_enum = is_enum_class(tree, cls)
        is_dc = is_dataclass(tree, cls)
        has_sl = has_slots(tree, cls)
        has_do = class_has_do(tree, cls)

        should_have_do = not (is_enum or is_dc or has_sl)
        exclude_reason = ''
        if is_enum:
            exclude_reason = 'Enum'
        elif is_dc:
            exclude_reason = 'dataclass'
        elif has_sl:
            exclude_reason = '__slots__'

        if has_do and not should_have_do:
            issues.append((relpath, cls, f'HAS do BUT EXCLUDED ({exclude_reason})'))
        elif should_have_do and not has_do:
            issues.append((relpath, cls, 'MISSING do'))

def main():
    for root, dirs, files in os.walk(BASE):
        # 跳过 __pycache__
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'Temp', 'temp')]
        for fname in files:
            if fname.endswith('.py') and not fname.startswith('__'):
                scan_file(os.path.join(root, fname))

    # 按文件分组输出
    by_file = {}
    for relpath, cls, issue in issues:
        by_file.setdefault(relpath, []).append((cls, issue))

    print(f"总问题数: {len(issues)}\n")
    for relpath in sorted(by_file):
        print(f"【{relpath}】")
        for cls, issue in sorted(by_file[relpath]):
            print(f"  {cls}: {issue}")
        print()

    # 分别统计
    missing = [(p, c) for p, c, i in issues if i == 'MISSING do']
    extra = [(p, c) for p, c, i in issues if i.startswith('HAS do')]
    print(f"需添加 do: {len(missing)} 个类")
    print(f"需移除 do: {len(extra)} 个类")

if __name__ == '__main__':
    main()
