# vools.bridge.pentad — Pentad 桥接

Pentad 是一门多范式语言（Rust 实现），编译器为 `p5c`（含 run/jit/dump/check 等子命令）。
本桥接将 Pentad 接入 vools 统一跨语言框架：解释执行、代码生成、参数字面量注入。

## 核心 API

| 名称 | 类型 | 说明 |
|------|------|------|
| `pentad` | 装饰器 | `@pentad` 将 Python 函数体作为 Pentad 代码执行 |
| `PentadBridge` | 类 | 继承 LangBridge 的桥接实现 |
| `pentad_bridge` | 实例 | 全局 PentadBridge 实例 |
| `compile_and_run(code, args, ret_type)` | 函数 | 直接执行一段 Pentad 源码 |
| `pentad_compiler_available()` | 函数 | 探测 p5c 工具链是否可用 |
| `get_pentad_version()` | 函数 | 获取 p5c 版本号 |

## 快速开始

```python
from vools.bridge.pentad import pentad, compile_and_run

@pentad
def add(x: int, y: int) -> int:
    return "print(x + y)"

print(add(3, 5))   # -> 8

# 无装饰器直接跑
result = compile_and_run("print(1 + 2)")   # -> '3'
```

## 能力说明

- **语言类型**：INTERPRETED（执行型），执行方式 `p5c run -q <file>.p5`
- **参数传递**：Python 参数以 Pentad `let` 绑定嵌入源码顶部（int/float/str/bool）
- **输出解析**：`p5c run -q` 抑制词法/语法/执行诊断，只保留程序自身 stdout；取末行作为结果
- **工具链探测**：位置统一由 `vools.bridge.configs` 解析——用户 JSON
  （`~/.vools/bridge_config.json`，探针发现后写入，不进仓库不发布）→
  `VOOLS_PROJECTS_ROOT` 扫描 → `VOOLS_PENTAD_ROOT`/`VOOLS_PENTAD_PATH` → PATH → WSL
- **缓存**：源文件按 `func_name + md5(code)` 落 `%TEMP%/vools_pentad_cache/`
- **编码**：p5c 输出为 UTF-8，本桥接显式按 UTF-8 解码（Windows 本地编码是 GBK）

## 工具链位置的可配置性

不硬编码用户机器绝对路径。p5c 的查找顺序（`vools.bridge.configs.resolve_compiler('pentad')`）：

1. 环境变量 `VOOLS_PENTAD_PATH`（直接指定可执行文件）
2. 环境变量 `VOOLS_PENTAD_ROOT` + 相对 globs（`target/release/p5c.exe` 等）
3. 用户 JSON 中的 `project_roots.pentad` / `discovered.pentad`
4. 工程根自动扫描（`VOOLS_PROJECTS_ROOT` 下的 `Pentad`/`pentad` 子目录）
5. `PATH` 中的 `p5c`

用户可在 `~/.vools/bridge_config.json` 写入 `overrides.pentad` 直接覆盖。

## 已知限制

- 参数以 `let` 绑定嵌入：字符串内嵌转义，含复杂转义的建议用 `run_project` 直跑
- 返回值取 stdout 末行：多行输出只返回最后一行
- Pentad 语言自身的运行时/JIT 特性由 `p5c` 决定，本桥接不改语言语法

## 测试

```bash
python -m pytest tests/test_pentad_bridge.py -v
```