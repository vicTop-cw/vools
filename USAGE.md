# USAGE — vools 使用指南

> 速览见 [README.md](README.md)，完整文档见 <https://victop-cw.github.io/vools/>。
> 本文件聚焦「怎么用」：安装、导入约定、各子系统的典型用法、包边界与常见问题。
> Actus 动作引擎属于独立包 `vools-actus`，不在此文档范围内（见其自带 README）。

---

## 1. 安装

vools 核心库零强制依赖（Python ≥ 3.6），其余能力按 extra 按需安装：

```bash
# 核心库（函数式 / 装饰器 / 数据类型 / 响应式 / SQL 等）
pip install vools

# 全部可选能力（含 bridges / rx / actus / xl / dll32 / pyk）
pip install "vools[all]"

# 按场景挑选
pip install "vools[bridges]"   # 多语言桥接（vools-bridges）
pip install "vools[rx]"         # 响应式扩展（vools-rx）
pip install "vools[pyk]"       # PySpark / PostgreSQL 集成（vools-pyk）
pip install "vools[security]"  # vtext 的 fernet/aes 加密（cryptography）
pip install "vools[serialize]" # msgpack / orjson 序列化后端
```

从源码安装：

```bash
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install .
```

> **命名空间约定**：`bridges` / `rx` / `actus` / `pyk` / `xl` / `dll32` 都是按命名空间包
> 分发的独立 PyPI 包；安装后并入 `vools.*` 命名空间（如 `vools_bridges` 模块对应
> `vools.bridge`）。核心库 `vools` 不含这些重依赖，保持轻量。

---

## 2. 导入约定

所有顶层能力都在 `vools` 直接命名空间下，统一 `import vools` 或具名导入：

```python
from vools import memorize, once, retry, overload, curry, stuff
from vools import Seq, Ops, _, g, iif, pipe, Box
from vools import Observable
from vools import VList, VText, VDate
```

可选子系统的导入：

```python
# bridges（需装 vools-bridges）：独立顶层包 vools_bridges
from vools_bridges import discover_all, get_discovery_report

# pyk（需装 vools-pyk）：惰性命名空间，未装时 import 抛 AttributeError
import vools
pyk = vools.pyk           # 等价于 import vools.pyk
```

> 未安装对应 extra 时，`vools.pyk` / `vools.vicspark` 会抛出清晰的 `AttributeError`，
> 提示你 `pip install "vools[pyk]"`。

---

## 3. 装饰器

```python
from vools import memorize, once, retry, overload, curry, stuff, lazy, repeat

@memorize(duration=60)                 # 60 秒内的调用结果缓存
def expensive(x):
    return x ** 2

@once                                 # 进程内只执行一次
def init():
    return 42

@retry(times=3, delay=1)              # 失败重试 3 次，间隔 1s
def risky():
    ...

@overload
def process(x: int) -> int:
    return x * 2
@process.register
def process(x: str) -> str:
    return x.upper()

@curry
def add(a, b, c):
    return a + b + c
assert add(1)(2)(3) == 6

@stuff
def mul(a, b):
    return a * b
assert mul(2)(3)() == 6
```

可用装饰器一览：`memorize` / `once` / `lazy` / `repeat` / `retry` / `curry` / `overload` / `stuff`。

---

## 4. 函数式编程

```python
from vools import Seq, Ops, _, g, iif, pipe, Box

# Seq 链式操作
evens_double = Seq(range(10)).filter(lambda x: x % 2 == 0).map(lambda x: x * 2).collect()
# [0, 4, 8, 12, 16]

# Ops 管道操作符（| 串联）
total = range(10) | Ops.filter(lambda x: x > 3) | Ops.map(lambda x: x * 2) | Ops.sum()
# 84

# 占位符
f = _ + 1
assert f(2) == 3

# 箭头函数
f = g("x, y => x + y")
assert f(3, 4) == 7

# 条件表达式
assert iif(True, "yes", "no") == "yes"

# 对象包装
b = Box([1, 2, 3]).map(lambda xs: [x * 2 for x in xs])
```

---

## 5. 数据类型

```python
from vools import VList, VText, VDate

vl = VList([1, 2, 3]).map(lambda x: x + 1)     # 增强列表，链式 API
vt = VText("hello").upper().reverse()           # 增强文本
```

---

## 6. 响应式编程

```python
from vools import Observable, Ops

result = []
Observable.from_iterable([1, 2, 3, 4, 5]).pipe(
    Ops.filter(lambda x: x % 2 == 0),
    Ops.map(lambda x: x * 2),
    Ops.take(2),
).subscribe(result.append)

print(result)   # [4, 8]
```

