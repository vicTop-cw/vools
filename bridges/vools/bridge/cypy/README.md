# vools.bridge.cypy — Cypy 桥接

Cypy 是一门 Python-like 语言，编译到 Cython（逐步类型、编译期检查、高性能 C 代码生成）。
编译器 `cypyc` 支持 transpile / compile / build / run 等子命令。

## 核心 API

| 名称 | 类型 | 说明 |
|------|------|------|
| `cypy` | 装饰器 | `@cypy` 将 Python 函数体作为 Cypy 代码转译/运行 |
| `CypyBridge` | 类 | 继承 LangBridge 的桥接实现 |
| `cypy_bridge` | 实例 | 全局 CypyBridge 实例 |
| `compile_and_run(code, args)` | 函数 | 直接转译一段 Cypy 源码 |
| `cypy_compiler_available()` | 函数 | 探测 cypyc 工具链（转译能力） |
| `cypy_run_available()` | 函数 | 探测完整执行链路（Python.h + C 编译器） |

## 快速开始

```python
from vools.bridge.cypy import cypy, compile_and_run

@cypy
def hello() -> str:
    return "print(1 + 2)"

print(hello())   # 环境支持时 -> 3；否则 -> .pyx 路径
```

## 能力说明

- **语言类型**：INTERPRETED（转译型），核心产物为 `.pyx`（`cypyc transpile`）
- **参数传递**：Python 参数以 arg0/arg1 占位符**文本替换**注入（Cypy 语法贴近 Python）
- **执行链路**（可选）：`cypyc run` 完整链路（转译 → Cython 编译 .pyd → 运行）；
  需要**完整 Python（含 Python.h）+ C 编译器（MSVC/gcc）**。当前 Loomy 精简运行时
  缺 Python.h 时自动降级：返回 .pyx 转译产物路径，可用 `fallback` 回退 Python 实现
- **缓存**：按 `func_name + md5(code)` 落 `%TEMP%/vools_cypy_cache/`

## 高级用法

### 异步模式

设置 `async_mode=True` 后，装饰器返回 async 函数，编译和执行在线程池中异步完成：

```python
from vools.bridge.cypy import cypy

@cypy(async_mode=True)
async def heavy_compute(x: int) -> int:
    return "print(arg0 * 2)"

result = await heavy_compute(50)  # -> 100
```

### deps 依赖

通过 `deps` 参数声明辅助函数依赖，框架自动拓扑排序并一并转译：

```python
from vools.bridge.cypy import cypy

@cypy
def helper(x: int) -> int:
    return "print(arg0 + 1)"

@cypy(deps=[helper])
def compute(x: int) -> int:
    return "print(helper(arg0))"
```

### module_code

通过 `module_code` 注入模块级代码（类型声明、全局常量等）：

```python
@cypy(module_code='VERSION = "1.0"')
def version_info() -> str:
    return "print(VERSION)"
```

## 已知限制

- 完整编译运行依赖 Python.h（当前 Loomy python-runtime 精简版不包含）；
  在带完整开发头文件的 Python 环境（如 VS Code 官方 Python + Build Tools）下可直接运行
- 返回值取 stdout 文本；参数替换为文本级替换，复杂场景建议直拼字面量

## 测试

```bash
python -m pytest tests/test_cypy_bridge.py -v
```
