# vools 项目长期记忆

## 项目约定

- **计划文档位置**: 所有计划/方案文档保存在 `E:\IDEProjects\AI\vools\.workbuddy\` 目录下，不放在其他位置。

## 模块结构 (2026-06-19 重构后)

- `vools/vic/` — 已移除，不再存在
- `vools/utils/tools.py` — 原 `vicTools` 的所有静态方法拆分为独立函数（`transfer`, `shift`, `get_date_seq`, `regexp_*` 系列等 30+ 个）
- `vools/data/vlist.py` — `VList`（原 `vicList`），使用 `@rself` + `ListLikeMeta`
- `vools/data/vtext.py` — `VText`（原 `vicText`），使用 `@rself`，简化了不必要的实例属性
- `vools/datetime/vdate_class.py` — `VDate`（原 `vicDate`），使用 `@rself`
- `vools/__init__.py` — 通过延迟加载保留旧名称（`vicTools`/`vicDate`/`vicText`/`vicList`）的向后兼容访问
- `vools/functional/box.py` — 内部引用已全部更新为新位置和新名称

## 关键设计模式

- `@rself` 装饰器（`vools/decorators/rself.py`）：类装饰器，确保链式调用时返回子类类型而非父类类型
- `ListLikeMeta` 元类：使 `isinstance(x, VList)` 对普通 `list` 也返回 `True`
- 延迟导入：`tools.py` 中 `transfer()` 对 VList/VText 使用延迟导入避免循环依赖
