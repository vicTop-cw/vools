"""
vools.bridge.cangjie.templates - 仓颉代码生成模板

提供仓颉代码自动生成功能,包括函数签名、package 声明、@C 注解等。

设计目标:
- 从 Python 函数签名自动生成仓颉函数声明
- 生成符合 C ABI 的导出函数(@C 注解)
- 支持自动签名和手动签名两种模式
"""

from .types import get_cj_type


def generate_cj_signature(func_name, param_names, param_types, return_type):
    """
    生成仓颉函数签名

    参数:
        func_name: 函数名
        param_names: 参数名列表
        param_types: 仓颉参数类型列表
        return_type: 仓颉返回类型

    返回:
        函数签名字符串
    """
    params = []
    for name, cj_type in zip(param_names, param_types):
        params.append(f'{name}: {cj_type}')

    params_str = ', '.join(params)

    if return_type == 'Unit':
        return f'func {func_name}({params_str}): {return_type}'
    else:
        return f'func {func_name}({params_str}): {return_type}'


def generate_cj_code(
    func_name,
    param_names,
    param_types,
    return_type,
    body,
    package_name=None,
    include_c_annotation=True
):
    """
    生成完整的仓颉代码

    参数:
        func_name: 函数名
        param_names: 参数名列表
        param_types: 仓颉参数类型列表
        return_type: 仓颉返回类型
        body: 函数体代码
        package_name: 包名(默认使用函数名)
        include_c_annotation: 是否包含 @C 注解

    返回:
        完整的仓颉代码字符串
    """
    if package_name is None:
        package_name = func_name

    # 生成函数签名
    signature = generate_cj_signature(func_name, param_names, param_types, return_type)

    # 处理函数体缩进
    indented_body = ''
    for line in body.split('\n'):
        if line.strip():
            indented_body += '    ' + line + '\n'
        else:
            indented_body += '\n'

    # 生成 @C 注解(如果需要)
    c_annotation = '@C\n' if include_c_annotation else ''

    # 组合完整代码
    code = f'''package {package_name}

{c_annotation}{signature} {{
{indented_body}}}
'''

    return code


def generate_from_python_func(func, body, auto_signature=True):
    """
    从 Python 函数生成仓颉代码

    参数:
        func: Python 函数对象
        body: 仓颉函数体代码
        auto_signature: 是否自动生成签名

    返回:
        完整的仓颉代码字符串
    """
    import inspect

    func_name = func.__name__
    sig = inspect.signature(func)

    # 获取参数信息
    param_names = []
    param_types = []

    for name, param in sig.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        param_names.append(name)

        # 从注解获取类型
        if param.annotation is not param.empty:
            param_types.append(get_cj_type(param.annotation))
        else:
            param_types.append('Int64')  # 默认类型

    # 获取返回类型
    return_type = 'Unit'
    if sig.return_annotation is not sig.empty:
        return_type = get_cj_type(sig.return_annotation)

    # 生成代码
    return generate_cj_code(
        func_name,
        param_names,
        param_types,
        return_type,
        body,
        package_name=func_name,
        include_c_annotation=True
    )


class CangjieCodeGenerator:
    """仓颉代码生成器类"""

    def __init__(self, package_name=None):
        self.package_name = package_name

    def generate_function(self, func_name, params, return_type, body):
        """
        生成单个函数

        参数:
            func_name: 函数名
            params: 参数列表 [(name, type), ...]
            return_type: 返回类型
            body: 函数体

        返回:
            仓颉代码字符串
        """
        param_names = [p[0] for p in params]
        param_types = [p[1] for p in params]

        return generate_cj_code(
            func_name,
            param_names,
            param_types,
            return_type,
            body,
            self.package_name
        )

    def generate_module(self, functions):
        """
        生成包含多个函数的模块

        参数:
            functions: 函数列表 [(name, params, return_type, body), ...]

        返回:
            仓颉代码字符串
        """
        if self.package_name is None:
            self.package_name = 'cangjie_module'

        code_lines = [f'package {self.package_name}', '']

        for func_name, params, return_type, body in functions:
            param_names = [p[0] for p in params]
            param_types = [p[1] for p in params]

            signature = generate_cj_signature(func_name, param_names, param_types, return_type)

            # 处理函数体缩进
            indented_body = ''
            for line in body.split('\n'):
                if line.strip():
                    indented_body += '    ' + line + '\n'
                else:
                    indented_body += '\n'

            code_lines.append('@C')
            code_lines.append(f'{signature} {{')
            code_lines.append(indented_body.rstrip())
            code_lines.append('}')
            code_lines.append('')

        return '\n'.join(code_lines)