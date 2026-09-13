# vools.bridge.lz — LZ (Lang-Zone) 桥接

LZ 是面向系统编程的静态类型语言，编译器 `lang-zone` 走 IR 中间表示路线（AST → LZIR → Rust）。
本桥接将 LZ 接入 vools 统一跨语言框架：核心能力为 **LZ → Rust 转译**。

## 核心 API

| 名称 | 类型 | 说明 |
|------|------|------|
| `lz` | 装饰器 | `@lz` 将 Python 函数体作为 LZ 代码转译 |
| `LzBridge` | 类 | 继承 LangBridge 的桥接实现 |
| `lz_bridge` | 实例 | 全局 LzBridge 实例 |
| `compile_and_run(code, args)` | 函数 | 直接转译一段 LZ 源码 |
| `lz_compiler_available()` | 函数 | 探测 lang-zone 工具链 |
| `rustc_available()` | 函数 | 探测 rustc（执行链路开关） |

## 快速开始

```python
from vools.bridge.lz import lz, compile_and_run

@lz
def hello(x: int) -> int:
    return """
    def main():
        let v = arg0 + 1
        print(v)
    """

print(hello(1))   # rustc 可用 -> 执行输出；否则 -> .rs 路径
```

## 能力说明

- **语言类型**：INTERPRETED（转译型），核心产物为 `.rs`（`lang-zone file.lz -> file.rs`）
- **参数传递**：Python 参数以 `let argN = <字面量>;` 绑定注入源码顶部
- **执行链路**（可选）：rustc 可用时 `rustc hello.rs` 编译为可执行文件并运行；
  rustc 不可用时**降级返回 .rs 路径**，可用 `fallback` 参数回退 Python 实现
- **编码**：LZ 解析器不识别 BOM，所有 .lz 写入为 UTF-8 无 BOM
- **缓存**：按 `func_name + md5(code)` 落 `%TEMP%/vools_lz_cache/`

## 高级用法

### 异步模式

设置 `async_mode=True` 后，装饰器返回 async 函数，编译和执行在线程池中异步完成：

```python
from vools.bridge.lz import lz

@lz(async_mode=True)
async def heavy_compute(x: int) -> int:
    return """
    def main():
        let v = arg0 * 2
        print(v)
    """

result = await heavy_compute(50)  # -> 100
```

### deps 依赖

通过 `deps` 参数声明辅助函数依赖，框架自动拓扑排序并一并转译：

```python
from vools.bridge.lz import lz

@lz
def helper(x: int) -> int:
    return """
    def helper():
        let v = arg0 + 1
        print(v)
    """

@lz(deps=[helper])
def compute(x: int) -> int:
    return """
    def main():
        let r = helper(arg0)
        print(r)
    """
```

### module_code

通过 `module_code` 注入模块级代码（类型声明、全局常量等）：

```python
@lz(module_code='let VERSION = "1.0"')
def version_info() -> str:
    return """
    def main():
        print(VERSION)
    """
```

## 已知限制

- 生成的 .rs 依赖 `lz_builtins` crate，rustc 编译需要 crate 在 rustc 搜索路径可见
- 返回值取 stdout 文本（LZ `print` 输出），类型转换暂不精细
- `lang-zone` 的 Cython 后端（lzcyc）未封装，如需 Cython 产物可直调 `CY/` 子项目

## 测试

```bash
python -m pytest tests/test_lz_bridge.py -v
```
