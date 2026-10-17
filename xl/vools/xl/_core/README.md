# vools.xl._core — 核心基础设施

XL 桥接的**底层核心**：与 Excel COM/原生接口无关的通用装载与 API 聚合。
为上层 `_dlls`、`_objects`、`_highlevel` 提供基础。

## 模块

| 模块 | 说明 |
|---|---|
| `api.py` | API 聚合：把各引擎的能力统一到同一调用面 |
| `loader.py` | 按引擎装载 `vools.xl`（惰性） |

## 约定

- 不直接触碰 COM 或原生 Dll 导入（那在 `_dlls`）。
- 每个模块显式声明 `__all__`。
