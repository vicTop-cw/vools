import re
from typing import Dict, Any, Optional, List, Callable
__all__ = ["arrow_func",'g','_eval_expr_with_semicolon']
# Arrow 表达式模式
arrow_pattern = r'^\s*([^;]*?)\s*=>\s*(.+)$'

def parse_arrow_expr(expr: str) -> tuple:
    """解析 arrow 表达式"""
    expr = expr.strip()
    match = re.match(arrow_pattern, expr)
    if not match:
        return [], ""
    
    params_str = match.group(1).strip()
    body_str = match.group(2).strip()
    
    # 解析参数列表
    params = []
    if params_str:
        # 按逗号分割参数，处理 *args 和 **kwargs
        raw_params = [p.strip() for p in params_str.split(',') if p.strip()]
        
        for param in raw_params:
            if param.startswith('**'):
                # **kwargs
                param_name = param[2:].strip()
                if param_name:
                    params.append(('**', param_name))
            elif param.startswith('*'):
                # *args
                param_name = param[1:].strip()
                if param_name:
                    params.append(('*', param_name))
            else:
                # 普通参数
                params.append(('', param))
    
    return params, body_str

def convert_ternary(expression):
    """
    将类C的三元运算符(a ? b ! c)转换为Python的三元运算符(b if a else c)
    """
    import re
    
    # 处理嵌套的三元运算符
    while '?' in expression:
        # 找到最内层的三元运算符
        match = re.search(r'\(([^()]+)\?([^()]+)\!([^()]+)\)', expression)
        if not match:
            # 处理没有括号的情况
            match = re.search(r'([^?]+)\?([^!]+)\!([^!]+)$', expression)
            if not match:
                break
                
        full_match = match.group(0) if match.group(0).startswith('(') else match.group(0)
        condition = match.group(1).strip()
        true_expr = match.group(2).strip()
        false_expr = match.group(3).strip()
        
        # 转换格式
        converted = f"({true_expr} if {condition} else {false_expr})"
        
        # 替换原表达式中的部分
        expression = expression.replace(full_match, converted)
    
    return expression


def create_arrow_function(params: List[tuple], body: str, env: Dict[str, Any],body_sep :str = ';') -> Callable:
    """创建 arrow 函数"""
    
    # 构建参数列表
    normal_params = []
    args_param = None
    kwargs_param = None
    
    for param_type, param_name in params:
        if param_type == '*':
            args_param = param_name
        elif param_type == '**':
            kwargs_param = param_name
        else:
            normal_params.append(param_name)
    if body_sep != ';':
        # body = re.sub(body_sep,';',body)
        body = body.replace(body_sep,';')
    # 构建函数体
    if ';' in body:
        # 多语句函数体
        statements = [s.strip() for s in body.split(';') if s.strip()]
        if statements:
            # 最后一条语句作为返回值
            last_stmt = statements[-1]
            other_stmts = statements[:-1]
            
            # 构建函数代码
            code_lines = []
            for stmt in other_stmts:
                code_lines.append(f"    {stmt}")
            
            if last_stmt:
                code_lines.append(f"    return {last_stmt}")
            else:
                code_lines.append("    pass")
            
            func_body = "\n".join(code_lines)
        else:
            func_body = "    pass"
    else:
        # 单表达式函数体
        func_body = f"    return {body}"
    
    # 构建完整的函数定义
    param_parts = []
    
    # 添加普通参数
    if normal_params:
        param_parts.append(", ".join(normal_params))
    
    # 添加 *args 参数
    if args_param:
        param_parts.append(f"*{args_param}")
    
    # 添加 **kwargs 参数
    if kwargs_param:
        param_parts.append(f"**{kwargs_param}")
    
    param_str = ", ".join(param_parts)
    func_def = f"def arrow_func({param_str}):\n{func_body}"
    
    # 执行函数定义
    try:
        exec(func_def, env)
        return env['arrow_func']
    except Exception as e:
        # 如果失败，尝试创建简单的lambda
        lambda_params = []
        
        # 添加普通参数
        if normal_params:
            lambda_params.extend(normal_params)
        
        # 添加 *args 参数
        if args_param:
            lambda_params.append(f"*{args_param}")
        
        # 添加 **kwargs 参数
        if kwargs_param:
            lambda_params.append(f"**{kwargs_param}")
        
        param_str = ", ".join(lambda_params)
        
        # 构建lambda表达式
        if ';' in body:
            # 对于多语句，只取最后一条作为返回值
            statements = [s.strip() for s in body.split(';') if s.strip()]
            if statements:
                lambda_body = statements[-1]
            else:
                lambda_body = "None"
        else:
            lambda_body = body
        
        lambda_expr = f"lambda {param_str}: {lambda_body}"
        
        try:
            return eval(lambda_expr, env)
        except Exception as e2:
            # 如果还是失败，创建一个简单的包装函数
            def wrapper(*args, **kwargs):
                # 创建一个局部环境
                local_env = env.copy()
                
                # 将参数添加到局部环境
                for i, param in enumerate(normal_params):
                    if i < len(args):
                        local_env[param] = args[i]
                
                if args_param:
                    local_env[args_param] = args[len(normal_params):]
                
                if kwargs_param:
                    local_env[kwargs_param] = kwargs
                
                # 执行函数体
                if ';' in body:
                    statements = [s.strip() for s in body.split(';') if s.strip()]
                    for stmt in statements[:-1]:
                        exec(stmt, local_env)
                    if statements:
                        return eval(statements[-1], local_env)
                    return None
                else:
                    return eval(body, local_env)
            
            return wrapper