类型：`Observable` / `Subject` / `BehaviorSubject` / `ReplaySubject`。

---

## 7. SQL 引擎

`vools.sql` 提供 SQLite / PostgreSQL / Spark（方言 + 构建器）：

```python
from vools.sql import sqlite, build

# SQLite 内联
conn = sqlite.connect(":memory:")
sqlite.execute(conn, "CREATE TABLE t(a INTEGER)")

# 方言构建器
q = build.select("a", "b").from_("t").where(build.eq("a", 1))
```

> PostgreSQL / Spark 能力在 `vools[pyk]`（独立包 `vools-pyk`）中提供，见其 README。

---

## 8. 多语言桥接（vools-bridges）

需先 `pip install vools-bridges`。编译器**自动发现**（本机 + WSL），无需手配 PATH：

```python
from vools_bridges import discover_all, get_discovery_report, configure_from_discovery

result = discover_all(include_wsl=True)        # 一键发现所有编译器
print(get_discovery_report())                  # 格式化报告
configure_from_discovery(include_wsl=True)     # 自动配置管理器

from vools_bridges import get_helper
nim = get_helper("nim")
if nim.is_available():
    print(nim.get_compiler_path())
```

支持 27+ 种语言（Lua / Rust / Go / Java / Kotlin / Scala / Swift / Dart / MoonBit / Nim …）。
编译器位置由 `bridges/vools/bridge/configs.py` 单一声明（`~/.vools/bridge_config.json`
用户覆盖，本机生成、不进仓库），跨进程可复现。新增 Pentad 桥接 `p5c run -q` 解释执行。

---

## 9. PySpark / PostgreSQL 集成（vools-pyk）

需 `pip install "vools[pyk]"`（或 `pip install vools-pyk`）。核心库不再携带该代码：

```python
import vools
pyk = vools.pyk                                # 命名空间合并，未装则抛 AttributeError
df = pyk.df.from_spark(...)                    # PySpark DataFrame 桥接
# PostgreSQL 连接 / 方言见 vools-pyk 的 docs/
```

仅想要 pyspark 运行时（不装全套 `vools-pyk` API）可用兼容指令 `pip install "vools[spark]"`。

---

## 10. CLI

```bash
vools --help
```

入口：`pyproject.toml` 的 `[project.scripts] vools = "vools.__main__:main"`。

---

## 11. 测试

默认只跑纯 Python 核心测试（functional / decorators / data / core / serialize / task …）；
需要外部资源的子项目按路径单独跑：

```bash
python -m pytest tests/                          # 核心测试（默认 addopts）
python -m pytest bridges/tests/                  # 桥接测试（需 vools-bridges）
python -m pytest --override-ini="addopts=--tb=short -q"   # 跑全部（含被 ignore 的）
python -m pytest tests/functional/test_pipe_ops.py::test_basic_pipe -v
python -m pytest tests/ --cov=vools --cov-report=html
```

---

## 12. 常见问题

- **`import vools.pyk` 报 AttributeError**：没装 `vools-pyk`。`pip install "vools[pyk]"`。
- **桥接找不到编译器**：先 `discover_all(include_wsl=...)`，或把工具链写进
  `~/.vools/bridge_config.json`（用 `VOOLS_BRIDGE_CONFIG` 可改路径）。
- **中文乱码（Tnr/Pentad 等子进程）**：桥接层已统一 `.decode('utf-8', errors='replace')`，
  与本机 locale 无关；若仍乱码，确认子进程确实以 UTF-8 输出。
- **PySpark 在本机起不来**：多为 JDK / SPARK_HOME 版本不匹配（如 Spark 2.4 需 JDK 8、
  winutils.exe）。环境修复见 `tests/_spark_env.py`（仅本机开发用，不随包发布）。

---

## 13. 包边界速查

| 能力 | 包 | 安装 | 顶层导入 |
|------|----|------|----------|
| 核心（装饰器/函数式/数据/响应式/SQL） | `vools` | `pip install vools` | `from vools import ...` |
| 多语言桥接 | `vools-bridges` | `vools[bridges]` | `from vools_bridges import ...` |
| 响应式扩展 | `vools-rx` | `vools[rx]` | `from vools.rx import ...` |
| PySpark/PostgreSQL | `vools-pyk` | `vools[pyk]` | `import vools.pyk` |
| Actus 动作引擎 | `vools-actus` | `vools[actus]` | 见其 README（独立仓库流程） |
| Excel | `vools-xl` | `vools[xl]` | `from vools.xl import ...` |
| 32 位 DLL 调用 | `vools-dll32` | `vools[dll32]` | `from vools.dll32 import ...` |
