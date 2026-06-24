"""
memoize 子命令 - 函数记忆化 CLI

用法示例:
    vools memoize --func "lambda x: x * 2" --args 5 --repeat 3
    vools memoize --func "my_func" --args 10 --repeat 5
"""

from typing import Optional, List, Callable
import time
import typer
from typing_extensions import Annotated

from vools import memorize

memoize_app = typer.Typer(help="Memoize 记忆化命令")


def parse_lambda_or_func(expr: str) -> Callable:
    """解析 lambda 表达式或函数名"""
    try:
        return eval(expr, {"__builtins__": {}})
    except Exception:
        import builtins
        if hasattr(builtins, expr):
            return getattr(builtins, expr)
        raise ValueError(f"无法解析表达式: {expr}")


def timing_decorator(func: Callable) -> Callable:
    """计时装饰器"""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        return result, elapsed
    return wrapper


@memoize_app.command()
def call(
    func_expr: str = typer.Argument(..., help="函数表达式，如: lambda x: x * 2"),
    args: List[str] = typer.Argument(..., help="函数参数"),
    repeat: int = typer.Option(1, "--repeat", "-r", help="重复调用次数"),
    show_cache: bool = typer.Option(False, "--show-cache/--no-show-cache", help="显示缓存状态"),
):
    """调用记忆化函数并测量性能"""
    func = parse_lambda_or_func(func_expr)
    
    # 解析参数
    parsed_args = []
    for arg in args:
        try:
            parsed_args.append(eval(arg, {"__builtins__": {}}))
        except Exception:
            parsed_args.append(arg)
    
    # 应用 memorize 装饰器
    memorized_func = memorize(func)
    
    typer.echo(f"函数: {func_expr}")
    typer.echo(f"参数: {parsed_args}")
    typer.echo(f"重复次数: {repeat}")
    typer.echo("-" * 40)
    
    total_time = 0
    results = []
    
    for i in range(repeat):
        result, elapsed = timing_decorator(memorized_func)(*parsed_args)
        results.append(result)
        total_time += elapsed
        
        cache_status = "缓存命中" if i > 0 else "首次计算"
        typer.echo(f"第 {i+1} 次: 结果={result}, 耗时={elapsed:.6f}s, {cache_status}")
    
    typer.echo("-" * 40)
    typer.echo(f"平均耗时: {total_time/repeat:.6f}s")
    typer.echo(f"结果一致: {len(set(results)) == 1}")
    
    return results[0]


@memoize_app.command()
def benchmark(
    func_expr: str = typer.Argument(..., help="函数表达式"),
    args: List[str] = typer.Argument(..., help="函数参数"),
    iterations: int = typer.Option(100, "--iterations", "-n", help="基准测试迭代次数"),
):
    """基准测试记忆化函数"""
    func = parse_lambda_or_func(func_expr)
    
    # 解析参数
    parsed_args = []
    for arg in args:
        try:
            parsed_args.append(eval(arg, {"__builtins__": {}}))
        except Exception:
            parsed_args.append(arg)
    
    # 应用 memorize 装饰器
    memorized_func = memorize(func)
    
    # 预热
    for _ in range(10):
        memorized_func(*parsed_args)
    
    # 基准测试
    start = time.time()
    for _ in range(iterations):
        memorized_func(*parsed_args)
    elapsed = time.time() - start
    
    typer.echo(f"函数: {func_expr}")
    typer.echo(f"参数: {parsed_args}")
    typer.echo(f"迭代次数: {iterations}")
    typer.echo(f"总耗时: {elapsed:.4f}s")
    typer.echo(f"平均每次: {elapsed/iterations*1000:.4f}ms")
    typer.echo(f"每秒操作数: {iterations/elapsed:.2f}")
    
    return elapsed


if __name__ == "__main__":
    typer.run(call)
