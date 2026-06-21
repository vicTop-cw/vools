"""
给指定文件中的所有缺失类添加 do 实例方法。
用法: python dev_tools/add_do_to_file.py <file_path>
生成 <file_path>.new，检查后再覆盖原文件。
"""
import ast
import sys
import os

# 标准 do 方法源代码（用作插入模板）
DO_METHOD = '''    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
'''

def _has_slots(tree, class_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == '__slots__':
                            return True
    return False

def _is_enum(filepath, class_name):
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for base in node.bases:
                if (isinstance(base, ast.Attribute) and base.attr == 'Enum') or \
                   (isinstance(base, ast.Name) and base.id == 'Enum'):
                    return True
    return False

def _is_dataclass(filepath, class_name):
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Name) and dec.id == 'dataclass') or \
                   (isinstance(dec, ast.Attribute) and dec.attr == 'dataclass'):
                    return True
    return False

def _class_has_do(filepath, class_name):
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == 'do':
                    return True
    return False

def _find_insert_line(lines, class_name):
    """找到 do 方法应插入的行索引（0-based），在类体中最后一个非空行之后"""
    in_class = False
    class_indent = None
    last_meaningful = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        # 检测类开始
        if not in_class and (stripped.startswith(f'class {class_name}') or
                                   stripped.startswith(f'class {class_name}(')):
            in_class = True
            class_indent = len(line) - len(line.lstrip())
            continue
        if in_class:
            cur_indent = len(line) - len(line.lstrip()) if stripped else None
            # 缩进小于等于类定义缩进，且非空，说明类已结束
            if cur_indent is not None and cur_indent <= class_indent and stripped:
                break
            if stripped:  # 记录最后一个非空行
                last_meaningful = i
    return last_meaningful  # 可能是 None

def add_do_to_file(filepath):
    relpath = os.path.relpath(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
    lines = source.split('\n')

    # 第一遍扫描：找出需要修复的类
    tree = ast.parse(source)
    to_fix = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        cls = node.name
        if _is_enum(filepath, cls) or _is_dataclass(filepath, cls) or _has_slots(tree, cls):
            continue
        if _class_has_do(filepath, cls):
            continue
        to_fix.append(cls)

    if not to_fix:
        print(f"{relpath}: 无需修改（所有类已有 do）")
        return False

    print(f"{relpath}: 需为以下类添加 do: {to_fix}")
    print("--- 变更预览 ---")

    # 逐个类处理
    new_lines = lines[:]
    for cls in to_fix:
        pos = _find_insert_line(new_lines, cls)
        if pos is None:
            print(f"  WARNING: 无法找到 {cls} 的插入位置，跳过")
            continue

        # 构造带缩进的 do 方法
        # 找到类的缩进级别
        class_indent = 4
        for line in new_lines:
            if line.strip().startswith(f'class {cls}') or line.strip().startswith(f'class {cls}('):
                class_indent = len(line) - len(line.lstrip())
                break

        do_lines = []
        for dl in DO_METHOD.split('\n'):
            if dl.strip() == '':
                do_lines.append('')
            else:
                do_lines.append(' ' * class_indent + dl)

        # 在 pos 行（最后一个非空行）之后插入
        # 确保插入位置后有空行分隔
        insert_idx = pos + 1
        if insert_idx < len(new_lines) and new_lines[insert_idx].strip():
            new_lines.insert(insert_idx, '')
            insert_idx += 1
        new_lines[insert_idx:insert_idx] = do_lines
        print(f"  + {cls}: 在第 {pos+1} 行后插入 do 方法")

    # 写入 .new 文件
    new_source = '\n'.join(new_lines)
    new_path = filepath + '.new'
    with open(new_path, 'w', encoding='utf-8') as f:
        f.write(new_source)

    print(f"\n已生成预览文件: {new_path}")
    print(f"检查后若无误，执行: copy {new_path} {filepath} && del {new_path}")
    return True


def main():
    if len(sys.argv) < 2:
        print("用法: python add_do_to_file.py <file_path>")
        return
    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"文件不存在: {filepath}")
        return
    add_do_to_file(filepath)


if __name__ == '__main__':
    main()
