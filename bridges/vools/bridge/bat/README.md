# vools.bridge.bat — Windows Batch 桥接

提供 `.bat` / `.cmd` 批处理脚本的生成、编译、执行桥接，支持在 vools 框架内
以一致接口调用 Windows 批处理语言。

## 模块

- `bridge/bat/__init__.py` — 命名空间入口
- `bridge/bat/compiler.py` — 批处理脚本编译器/执行器

## 公开符号

`compiler.py` 暴露批处理桥接所需的核心类/函数（见文件内 `__all__`）。

## 约定

- 桥接层保持 py3.6+ 兼容。
- 所有编译器探测走 `vools.bridge.probe`，避免 import 期直接 spawn 子进程。
