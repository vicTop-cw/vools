# 多语言桥接 {#B00}

> **模块路径**：vools.bridge
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#B00
> **最后更新**：2026-06-30

## 模块概述

vools 桥接模块支持调用 27 种编程语言：

- **编译型语言**：Rust、Nim、Go、C、C++
- **JVM 语言**：Java、Kotlin、Scala
- **脚本语言**：Lua、JavaScript、PHP、Perl
- **移动端**：Swift、Dart、Kotlin
- **其他**：MoonBit、Julia、Ruby 等

## 支持的语言

| 语言 | 加速效果 | 文档 |
|------|----------|------|
| Rust | ⭐⭐⭐⭐⭐ | [rust.md](rust.md) |
| Nim | ⭐⭐⭐⭐ | [nim.md](nim.md) |
| Go | ⭐⭐⭐⭐ | [go.md](go.md) |
| 其他语言 | ⭐⭐⭐ | [others.md](others.md) |

## 使用方式

使用 `@rust` 装饰器调用 Rust 函数：

```python
from vools.bridge import rust

@rust
def fast_hash(data: str) -> str:
    # Rust 实现
    pass

result = fast_hash("hello")  # 自动编译并调用 Rust 函数
```