def arrow_func(expr: str, env: Optional[Dict[str, Any]] = None) -> Callable:
    """
    根据 arrow 表达式生成可调用函数
    
    Args:
        expr: arrow 表达式，格式为 "参数 => 函数体"
        env: 执行环境字典，包含可用的变量和函数
    
    Returns:
        可调用的函数对象
    """
    if env is None:
        env = {}
    
    # 确保env中有基本的Python内置函数
    if '__builtins__' not in env:
        env['__builtins__'] = __builtins__
    
    # 解析表达式
    params, body = parse_arrow_expr(expr)
    if '\n' in body:
        body = body.replace('\n', ';')
    # 转换三元运算符
    if "?" in body:
        bodies = body.split(';')
        for i in range(len(bodies)):
            if not "?" in bodies[i]:
                continue
            bodies[i] = convert_ternary(bodies[i])
        body = ';'.join(bodies)
    # 创建函数
    return create_arrow_function(params, body, env)





def _eval_expr_with_semicolon(expr: str, env: Dict) -> Any:
    """
    执行可能包含分号的表达式，返回最后一个表达式的结果
    如果以分号结尾，返回None
    """
    if not expr:
        return None
    
    # 检查是否以分号结尾
    ends_with_semicolon = expr.strip().endswith(';')
    
    # 按分号分割表达式
    statements = [stmt.strip() for stmt in expr.split(';')]
    
    # 移除空语句
    statements = [stmt for stmt in statements if stmt]
    
    if not statements:
        return None
    
    # 创建一个新的字典来存储局部变量
    local_vars = {} #env.copy()
    
    # 执行所有语句
    for i, stmt in enumerate(statements):
        try:
            # 如果是赋值语句，使用exec
            if '=' in stmt and not stmt.strip().startswith('='):
                # 赋值语句
                exec(stmt, env, local_vars)
            else:
                # 表达式语句，使用eval
                result = eval(stmt, env, local_vars)
                # 如果是最后一个语句且不以分号结尾，返回结果
                if i == len(statements) - 1 and not ends_with_semicolon:
                    return result
        except Exception as e:
            print(f"Warning: Failed to execute statement '{stmt}': {e}")
    
    # 如果以分号结尾或最后一个语句是赋值语句，返回None
    return None

