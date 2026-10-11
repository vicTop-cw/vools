# Checklist

## system-integration-cli 子包

- [x] 目录 `vools/sys/` 已创建
- [x] `vools/sys/__init__.py` 正确导出 Fire 应用
- [x] `vools/sys/fire_app.py` 包含正确的 Fire 实例
- [x] `pyproject.toml` 包含 fire 可选依赖
- [x] `vools/sys/dll_cmd.py` 实现了 dll 子命令
- [x] `vools/sys/compile_cmd.py` 实现了 compile 子命令
- [x] `vools/sys/run_cmd.py` 实现了 run 子命令
- [x] `vools/sys/env_cmd.py` 实现了 env 子命令
- [x] `vools/__main__.py` 集成了 sys 子命令
- [x] `vools sys --help` 正确显示帮助信息
- [x] `vools sys dll --list` 正确列出可用 DLL
- [x] `vools sys env --python` 正确显示 Python 信息
- [x] 集成测试全部通过
