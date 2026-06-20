"""
批量修复缺失的返回注解和 docstring

智能检测：
- 无 return 语句 → -> None
- 有 return self → -> Self
- @property 且有 return expr → 尝试推断类型
- 其他 → -> Any

同时为无 docstring 的 public method 添加一句话 docstring。
"""
import ast
import os
import sys
from typing import Set, Tuple

base = 'vools'
skip_dirs = {'__pycache__', '.git', '.pytest_cache', 'Temp'}

# 已知返回类型的 pattern
RETURN_TYPE_MAP = {
    'bool': 'bool',
    'int': 'int',
    'str': 'str',
    'float': 'float',
    'list': 'list',
    'dict': 'dict',
    'True': 'bool',
    'False': 'bool',
    'None': 'None',
    '[]': 'list',
    '{}': 'dict',
    '()': 'tuple',
    "''": 'str',
    '': 'str',
    '0': 'int',
    '0.0': 'float',
}

def infer_return_type(method_body: str, method_name: str) -> str:
    """根据方法体推断返回类型"""
    # @property → 看 return 表达式
    # 检查所有 return 语句
    lines = method_body.split('\n')
    returns = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('return '):
            ret_val = stripped[7:].strip()
            returns.append(ret_val)
    
    if not returns:
        return 'None'
    
    # 检查是否返回 self
    if any(r == 'self' for r in returns):
        return "'Self'"
    
    # 常见字面量
    for ret in returns:
        if ret in RETURN_TYPE_MAP:
            return RETURN_TYPE_MAP[ret]
    
    # 返回函数调用
    if all(r.startswith('self.') or r.startswith('cls.') for r in returns):
        # 可能是链式调用
        return "'Self'"
    
    # boolean 运算符
    if any(op in ret for ret in returns for op in [' and ', ' or ', ' not ', 'is ', '==', '!=', '>', '<', 'in ']):
        return 'bool'
    
    # f-string / concat
    if any('f"' in ret or "f'" in ret or " + " in ret for ret in returns) and any('str' in r for r in returns if isinstance(r, str)):
        pass  # 保守，用 Any
    
    # 列表推导式
    if any(ret.startswith('[') for ret in returns):
        return 'list'
    
    return 'Any'


def has_return_statement(method_node) -> bool:
    """检查方法体是否有 return 语句"""
    for node in ast.walk(method_node):
        if isinstance(node, ast.Return):
            return True
    return False


def generate_docstring(method_name: str, return_type: str, is_property: bool = False) -> str:
    """根据方法名生成一句话 docstring"""
    # 中英文常见前缀映射
    doc_map = {
        'get': '获取',
        'set': '设置',
        'is_': '判断是否',
        'has_': '判断是否有',
        'to_': '转换为',
        'from_': '从创建',
        'add_': '添加',
        'remove_': '移除',
        'clear': '清空',
        'find': '查找',
        'search': '搜索',
        'parse': '解析',
        'validate': '验证',
        'check': '检查',
        'run': '运行',
        'start': '启动',
        'stop': '停止',
        'load': '加载',
        'save': '保存',
        'dump': '转储',
        'copy': '复制',
        'merge': '合并',
        'sort': '排序',
        'filter': '过滤',
        'map_': '映射',
        'reduce': '归约',
        'flat_map': '扁平映射',
        'subscribe': '订阅',
        'unsubscribe': '取消订阅',
        'on_next': '下一项回调',
        'on_error': '错误回调',
        'on_completed': '完成回调',
    }
    
    if is_property:
        return '"""属性值"""'
    
    for prefix, desc in doc_map.items():
        if method_name.startswith(prefix):
            rest = method_name[len(prefix):].lstrip('_')
            if rest:
                return f'"""{desc}{rest}"""'
            return f'"""{desc}"""'
    
    if return_type == 'None' or return_type == 'None':
        return '"""执行操作"""'
    
    return '"""获取值"""'


def fix_file(path: str) -> Tuple[int, int]:
    """修复单个文件，返回 (修复注解数, 修复docstring数)"""
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    
    tree = ast.parse(source)
    fixes_annot = 0
    fixes_doc = 0
    new_source = source
    
    # 从后往前修复，避免行号偏移
    fixes = []
    
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith('_'):
                    method_source = source.split('\n')[m.lineno-1:m.end_lineno]
                    method_body = '\n'.join(method_source)
                    is_property = any(
                        isinstance(d, ast.Name) and d.id == 'property'
                        for d in ast.iter_child_nodes(m) if isinstance(d, ast.Name)
                    ) or any(
                        isinstance(d, ast.Attribute) and d.attr == 'setter'
                        for d in ast.iter_child_nodes(m) if isinstance(d, ast.Attribute)
                    )
                    
                    # 修复返回注解
                    if m.returns is None and not m.name.startswith('__'):
                        ret_type = infer_return_type(method_body, m.name)
                        has_ret = has_return_statement(m)
                        if not has_ret:
                            ret_type = 'None'
                        
                        # 找到 def 行
                        def_line_idx = m.lineno - 1
                        def_line = source.split('\n')[def_line_idx]
                        if '(' in def_line and ')' in def_line:
                            # 在 ) 后插入 -> type
                            new_def = def_line.rstrip() + f' -> {ret_type}'
                            # 更精确：在 ) 后面插入
                            paren_end = def_line.rfind(')')
                            if paren_end != -1 and '->' not in def_line:
                                new_def = def_line[:paren_end+1] + f' -> {ret_type}' + def_line[paren_end+1:].rstrip(':') + ':'
                                new_lines = source.split('\n')
                                new_lines[def_line_idx] = new_def
                                new_source = '\n'.join(new_lines)
                                fixes_annot += 1
                    
                    # 修复 docstring
                    has_doc = bool(
                        m.body and isinstance(m.body[0], ast.Expr)
                        and isinstance(m.body[0].value, ast.Constant)
                    )
                    if not has_doc and not m.name.startswith('__'):
                        doc = generate_docstring(m.name, ret_type if m.returns else 'None', is_property)
                        lines = new_source.split('\n')
                        # 在 def 行后插入 docstring
                        indent = ' ' * (m.col_offset + 4)
                        insert_line = m.body[0].lineno - 1 if m.body else m.lineno
                        # 找到 def 行后第一个非空行
                        for i in range(m.lineno, len(lines)):
                            if lines[i].strip():
                                insert_line = i
                                break
                        lines.insert(insert_line, indent + doc)
                        new_source = '\n'.join(lines)
                        fixes_doc += 1
    
    # 写入
    if fixes_annot > 0 or fixes_doc > 0:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_source)
    
    return fixes_annot, fixes_doc


total_annot = 0
total_doc = 0
files_fixed = 0

for root, dirs, files in os.walk(base):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    for fn in files:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(root, fn)
        a, d = fix_file(path)
        if a > 0 or d > 0:
            files_fixed += 1
            total_annot += a
            total_doc += d
            print(f'  {os.path.relpath(path,base)}: annot={a} doc={d}')

print(f'\nFixed: {files_fixed} files, {total_annot} annotations, {total_doc} docstrings')