def gene_lambda_func(expr: str, mode='single', env=None):
    """
    生成支持多元参数的函数
    
    参数:
    expr: 字符串表达式
    mode: 
        'single' - 每个独立的 '_' 视为一个参数（按顺序对应）
        'indexed' - 使用 '_n' 格式，数字 n 表示参数位置（n>=1）
    env: 执行环境变量字典，默认为None
    
    返回: lambda 函数
    
    示例:
    # 模式1: 独立的下划线
    f1 = gene_lambda_func('_ + 2 * _', mode='single')
    print(f1(3, 4))  # 11

    f2 = gene_lambda_func('_ and _', mode='single')
    print(f2(True, False))  # False

    # 模式2: 带索引的下划线
    f3 = gene_lambda_func('_1 + 2*_2', mode='indexed')
    print(f3(3, 4))  # 11

    f4 = gene_lambda_func('_1 and _3', mode='indexed')
    print(f4(True, 0, False))  # False

    # 混合模式示例
    f5 = gene_lambda_func('_2 and _3 and _1 > 0 and _1 < 10', mode='indexed')
    print(f5(5, True, True))  # True
    
    # 支持分号分隔的多个语句
    f6 = gene_lambda_func('x = _1 + _2; y = x * 2; y', mode='indexed')
    print(f6(3, 4))  # 14
    
    # 使用自定义环境变量
    custom_env = {'multiplier': 3}
    f7 = gene_lambda_func('_1 * multiplier', mode='indexed', env=custom_env)
    print(f7(5))  # 15
    """
    
    # 如果env为None，初始化为空字典
    if env is None:
        env = {}
    
    # 检查是否包含分号
    if ';' in expr:
        # 如果有分号，使用 _eval_expr_with_semicolon 处理
        if mode == 'single':
            pattern = r'(?<!\w)_(?!\w)'
            matches = list(re.finditer(pattern, expr))
            num_params = len(matches)
            
            if num_params == 0:
                # 创建无参函数，支持分号
                def func_with_semicolon():
                    local_env = env.copy()
                    return _eval_expr_with_semicolon(expr, local_env)
                return func_with_semicolon
            
            arg_names = [f'x{i}' for i in range(num_params)]
            
            # 替换表达式中的占位符
            parts = []
            last_idx = 0
            for i, match in enumerate(matches):
                start, end = match.span()
                parts.append(expr[last_idx:start])
                parts.append(arg_names[i])
                last_idx = end
            parts.append(expr[last_idx:])
            
            new_expr = ''.join(parts)
            
            # 创建支持分号的函数
            def func_with_semicolon(*args):
                if len(args) != num_params:
                    raise ValueError(f"期望 {num_params} 个参数，但得到了 {len(args)} 个")
                
                local_env = env.copy()
                for i, arg in enumerate(args):
                    local_env[arg_names[i]] = arg
                
                return _eval_expr_with_semicolon(new_expr, local_env)
            
            return func_with_semicolon
        
        elif mode == 'indexed':
            # 提取所有索引参数
            pattern = r'(?<!\w)_(0*[1-9]\d*)(?!\w)'
            matches = list(re.finditer(pattern, expr))
            
            if not matches:
                # 创建无参函数，支持分号
                def func_with_semicolon():
                    local_env = env.copy()
                    return _eval_expr_with_semicolon(expr, local_env)
                return func_with_semicolon
            
            indices = [int(match.group(1)) for match in matches]
            max_index = max(indices)
            arg_names = [f'x{i}' for i in range(max_index)]
            
            # 替换表达式中的占位符
            parts = []
            last_idx = 0
            for match in matches:
                start, end = match.span()
                idx = int(match.group(1)) - 1
                parts.append(expr[last_idx:start])
                parts.append(arg_names[idx])
                last_idx = end
            parts.append(expr[last_idx:])
            
            new_expr = ''.join(parts)
            
            # 创建支持分号的函数
            def func_with_semicolon(*args):
                if len(args) < max_index:
                    raise ValueError(f"期望至少 {max_index} 个参数，但得到了 {len(args)} 个")
                
                local_env = env.copy()
                for i, arg in enumerate(args):
                    if i < max_index:
                        local_env[arg_names[i]] = arg
                
                return _eval_expr_with_semicolon(new_expr, local_env)
            
            return func_with_semicolon
    
    else:
        # 如果没有分号，使用原来的逻辑
        if mode == 'single':
            pattern = r'(?<!\w)_(?!\w)'
            matches = list(re.finditer(pattern, expr))
            num_params = len(matches)
            
            if num_params == 0:
                return eval(f'lambda: {expr}', env, {})
            
            arg_names = [f'x{i}' for i in range(num_params)]
            
            parts = []
            last_idx = 0
            for i, match in enumerate(matches):
                start, end = match.span()
                parts.append(expr[last_idx:start])
                parts.append(arg_names[i])
                last_idx = end
            parts.append(expr[last_idx:])
            
            new_expr = ''.join(parts)
            lambda_str = f'lambda {", ".join(arg_names)}: {new_expr}'
            return eval(lambda_str, env, {})
        
        elif mode == 'indexed':
            pattern = r'(?<!\w)_(0*[1-9]\d*)(?!\w)'
            matches = list(re.finditer(pattern, expr))
            
            if not matches:
                return eval(f'lambda: {expr}', env, {})
            
            indices = [int(match.group(1)) for match in matches]
            max_index = max(indices)
            arg_names = [f'x{i}' for i in range(max_index)]
            
            parts = []
            last_idx = 0
            for match in matches:
                start, end = match.span()
                idx = int(match.group(1)) - 1
                parts.append(expr[last_idx:start])
                parts.append(arg_names[idx])
                last_idx = end
            parts.append(expr[last_idx:])
            
            new_expr = ''.join(parts)
            lambda_str = f'lambda {", ".join(arg_names)}: {new_expr}'
            return eval(lambda_str, env, {})
    
    raise ValueError(f"无效的模式: {mode}. 请使用 'single' 或 'indexed'")


