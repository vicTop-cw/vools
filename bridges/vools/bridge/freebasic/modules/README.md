# vools.bridge.freebasic.modules — FreeBASIC 模块桥接

FreeBASIC 语言的**模块级**桥接实现：把 `.bas` / `.bi` 模块的编译、加载、
符号导出/导入映射为 vools 统一的桥接接口。

## 用途

- 编译 FreeBASIC 源码并导出函数/常量
- 从 Python 侧按模块名加载 `.so` / `.dll`
- 与 `vools.bridge.freebasic` 主桥接层配合工作

## 约定

- 每个模块显式声明 `__all__`。
- 探测 FreeBASIC 编译器走 `vools.bridge.probe`，避免 import 期直接 spawn。
