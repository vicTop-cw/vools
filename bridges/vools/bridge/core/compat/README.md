# vools.bridge.core.compat — 跨版本兼容垫片

提供 `asyncio.run` 等 **Python 3.6 缺失** 但 bridges 测试/运行依赖的便利函数的
版本无关实现：py3.7+ 直接转发标准库，py3.6 手工实现（含取消残留任务、关闭
async generators 等收尾）。

## 模块

- `compat/asyncio_compat.py` — `asyncio.run` 垫片

## 使用

py3.6 下测试可在 conftest 里把 `asyncio.run` 挂到本模块的 `run`，使
`asyncio.run(...)` 调用两种版本都能工作。

## 约定

- 不引入第三方依赖。
- 每个模块显式声明 `__all__`。
