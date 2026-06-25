"""
ops 子命令 - Ops 管道操作 CLI

用法示例:
    vools ops --pipe 1 2 3 4 5 --filter "lambda x: x % 2 == 0"
    vools ops --pipe 1 2 3 4 5 --map "lambda x: x * 2" --sum
    vools ops --pipe 1 2 3 4 5 6 7 8 9 10 --filter "lambda x: x % 2 == 0" --map "lambda x: x ** 2" --sum
"""

from typing import Optional, List, Callable
import typer
from typing_extensions import Annotated

from ..functional import Ops, O

ops_app = typer.Typer(help="Ops 管道操作命令")


def parse_lambda(expr: str) -> Callable:
    """解析 lambda 表达式字符串"""
    return eval(expr, {"__builtins__": {}})


@ops_app.command()
def pipe(
    items: List[int] = typer.Argument(..., help="输入数据列表"),
    filter_expr: Annotated[
        Optional[str],
        typer.Option("--filter", "-f", help="过滤表达式")
    ] = None,
    map_expr: Annotated[
        Optional[str],
        typer.Option("--map", "-m", help="映射表达式")
    ] = None,
    sum_flag: bool = typer.Option(False, "--sum/--no-sum", help="求和"),
    min_flag: bool = typer.Option(False, "--min/--no-min", help="最小值"),
    max_flag: bool = typer.Option(False, "--max/--no-max", help="最大值"),
    count_flag: bool = typer.Option(False, "--count/--no-count", help="计数"),
    collect_flag: bool = typer.Option(True, "--collect/--no-collect", help="收集为列表"),
):
    """管道操作"""
    result = items
    
    if filter_expr:
        result = result | Ops.filter(parse_lambda(filter_expr))
    
    if map_expr:
        result = result | Ops.map(parse_lambda(map_expr))
    
    if sum_flag:
        result = result | Ops.sum
        typer.echo(f"求和结果: {result}")
        return result
    
    if min_flag:
        result = result | Ops.min
        typer.echo(f"最小值: {result}")
        return result
    
    if max_flag:
        result = result | Ops.max
        typer.echo(f"最大值: {result}")
        return result
    
    if count_flag:
        result = result | Ops.count
        typer.echo(f"计数: {result}")
        return result
    
    if collect_flag:
        result = result | Ops.as_list
        typer.echo(f"结果: {result}")
        return result
    
    typer.echo(f"结果: {result}")
    return result


@ops_app.command()
def filter_op(
    items: List[int] = typer.Argument(..., help="输入数据列表"),
    expr: str = typer.Argument(..., help="过滤表达式"),
):
    """管道过滤操作"""
    result = items | Ops.filter(parse_lambda(expr)) | Ops.as_list
    typer.echo(f"过滤结果: {result}")
    return result


@ops_app.command()
def map_op(
    items: List[int] = typer.Argument(..., help="输入数据列表"),
    expr: str = typer.Argument(..., help="映射表达式"),
):
    """管道映射操作"""
    result = items | Ops.map(parse_lambda(expr)) | Ops.as_list
    typer.echo(f"映射结果: {result}")
    return result


@ops_app.command()
def sum_op(
    items: List[int] = typer.Argument(..., help="输入数据列表"),
):
    """管道求和操作"""
    result = items | Ops.sum
    typer.echo(f"求和结果: {result}")
    return result


if __name__ == "__main__":
    typer.run(pipe)
