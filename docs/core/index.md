# 核心功能文档

> **模块路径**：`vools`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **最后更新**：2026-06-30

## 概述

vools 核心功能文档涵盖装饰器、函数式编程辅助工具等核心模块。

## 文档列表

| 编号 | 文档 | 说明 |
|------|------|------|
| #004 | [装饰器总览](./decorators.md) | 装饰器模块功能总览 |
| #005 | [占位符](./placeholder.md) | 占位符 `_`、`_1`、`_2` 等用法 |
| #006 | [函数重载](./overload.md) | `@overload`、`@overcurry`、`@overloads` 装饰器 |
| #007 | [柯里化](./curry.md) | `@curry`、`@stuff` 装饰器 |
| #008 | [缓存装饰器](./memoize.md) | `@memorize`、`@persist` 装饰器 |

## 核心模块

### vools.decorators

装饰器模块，包含：

- **缓存装饰器**：`memorize`、`once`、`persist`
- **控制流装饰器**：`repeat`、`retry`、`rerun`
- **柯里化装饰器**：`curry`、`delay_curry`
- **重载装饰器**：`overload`、`overcurry`、`overloads`
- **线程装饰器**：`trd`、`proc`
- **快捷工具**：`timeit`、`safe`、`throttle`、`debounce`

### vools.functional

函数式编程模块，包含：

- **占位符**：`_`、`_1`、`_2` 等单例占位符
- **箭头函数**：`g` 函数
- **管道操作**：`pipe`、`compose`
- **盒函数**：`box`、`iif`

### vools.cache

缓存模块，包含：

- **TimedCache**：带过期时间的线程安全缓存
- **memorize**：函数结果内存缓存
- **persist**：函数结果持久化缓存

## 快速导航

```python
# 装饰器使用
from vools import memorize, once, persist
from vools import retry, repeat
from vools import curry, overload

# 占位符使用
from vools.functional import _, _1, _2, _3, g
```

## 相关链接

- [主文档索引](../index.md)
- [函数式编程文档](../functional/index.md)
- [装饰器调用模式](../decorator_calling_modes_summary.md)
