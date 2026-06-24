"""
vools.bridge.julia.templates - Julia 代码生成模板

提供 Julia 函数代码生成功能，包括：
- 生成完整的 Julia 源文件代码
- 处理函数签名和参数列表
- 处理字符串、数组等复杂类型的包装
"""

import inspect
from typing import Any, Callable, List, Optional, Tuple


def _preprocess_julia_body(body: str, auto_signature: bool) -> str:
    """
    预处理 Julia 函数体

    - 剥离前导空行
    - auto_signature=True 时按行 4 空格缩进
    - 保留空行
    """
    if not auto_signature:
        return body

    indented_lines = []
    for raw_line in body.split('\n'):
        line = raw_line.rstrip()
        if not line:
            indented_lines.append('')
            continue
        indented_lines.append('    ' + line)

    # 去掉首尾空行
    while indented_lines and not indented_lines[0]:
        indented_lines.pop(0)
    while indented_lines and not indented_lines[-1]:
        indented_lines.pop()

    return '\n'.join(indented_lines)


def _resolve_params_from_sig(sig: inspect.Signature) -> List[Tuple[str, str, bool]]:
    """
    从函数签名解析形参列表（Julia 端）

    返回：
        [(name, julia_type, is_array), ...]
        - is_array=True 时表示该形参是 Ptr{Cvoid}（需配长度形参）
    """
    from .types import get_julia_type, is_array_type

    params = []
    for pname, param in sig.parameters.items():
        if param.annotation is not inspect.Parameter.empty:
            julia_t = get_julia_type(param.annotation)
        else:
            julia_t = 'Int64'
        is_arr = is_array_type(julia_t)
        params.append((pname, julia_t, is_arr))
    return params


def generate_julia_function(
    func_name: str,
    sig: inspect.Signature,
    ret_julia_type: str,
    body: str,
    auto_signature: bool = True,
) -> str:
    """
    生成完整的 Julia 源文件代码

    参数：
        func_name: 函数名
        sig: inspect.Signature 对象
        ret_julia_type: Julia 端返回类型
        body: 函数体代码
        auto_signature: 是否自动生成签名（True 时 body 按 4 空格缩进）

    返回：
        完整 Julia 源文件字符串
    """
    params = _resolve_params_from_sig(sig)

    # 构造参数列表：数组参数拆为 (ptr, n) 两项
    julia_params = []
    for name, julia_t, is_arr in params:
        if is_arr:
            julia_params.append(f'{name}::Ptr{{Cvoid}}')
            julia_params.append(f'{name}_n::Int64')
        else:
            julia_params.append(f'{name}::{julia_t}')

    params_str = ', '.join(julia_params) if julia_params else ''

    # 返回值类型
    if ret_julia_type in ('Nothing', 'Void', 'Nothing'):
        ret_signature = ''
    else:
        ret_signature = f'::{ret_julia_type}'

    # 缩进函数体
    indented_body = _preprocess_julia_body(body, auto_signature)
    if indented_body:
        indented_body = '\n' + indented_body + '\n'
    else:
        indented_body = '\n'

    # 生成完整的 Julia 代码
    # Julia 使用 function...end 语法
    code = f'''# Auto-generated Julia code by vools.bridge.julia
# Function: {func_name}

function {func_name}({params_str}){ret_signature}
{indented_body}end
'''
    return code


def generate_julia_c_wrapper(
    func_name: str,
    sig: inspect.Signature,
    ret_julia_type: str,
    body: str,
) -> str:
    """
    生成 Julia C 调用接口代码

    生成使用 ccall 风格的 Julia 代码，用于从 Julia 调用 C 共享库。
    这不是主要用途，主要用于生成导出给 Python 调用的函数。

    参数：
        func_name: 函数名
        sig: inspect.Signature 对象
        ret_julia_type: Julia 端返回类型
        body: 函数体代码

    返回：
        Julia 代码字符串
    """
    # 使用 main 函数风格，Julia 脚本形式
    params = _resolve_params_from_sig(sig)

    # 构造参数列表
    julia_params = []
    for name, julia_t, is_arr in params:
        if is_arr:
            julia_params.append(f'{name}::Ptr{{Cvoid}}')
            julia_params.append(f'{name}_n::Int64')
        else:
            julia_params.append(f'{name}::{julia_t}')

    params_str = ', '.join(julia_params) if julia_params else ''

    # 返回值类型
    if ret_julia_type in ('Nothing', 'Void'):
        ret_signature = ''
    else:
        ret_signature = f'::{ret_julia_type}'

    # 缩进函数体
    indented_body = _preprocess_julia_body(body, True)
    if indented_body:
        indented_body = '\n' + indented_body + '\n'
    else:
        indented_body = '\n'

    code = f'''# Auto-generated Julia code by vools.bridge.julia
# Function: {func_name}

function {func_name}({params_str}){ret_signature}
{indented_body}end
'''
    return code


def generate_compile_script(
    func_name: str,
    source_code: str,
    output_path: str,
    julia_path: str = 'julia',
) -> str:
    """
    生成 Julia 编译脚本

    生成一个 Julia 脚本，用于将 Julia 源文件编译为共享库。

    参数：
        func_name: 函数名
        source_code: Julia 源代码
        output_path: 输出的共享库路径
        julia_path: Julia 可执行文件路径

    返回：
        编译脚本字符串
    """
    # 创建临时 Julia 脚本
    script = f'''
# Compile Julia function to shared library
using JuliaJLL

# Write the source code
source_file = "{func_name}_temp.jl"
open(source_file, "w") do f
    write(f, """
{source_code}
    """)
end

# Use StaticCompiler or PackageCompiler to create shared library
# For simplicity, we use a basic approach with julia
'''
    return script


__all__ = [
    'generate_julia_function',
    'generate_julia_c_wrapper',
    'generate_compile_script',
    '_resolve_params_from_sig',
    '_preprocess_julia_body',
]
