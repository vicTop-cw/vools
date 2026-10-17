# vools.xl._objects — Excel 对象模型

把 Excel 的核心对象（Workbook / Sheet / Cell / Range / Font / Format）封装成
**引擎无关**的 Python 类。上层 `_highlevel` 基于这些对象提供任务级 API。

## 模块

| 模块 | 对象 |
|---|---|
| `book.py` | `Workbook` |
| `sheet.py` | `Sheet`、`Range`、`Cell` |
| `font.py` | `Font` |
| `format.py` | `Format` |

## 约定

- 对象层不得直接依赖具体引擎（openpyxl/xlwings）——由 `_dlls` 注入。
- 每个模块显式声明 `__all__`。
