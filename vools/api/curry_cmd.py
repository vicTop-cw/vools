"""
curry 子命令 - 函数柯里化 CLI

用法示例:
    vools curry --func "lambda x, y: x + y" --args 5 10
    vools curry --func "lambda a, b, c: a * b * c" --args 2 3 4
"""

from typing import Optional, List, Callable
import typer
from typing_extensions import Annotated

from vools.decorators import curry

curry_app = typer.Typer(help="Curry 柯里化命令")


def parse_lambda_or_func(expr: str):
    """解析 lambda 表达式或函数名"""
    try:
        return eval(expr, {"__builtins__": {}})
    except Exception:
        # 如果是函数名，尝试从全局查找
        import builtins
        if hasattr(builtins, expr):
            return getattr(builtins, expr)
        raise ValueError(f"无法解析表达式: {expr}")


@curry_app.command()
def call(
    func_expr: str = typer.Argument(..., help="函数表达式，如: lambda x, y: x + y"),
    args: List[str] = typer.Argument(..., help="函数参数"),
    kwargs: Annotated[
        Optional[List[str]],
        typer.Option("--kwargs", "-k", help="关键字参数，格式: key=value")
    ] = None,
):
    """调用柯里化函数"""
    func = parse_lambda_or_func(func_expr)
    
    # 解析参数
    parsed_args = []
    for arg in args:
        try:
            parsed_args.append(eval(arg, {"__builtins__": {}}))
        except Exception:
            parsed_args.append(arg)
    
    # 解析关键字参数
    parsed_kwargs = {}
    if kwargs:
        for kw in kwargs:
            if "=" in kw:
                key, value = kw.split("=", 1)
                try:
                    parsed_kwargs[key] = eval(value, {"__builtins__": {}})
                except Exception:
                    parsed_kwargs[key] = value
    
    # 应用 curry 装饰器
    curried_func = curry(func)
    
    # 调用
    if parsed_kwargs:
        result = curried_func(*parsed_args, **parsed_kwargs)
    else:
        result = curried_func(*parsed_args)
    
    typer.echo(f"结果: {result}")
    return result


@curry_app.command()
def curry_func(
    func_expr: str = typer.Argument(..., help="函数表达式"),
):
    """将函数柯里化并显示"""
    func = parse_lambda_or_func(func_expr)
    curried = curry(func)
    typer.echo(f"原始函数: {func}")
    typer.echo(f"柯里化函数: {curried}")
    
    # 尝试调用示例
    try:
        if hasattr(func, "__code__") and func.__code__.co_argcount >= 2:
            # 如果是多参数函数，展示分步调用
            args_example = ["arg1", "arg2"]
            typer.echo(f"\n示例调用:")
            typer.echo(f"  curried({args_example[0]}) = {curried(args_example[0])}")
    except Exception as e:
        typer.echo(f"无法展示示例: {e}")
    
    return curried


if __name__ == "__main__":
    typer.run(call)
