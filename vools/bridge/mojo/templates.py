"""
vools.bridge.mojo.templates - Mojo 代码模板生成

负责生成符合 cdecl 边界的 Mojo 函数包装代码：
- @export("func_name") 装饰器
- def name(...) -> RetType abi("C"):
- 数组参数自动展开为 (ptr, length) 两个形参
- auto_signature 时剥离 # 注释行

运行环境：Mojo 1.0b1（WSL Linux）。
"""

import re
from typing import List, Tuple, Optional


def generate_function_signature(
    func_name: str,
    params: List[Tuple[str, str]],
    ret_type: str = 'Int64',
    export_name: Optional[str] = None,
) -> str:
    """
    生成 Mojo 函数签名（不含函数体）

    参数：
        func_name: 函数名（Python 端使用）
        params: [(param_name, mojo_type), ...] 形参列表
        ret_type: 返回类型 Mojo 字符串；'None' 表示无返回值
        export_name: 导出名称（None 则用 func_name）

    返回：
        Mojo 签名字符串（含 @export 装饰器 + def 头 + 冒号）
    """
    export = export_name or func_name
    # 形参列表
    if params:
        param_str = ', '.join(f'{pname}: {ptype}' for pname, ptype in params)
    else:
        param_str = ''

    if ret_type in (None, 'None', 'void'):
        sig = (
            f'@export("{export}")\n'
            f'def {func_name}({param_str}) abi("C"):'
        )
    else:
        sig = (
            f'@export("{export}")\n'
            f'def {func_name}({param_str}) -> {ret_type} abi("C"):'
        )
    return sig


def generate_mojo_wrapper(
    func_name: str,
    body: str,
    params: List[Tuple[str, str]],
    ret_type: str = 'Int64',
    export_name: Optional[str] = None,
) -> str:
    """
    生成完整的 Mojo 函数包装代码

    参数：
        func_name: 函数名
        body: 函数体字符串
        params: 形参列表
        ret_type: 返回类型
        export_name: 导出名称

    返回：
        完整 Mojo 源码字符串
    """
    sig = generate_function_signature(func_name, params, ret_type, export_name)
    indented = _indent_block(body, prefix='    ')
    return f'{sig}\n{indented}\n'


def _indent_block(text: str, prefix: str = '    ') -> str:
    """对文本块每行加缩进，保留空行"""
    lines = text.splitlines() if text else ['']
    out = []
    for line in lines:
        if line.strip() == '':
            out.append('')
        else:
            out.append(f'{prefix}{line}')
    return '\n'.join(out)


def preprocess_mojo_body(body: str) -> str:
    """
    预处理函数体字符串，剥离 # 注释行（用于 auto_signature 模式）

    与 fbc.py 行为一致：
    - 以 `#` 开头的行保留在签名外部（被剥离到函数体外）
    - 其他行作为函数体保留

    参数：
        body: 原始函数体字符串

    返回：
        剥离 # 注释行后的函数体字符串
    """
    out_lines = []
    for line in body.splitlines():
        if line.strip().startswith('#'):
            # 跳过 # 注释行
            continue
        out_lines.append(line)
    return '\n'.join(out_lines)


def split_preprocessor_and_body(body: str) -> Tuple[List[str], List[str]]:
    """
    分离预处理指令（imports 等）与函数体（与 fbc.py::generate_fbc_code 行为对齐）

    返回：
        (preprocessor_lines, function_body_lines)
    """
    preprocessor_lines = []
    function_body_lines = []
    for line in body.strip().split('\n'):
        line = line.strip()
        if not line:
            preprocessor_lines.append('')
            continue
        if line.startswith('#'):
            preprocessor_lines.append(line)
        else:
            function_body_lines.append(line)
    return preprocessor_lines, function_body_lines
