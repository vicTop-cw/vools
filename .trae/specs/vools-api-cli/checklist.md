# Checklist

## vools-api-cli 子包

- [x] 目录 `vools/api/` 已创建
- [x] `vools/api/__init__.py` 正确导出 Typer 应用
- [x] `vools/api/typer_app.py` 包含正确的 Typer 实例
- [x] `pyproject.toml` 包含 typer 可选依赖
- [x] `vools/api/seq_cmd.py` 实现了 seq 子命令
- [x] `vools/api/ops_cmd.py` 实现了 ops 子命令
- [x] `vools/api/curry_cmd.py` 实现了 curry 子命令
- [x] `vools/api/memoize_cmd.py` 实现了 memoize 子命令
- [x] `vools/__main__.py` 集成了 api 子命令
- [x] `vools api --help` 正确显示帮助信息
- [x] `vools seq --from-range 5 --map "x * 2" --collect` 输出正确
- [x] `vools ops --pipe "range(5)" --map "x * 2" --sum` 输出正确
- [x] 集成测试全部通过
