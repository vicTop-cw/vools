"""
Typer 应用实例 - vools api CLI 主应用

整合所有子命令:
- seq: Seq 序列操作
- ops: Ops 管道操作
- curry: 函数柯里化
- memoize: 函数记忆化
"""

import typer
from typing_extensions import Annotated

from .seq_cmd import seq_app
from .ops_cmd import ops_app
from .curry_cmd import curry_app
from .memoize_cmd import memoize_app

__all__ = ["typer_app"]

typer_app = typer.Typer(
    name="api",
    help="vools API 命令行工具 - 函数式编程操作集合",
    add_completion=False,
)

# 注册子命令
typer_app.add_typer(seq_app, name="seq")
typer_app.add_typer(ops_app, name="ops")
typer_app.add_typer(curry_app, name="curry")
typer_app.add_typer(memoize_app, name="memoize")


@typer_app.command()
def info():
    """显示 API 工具信息"""
    typer.echo("=" * 50)
    typer.echo("vools API 命令行工具")
    typer.echo("=" * 50)
    typer.echo("")
    typer.echo("可用子命令:")
    typer.echo("  seq      - Seq 序列操作 (range, filter, map, collect)")
    typer.echo("  ops      - Ops 管道操作 (pipe, filter, map, sum)")
    typer.echo("  curry    - 函数柯里化")
    typer.echo("  memoize  - 函数记忆化")
    typer.echo("")
    typer.echo("使用示例:")
    typer.echo("  vools api seq --from-range 10 --filter 'lambda x: x % 2 == 0'")
    typer.echo("  vools api ops --pipe 1 2 3 4 5 --filter 'lambda x: x % 2 == 0' --sum")
    typer.echo("  vools api curry --func 'lambda x, y: x + y' --args 5 10")
    typer.echo("  vools api memoize --func 'lambda x: x * 2' --args 5 --repeat 3")
    typer.echo("")


def main():
    """主入口"""
    typer_app()


if __name__ == "__main__":
    main()
