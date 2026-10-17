# vools.xl._dlls — 引擎 Dll 导入层

负责把不同后端引擎的 DLL/COM 装载封装成统一接口。当前支持：
`openpyxl`（纯 Python）、`xlwings`（COM）、`wps`（WPS Office COM）等。

## 模块

本目录仅有 `__init__.py`，DLL 装载逻辑按引擎分别落在
`vools.xl._core.loader` 与 `vools.xl._objects` 下。

## 约定

- DLL 装载必须**惰性**：避免 import 期即触发 COM 注册/加载。
- 任何探测（是否安装 wps/excel 等）走 `vools.actus.probe` 或
  `shutil.which`，不在 import 期 spawn 子进程。
