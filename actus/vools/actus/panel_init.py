"""panel — Actus 快捷面板（Quicker 风格人机入口）。"""

__version__ = "0.1.0"

# 注意（2026-10-17 寻虫 BUG-73）：这里曾写 `__all__ = ['app']`，但本文件从未定义
# 或导入 app —— 空头名让 `from vools.actus.panel_init import *` 抛
# AttributeError（实测）。面板的真实入口在 vools.actus.panel（run_panel /
# PanelApp），本文件全仓【零引用】（2026-10-17 grep 核实），是个历史遗留桩；
# 只把空头名摘掉、不引入新依赖（把 app 变真要么造 FastAPI 硬依赖、要么改语义，
# 都不是一行桩文件该有的动作）。
__all__ = []
