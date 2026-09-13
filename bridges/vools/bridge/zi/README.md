# vools.bridge.zi — 兹（Zi）桥接

兹是一门以中文为主、ASCII 命对外接口的编程语言，编译到 BEAM 字节码，
无缝复用 OTP 的并发、分布与容错能力。编译器为 Python 包 `zhi`
（词法 → 语法 → 语义 → Elixir 代码生成，四层全链路）。

## 核心 API

| 名称 | 类型 | 说明 |
|------|------|------|
| `zi` | 装饰器 | `@zi` 将 Python 函数体作为兹代码运行 |
| `ZiBridge` | 类 | 继承 LangBridge 的桥接实现 |
| `zi_bridge` | 实例 | 全局 ZiBridge 实例 |
| `compile_and_run(code, args)` | 函数 | 直接运行一段兹源码 |
| `zi_compiler_available()` | 函数 | 探测 zhi 编译器 + Elixir 运行时 |
| `get_zi_version()` | 函数 | 获取 zhi 编译器版本 |

## 快速开始

```python
from vools.bridge.zi import zi, compile_and_run

@zi
def hello() -> str:
    return """
    坊 示例

    策 主
        言 "你好，兹"
    """

print(hello())   # -> 你好，兹
```

## 能力说明

- **语言类型**：INTERPRETED（直通型），核心链路 `zhi compile <file.玆> --run`
  （即时编译到内存并运行 `策 主`，复用 OTP 运行时）
- **参数传递**：Python 参数以 arg0/arg1 占位符**文本替换**注入
  （避开 zhi 顶层 `赋` 作用域限制；body 内写 arg0/arg1 即被替换为字面量）
- **工具链**：zhi Python 包（`E:\IDEProjects\AI\兹\zhi\src`，src 布局）+ Elixir 可执行
- **编码**：.玆 文件 UTF-8 写入；Elixir 编译警告走 stderr 不影响 stdout 结果
- **缓存**：按 `func_name + md5(code)` 落 `%TEMP%/vools_zi_cache/`

## 高级用法

### 异步模式

设置 `async_mode=True` 后，装饰器返回 async 函数，编译和执行在线程池中异步完成：

```python
from vools.bridge.zi import zi

@zi(async_mode=True)
async def heavy_compute(x: int) -> int:
    return """
    坊 计算

    策 主
        赋 v = arg0 * 2
        言 v
    """

result = await heavy_compute(50)  # -> 100
```

### deps 依赖

通过 `deps` 参数声明辅助函数依赖，框架自动拓扑排序并一并编译：

```python
from vools.bridge.zi import zi

@zi
def helper(x: int) -> int:
    return """
    坊 辅助

    策 主
        赋 v = arg0 + 1
        言 v
    """

@zi(deps=[helper])
def compute(x: int) -> int:
    return """
    坊 计算

    策 主
        赋 r = 辅助(arg0)
        言 r
    """
```

### module_code

通过 `module_code` 注入模块级代码（类型声明、全局常量等）：

```python
@zi(module_code='坊 常量\n策 主\n    言 3.1415926')
def pi() -> float:
    return """
    坊 返回

    策 主
        言 3.14
    """
```

## 已知限制

- 返回值取 stdout 文本（`言` 输出），多行输出返回全文
- 参数替换是文本级替换：body 中与 argN 同名文本也会被替换，复杂场景建议用
  `compile_and_run` 直跑并自行拼接字面量
- `zi compile --build`（落盘 .beam）与 JS 后端未封装，如需可直调 zhi.cli

## 测试

```bash
python -m pytest tests/test_zi_bridge.py -v
```