def g(expr: str, env: Dict = None) -> Any:
    """
    通用函数生成器，支持多种表达式格式
    
    参数:
    expr: 字符串表达式，支持以下格式:
        - "x,y => x + y" : lambda表达式格式
        - "_ + 2 * _" : 使用下划线占位符
        - "_1 + _2" : 使用带索引的下划线
        - "lambda x: x + 1" : 标准lambda表达式
    env: 执行环境变量字典
    
    返回: 生成的函数
    
    示例:
    f1 = g("x,y => x + y")
    print(f1(3, 4))  # 7
    
    f2 = g("_ + 2 * _")
    print(f2(3, 4))  # 11
    
    f3 = g("_1 + _2")
    print(f3(3, 4))  # 7
    
    f4 = g("lambda x: x + 1")
    print(f4(5))  # 6
    """
    if env is None:
        env = {}
    
    # 如果已经是函数，直接返回
    if callable(expr):
        return expr
    
    # 检查是否是标准lambda表达式
    pattern3 = r"lambda\s+\w+\s*:\s*"
    if re.match(pattern3, expr):
        return eval(expr, env)
    
    # 检查是否包含 "=>" (lambda表达式格式)
    if "=>" in expr:
        a,b = expr.split("=>",1)
        if '\n' in b:
            b = b.strip().replace('\n',';')
        return arrow_func(f"{a.strip()}=>{b}", env)
    
    if "?" in expr:
        expr = convert_ternary(expr)
    # 检查下划线模式
    pattern1 = r'(?<!\w)_(?!\w)'  # 独立下划线
    pattern2 = r'(?<!\w)_(0*[1-9]\d*)(?!\w)'  # 带索引的下划线
    
    matches1 = list(re.finditer(pattern1, expr))
    matches2 = list(re.finditer(pattern2, expr))
    
    l1, l2 = len(matches1), len(matches2)
    
    # 如果两种模式都不匹配，创建无参函数
    if l1 == 0 and l2 == 0:
        return eval(f"lambda: {expr}", env, {})
    
    # 如果两种模式都匹配，报错
    if l1 > 0 and l2 > 0:
        raise ValueError(f"表达式 '{expr}' 中同时包含独立下划线和带索引的下划线，请只使用一种模式")
    
    # 根据模式调用gene_lambda_func
    mode = "single" if l1 > 0 else "indexed"
    return gene_lambda_func(expr, mode, env)

