"""
vools.api - Typer CLI 应用包

导出 Typer 应用实例，提供命令行接口。

子命令:
- seq: Seq 序列操作
- ops: Ops 管道操作  
- curry: 函数柯里化
- memoize: 函数记忆化

示例:
    from vools.api import typer_app
    typer_app()
"""

from .typer_app import typer_app, main, info

__all__ = ["typer_app", "main", "info"]

__version__ = "0.1.0"
