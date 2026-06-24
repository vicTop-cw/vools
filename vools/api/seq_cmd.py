"""
seq 子命令 - Seq 序列操作 CLI

用法示例:
    vools seq --from-range 10 --filter "lambda x: x % 2 == 0"
    vools seq --from-list 1 2 3 4 5 --map "lambda x: x * 2"
    vools seq --from-range 20 --filter "lambda x: x % 2 == 0" --map "lambda x: x ** 2" --collect
"""

from typing import Optional, List, Callable
import typer
from typing_extensions import Annotated

from vools.data import Seq

seq_app = typer.Typer(help="Seq 序列操作命令")


def parse_lambda(expr: str) -> Callable:
    """解析 lambda 表达式字符串"""
    return eval(expr, {"__builtins__": {}})


@seq_app.command()
def from_range(
    count: int = typer.Argument(..., help="范围大小（生成 0 到 count-1 的序列）"),
    filter_expr: Annotated[
        Optional[str],
        typer.Option("--filter", "-f", help="过滤表达式，如: lambda x: x % 2 == 0")
    ] = None,
    map_expr: Annotated[
        Optional[str],
        typer.Option("--map", "-m", help="映射表达式，如: lambda x: x * 2")
    ] = None,
    collect: bool = typer.Option(False, "--collect/--no-collect", help="立即收集结果"),
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-l", help="限制结果数量")
    ] = None,
):
    """从范围创建序列"""
    seq = Seq.range(count)
    
    if filter_expr:
        seq = seq.filter(parse_lambda(filter_expr))
    
    if map_expr:
        seq = seq.map(parse_lambda(map_expr))
    
    if limit:
        seq = seq.take(limit)
    
    if collect:
        result = seq.collect()
        typer.echo(f"结果: {result}")
        return result
    else:
        typer.echo(f"Seq (lazy): {seq}")
        return seq


@seq_app.command()
def from_list(
    items: List[int] = typer.Argument(..., help="列表元素"),
    filter_expr: Annotated[
        Optional[str],
        typer.Option("--filter", "-f", help="过滤表达式")
    ] = None,
    map_expr: Annotated[
        Optional[str],
        typer.Option("--map", "-m", help="映射表达式")
    ] = None,
    collect: bool = typer.Option(False, "--collect/--no-collect", help="立即收集结果"),
):
    """从列表创建序列"""
    seq = Seq(items)
    
    if filter_expr:
        seq = seq.filter(parse_lambda(filter_expr))
    
    if map_expr:
        seq = seq.map(parse_lambda(map_expr))
    
    if collect:
        result = seq.collect()
        typer.echo(f"结果: {result}")
        return result
    else:
        typer.echo(f"Seq (lazy): {seq}")
        return seq


@seq_app.command()
def filter_cmd(
    data: List[int] = typer.Argument(..., help="输入数据"),
    expr: str = typer.Argument(..., help="过滤表达式"),
):
    """过滤序列元素"""
    seq = Seq(data)
    result = seq.filter(parse_lambda(expr)).collect()
    typer.echo(f"过滤结果: {result}")
    return result


@seq_app.command()
def map_cmd(
    data: List[int] = typer.Argument(..., help="输入数据"),
    expr: str = typer.Argument(..., help="映射表达式"),
):
    """映射序列元素"""
    seq = Seq(data)
    result = seq.map(parse_lambda(expr)).collect()
    typer.echo(f"映射结果: {result}")
    return result


@seq_app.command()
def collect_cmd(
    data: List[int] = typer.Argument(..., help="输入数据"),
):
    """收集序列为列表"""
    seq = Seq(data)
    result = seq.collect()
    typer.echo(f"收集结果: {result}")
    return result


if __name__ == "__main__":
    typer.run(from_range)