# 测试代码
if __name__ == "__main__":
    import random
    
    # 测试环境
    test_env = {'random': random, 'sum': sum}
    
    # 测试无参函数
    print("=== 无参函数测试 ===")
    f1 = arrow_func(" => random.randint(0, 10)", test_env)
    print(f"无参函数: {f1()}")  # 0-10之间的随机数
    
    # 测试单参函数
    print("\n=== 单参函数测试 ===")
    f2 = arrow_func("x => y = x + 1; y", test_env)
    print(f"单参函数: {f2(5)}")  # 6
    
    # 测试多参数函数
    print("\n=== 多参数函数测试 ===")
    f3 = arrow_func("x, y, *args, **kwargs => sm = sum(args); ksm = sum([i for i in kwargs.values()]); sm + ksm + x + y", test_env)
    print(f"多参数函数: {f3(1, 2, 3, 4, a=5, b=6)}")  # 1+2+3+4+5+6 = 21
    
    # 测试只有*args
    print("\n=== 只有*args测试 ===")
    f4 = arrow_func("*args => sum(args)", test_env)
    print(f"只有*args: {f4(1, 2, 3, 4)}")  # 10
    
    # 测试只有**kwargs
    print("\n=== 只有**kwargs测试 ===")
    f5 = arrow_func("**kwargs => sum(kwargs.values())", test_env)
    print(f"只有**kwargs: {f5(a=1, b=2, c=3)}")  # 6
    
    # 测试复杂函数体
    print("\n=== 复杂函数体测试 ===")
    f6 = arrow_func("x, y => result = x * y; result = result + 10; result", test_env)
    print(f"复杂函数体: {f6(3, 4)}")  # 3 * 4+10=22
    
    # 测试空函数体
    print("\n=== 空函数体测试 ===")
    f7 = arrow_func(" => ", test_env)
    print(f"空函数体: {f7()}")  # None
    
    # 测试在环境中使用变量
    print("\n=== 环境变量测试 ===")
    test_env['base'] = 10
    f8 = arrow_func("x => x + base", test_env)
    print(f"使用环境变量: {f8(5)}")  # 15
    
    # 测试混合参数
    print("\n=== 混合参数测试 ===")
    f9 = arrow_func("a, b, *args, **kwargs => a + b + sum(args) + sum(kwargs.values())", test_env)
    print(f"混合参数: {f9(1, 2, 3, 4, x=5, y=6)}")  # 1+2+3+4+5+6=21
    from inspect import signature
    f10 = arrow_func("""
                     a,b,*z,**k =>
                     sm = sum(z)
                     ksm = sum(k.values())
                     a+b+sm+ksm""".strip().replace("\n",";"),test_env)
    print(f"混合参数: {f10(1, 2, 3, 4, x=5, y=6)}")  # 1+2+3+4+5+6=21
    sig = signature(f10)
    print(sig)
    f11 = g("a,b,*z,**k => a+b+sum(z)+sum(k.values())", test_env)
    print(f"混合参数: {f11(1, 2, 3, 4, x=5, y=6)}")  # 1+2+3+4+5+6=21
    sig = signature(f11)
    print(sig)
    f12 = g("a,b,*z,**k => a < b ? sum(z) + sum(k.values()) ! sum(z) * sum(k.values()) ", test_env)
    print(f"kkkkk: {f12(1, 2, 3, 4, x=5, y=6)}")  