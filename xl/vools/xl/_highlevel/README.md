# vools.xl._highlevel — 高层 API

把 `vools.xl._objects` 的低层对象封装成**面向任务**的高层接口：
读写 Excel 文件、pandas 互操作、公式引擎调度等。

## 模块

| 模块 | 公开能力 |
|---|---|
| `engines.py` | 引擎注册/切换 |
| `pandas_io.py` | DataFrame ⇄ Excel |
| `utils.py` | 高层工具函数 |

## 约定

- 所有 API 保持 py3.6+ 兼容。
- 每个模块显式声明 `__all__`。
