# vools.bridge.tnr — Tnr 桥接

Tnr 是面向 AI 的张量数学语言（公式即代码，Rust 实现），v2.0.1。
本桥接将 Tnr 接入 vools 统一跨语言框架：解释执行、代码生成、参数字面量注入、Tensor 输出解析。

## 核心 API

| 名称 | 类型 | 说明 |
|------|------|------|
| `tnr` | 装饰器 | `@tnr` 将 Python 函数体作为 Tnr 代码执行 |
| `TnrBridge` | 类 | 继承 LangBridge 的桥接实现 |
| `tnr_bridge` | 实例 | 全局 TnrBridge 实例 |
| `compile_and_run(code, args, ret_type)` | 函数 | 直接执行一段 Tnr 源码 |
| `run_tnr_file(path)` | 函数 | 直接运行 .tnr 文件，返回 (returncode, stdout, stderr) |
| `tnr_compiler_available()` | 函数 | 探测 Tnr 工具链是否可用 |
| `get_tnr_version()` | 函数 | 获取 Tnr 版本号 |

## 快速开始

```python
from vools.bridge.tnr import tnr, compile_and_run

@tnr
def matmul2(x: int, y: int) -> int:
    return "print(x * y);"

print(matmul2(6, 7))   # -> 42

# 无装饰器直接跑
result = compile_and_run("print(1 + 2);")   # -> 3
```

## 能力说明

- **语言类型**：INTERPRETED（解释型），执行方式 `tnr run <file>.tnr`
- **参数传递**：Python 参数以 Tnr 字面量嵌入源码顶部
  （int/float/str/bool/list；张量用 `[[1,2],[3,4]]` 嵌套列表语法）
- **输出解析**：`tnr run` 逐行打印，`Tensor<int64, []>(3)` 自动解析回 Python 值；
  非 Tensor 行原样返回字符串
- **工具链探测**：本机 `E:\IDEProjects\AI\Tnr\target\{release,debug}\tnr.exe`
  → PATH → WSL，探测失败时 `compiler_available()` 返回 False（配合 fallback 回退）
- **缓存**：源文件按 `func_name + md5(code)` 落 `%TEMP%/vools_tnr_cache/`

## 高级用法

### 异步模式

设置 `async_mode=True` 后，装饰器返回 async 函数，编译和执行在线程池中异步完成：

```python
from vools.bridge.tnr import tnr

@tnr(async_mode=True)
async def heavy_compute(x: int) -> int:
    return "print(x * x);"

result = await heavy_compute(100)  # -> 10000
```

### deps 依赖

通过 `deps` 参数声明辅助函数依赖，框架自动拓扑排序并一并编译：

```python
from vools.bridge.tnr import tnr

@tnr
def helper(x: int) -> int:
    return "print(x + 1);"

@tnr(deps=[helper])
def compute(x: int) -> int:
    return "print(helper(x));"

print(compute(5))  # -> 6
```

### module_code

通过 `module_code` 注入模块级代码（类型声明、全局常量等）：

```python
@tnr(module_code='let PI = 3.1415926')
def circle_area(r: float) -> float:
    return "print(PI * r * r);"
```

## 已知限制

- 参数以字面量嵌入：字符串内嵌 JSON 转义，含复杂转义的字符串建议用 `run_tnr_file` 直跑
- 返回值取 stdout 最后一行：多行输出的函数只返回末行解析值
- Tnr 转译子集（`tnr transpile`）能力未封装，如需 Rust 转译产物可直接调
  `run_tnr_file` 配合 `tnr transpile` 子命令

## 测试

```bash
python -m pytest tests/test_tnr_bridge.py -v
```
