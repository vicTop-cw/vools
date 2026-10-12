# vools.bridge.md「Markdown 即代码」实施计划

> 生成时间: 2026-09-12
> 模型: deepseek-v4-flash-0731 + Loomy 细化
> 状态: v2 定稿（含接口契约、错误处理、哈希策略、M1 任务拆分）

---

## 零、与 vools.md 的关系

`vools.md`（核心包 `vools/md/`）和 `vools.bridge.md`（桥接包 `bridges/vools/bridge/md/`）是**两个独立子包**，定位不同：

| | `vools.md` | `vools.bridge.md` |
|---|------------|-------------------|
| **位置** | `vools/md/` | `bridges/vools/bridge/md/` |
| **定位** | Markdown 处理工具集 | Markdown 即代码（可执行脚本） |
| **核心能力** | 解析/生成/HTML/主题/工具函数 | 解析 → 执行 → 产物管理 |
| **消费者** | 通用 Markdown 处理场景 | 多语言桥接编排 |

### bridge.md 对 vools.md 的复用

`vools.bridge.md` 的 parser 层**复用** `vools.md` 的代码块提取能力：

```python
# bridge.md/parser.py 内部调用 vools.md 的解析器
from vools.md.parser import parse as md_parse
from vools.md.parser import Document, CodeBlock as MdCodeBlock

# 用 vools.md 的 AST 提取代码块，再叠加 #! 指令解析
doc = md_parse(md_text)
for node in doc.children:
    if isinstance(node, MdCodeBlock):
        # node.language, node.code → 提取后解析指令
        ...
```

**不复用**的部分：
- 指令解析（`#!` 语法是 bridge.md 专属）
- 执行编排（bridge.md 独有）
- 产物管理（bridge.md 独有）

### 两个子包各自独立演进

- `vools.md` 继续作为通用 Markdown 工具集维护（解析器、生成器、HTML、主题、高级功能）
- `vools.bridge.md` 专注 Markdown 即代码场景，按需复用 vools.md 的底层解析

---

## 一、总体定位

新增子包 `vools.bridge.md`：让一个 `.md` 文件成为可直接运行的多语言脚本。

- **py 是胶水** — 解析、编排、依赖检查、产物管理
- **md 是载体** — 代码块承载各语言代码，`#!` 指令控制行为

```
┌─────────────────────────────────────────────────────┐
│  script.md                                          │
│  #!config config.lua   ← 文件级指令                  │
│  #!deps   deps.toml                                 │
│                                                     │
│  ```lua  #!config          ← 配置块（可选）           │
│  ...                                               │
│  ```                                               │
│  ```python #!run export=main ← 块级指令              │
│  print("hello")                                    │
│  ```                                               │
│  ```shell #!run workdir=../tmp                      │
│  echo done                                         │
│  ```                                               │
└──────────────┬──────────────────────────────────────┘
               │  py 胶水编排
┌──────────────▼──────────────────────────────────────┐
│  parse → config(lua) → deps(toml) → exec(块顺序)    │
│  → artifacts 管理 → build.yaml 清单                  │
└─────────────────────────────────────────────────────┘
```

---

## 二、四种格式的分工

| 格式 | 角色 | 落地方式 |
|------|------|----------|
| Lua | 配置 | `config.lua` 文件或 md 内 `#!config` 块，复用 `bridge.lua` 执行，JSON 回传 |
| TOML | 依赖管理 | `deps.toml` 声明运行时/解释器/包依赖，py 检查并提示 |
| YAML | 构建产物清单 + 库索引 | `build.yaml`：md_hash、块状态、产物路径/hash；多文件阶段作为库索引 |
| Python | 一切语言的胶水 | 解析器、编排器、执行器、产物管理器、CLI |

---

## 三、解析器精确语法规则

### 3.1 文件级指令

文件级指令必须出现在 **md 文件最顶部**，连续 `#!` 行，被第一个非 `#!` 行或空行终止。

```
#!config config.lua
#!deps   deps.toml
#!build-dir .mdbuild
#!entry  main
#!only   main,test
```

规则：
- 每行格式：`#!<key>  <value>`（key 和 value 之间至少一个空格）
- value 可选（如 `#!run` 无 value）
- 未声明的指令使用默认值

| 指令 | 默认值 | 说明 |
|------|--------|------|
| `#!config <path>` | 自动查找同目录 `config.lua` | 指定配置文件 |
| `#!deps <path>` | 自动查找同目录 `deps.toml` | 指定依赖文件 |
| `#!build-dir <path>` | `.mdbuild/` | 产物根目录 |
| `#!entry <tag>` | 无 | 入口块 tag（仅跑该 tag 及无 tag 的块） |
| `#!only a,b` | 无 | 默认只跑这些 tag 的块（可被 CLI `--only` 覆盖） |

### 3.2 代码块语法

标准 Markdown fenced code block，语言标识符决定桥接目标：

```
```lang #!directive1=val1 directive2=val2
code content
```
```

规则：
- 语言标识符 = 第一个 token（如 `python`、`lua`、`shell`、`c`）
- 指令部分 = 第一个 token 之后、换行之前的内容
- 指令格式：`#!key=value` 或 `#!key value`（空格分隔）
- 多个指令用空格分隔，或同一行多个 `#!` 前缀
- 无指令的代码块默认 `#!run`

### 3.3 块级指令全集

| 指令 | 值格式 | 默认 | 说明 |
|------|--------|------|------|
| `#!run` | 无 | 是 | 执行此块 |
| `#!compile` | 无 | — | 仅编译不执行（编译型语言） |
| `#!only-code` | 无 | — | 只展开源码到 sources/ |
| `#!skip` | 无 | — | 跳过此块 |
| `#!export <name>` | 标识符 | — | 注册产物到共享表 |
| `#!import <name>` | 标识符 | — | 引用前面 export 的产物 |
| `#!env K=V` | `K=V` | — | 块级环境变量（可多个） |
| `#!workdir <path>` | 路径 | md 所在目录 | 块运行目录 |
| `#!args "a b"` | 字符串 | 无 | 运行参数 |
| `#!stdin "..."` | 字符串 | 无 | 标准输入 |
| `#!timeout 30` | 整数（秒） | 60 | 超时 |
| `#!tag a,b` | 逗号分隔 | 无 | 标签（配合 `--only` / `#!only`） |
| `#!output <file>` | 文件名 | 无 | 捕获 stdout 到文件 |

### 3.4 纯文本段落

代码块之间的 Markdown 文本（标题、段落、列表等）在执行时被跳过，不参与执行流程。但文本中的相对路径引用在 `info` 模式下可用于文档展示。

---

## 四、块间数据流与 export/import 机制

### 4.1 共享产物表

```python
artifacts_table: dict[str, ArtifactEntry] = {}
# ArtifactEntry = {
#     'name': str,           # export 时指定的 name
#     'path': str,           # 产物文件路径
#     'hash': str,           # 产物内容 MD5
#     'source_block': int,   # 来源块序号
#     'source_tag': str|None # 来源块 tag
# }
```

### 4.2 export 流程

1. 块执行完成后，runner 检查该块是否声明了 `#!export <name>`
2. 若声明，runner 根据语言类型和产物路径创建 ArtifactEntry
3. 编译型语言：产物 = 编译后的 .dll/.so/.exe 路径
4. 解释型语言：产物 = 打包后的 zip 路径 或 stdout 输出文件路径
5. 注册到 `artifacts_table[name]`

### 4.3 import 流程

1. 块执行前，runner 检查该块是否声明了 `#!import <name>`
2. 在 `artifacts_table` 中查找对应 entry
3. 找到 → 将产物路径注入环境变量 `MD_IMPORT_<name>`（大写、下划线替换）
4. 未找到 → 记录 warning，不阻断执行（除非 `#!strict` 模式，v2 不做）

### 4.4 output 文件机制

`#!output <file>` 将块的 stdout 写入 `.mdbuild/tmp/<block_idx>-<file>`，供下游块通过 `#!import` 引用。

---

## 五、错误处理与中断策略

### 5.1 块级错误

| 错误类型 | 处理 | 报告字段 |
|----------|------|----------|
| 编译失败 | 记录 error，跳过后续依赖此块的 import | `status=error`, `error=msg`, `duration_ms` |
| 执行超时 | kill 子进程，记录 error | `status=timeout`, `timeout=sec` |
| 执行失败（非零退出码） | 记录 error，**继续执行后续块** | `status=failed`, `exit_code`, `stderr` |
| 输出文件写入失败 | 记录 error | `status=error`, `error=msg` |

### 5.2 全局策略

- **默认**：块失败不中断后续块（类似 shell 脚本 `set +e`）
- **`--strict`**（v2 加入）：任一块失败立即中断
- **`--only tag`**：只执行指定 tag 的块，其他块标记 `status=skipped`

### 5.3 配置/依赖错误

| 场景 | 处理 |
|------|------|
| config.lua 不存在 | 使用空配置，记录 info |
| config.lua 执行失败 | 记录 error，中止执行 |
| deps.toml 不存在 | 跳过依赖检查，记录 info |
| 依赖未安装 | 记录 warning，提示安装命令，继续执行 |

---

## 六、与现有 bridge 架构的对接

### 6.1 复用 LangBridge

```python
from vools.bridge import get_helper

# 在 runner 中，对每个代码块：
helper = get_helper(lang)  # 'python', 'lua', 'shell', 'c', ...
if helper.is_available():
    result = helper.execute_code(code, func_name="__md_entry")
else:
    # 走 fallback 或记录 missing
```

### 6.2 复用 CompileTracker

增量构建的哈希记录复用 `CompileTracker`：

```python
from vools.bridge import get_tracker, CompileMode

tracker = get_tracker()
key = f"md:{md_path}:{block_idx}"
source_md5 = hashlib.md5(code.encode()).hexdigest()
if tracker.is_changed(key, source_md5):
    # 重新编译/执行
    tracker.record(key, source_md5, artifact_path, ...)
```

### 6.3 CompileMode 映射

| md 指令 | CompileMode |
|---------|-------------|
| `#!run` | `NORMAL` |
| `#!compile` | `FORCE`（编译不执行） |
| `#!only-code` | `ONLY_CODE` |
| `--force` CLI | `DEBUG` |

### 6.4 fallback 机制

与 bridge 装饰器一致：编译器不可用时走 Python fallback（如果块语言是 Python），或记录缺失。

---

## 七、极简解析器规格

### 7.1 TOML 子集（deps.py）

支持：
- 键值对：`key = "value"` 或 `key = "value"`（字符串）
- 数组：`key = ["a", "b"]`
- 节标题：`[section]`
- 注释：`# 行注释`
- 整数：`key = 30`

不支持：
- 嵌套表、表数组、多行字符串
- 日期、布尔值（可扩展为 0/1）

解析结果：`dict[str, dict[str, Any]]`（节 → 键值）

### 7.2 YAML 子集（manifest.py）

支持：
- 映射：`key: value`
- 列表：`- item`
- 嵌套映射：缩进 2 空格
- 标量：字符串（引号或裸）、整数

不支持：
- 锚点/引用、多文档、流式语法 `[a, b]`
- 复杂类型（日期、null、布尔）

解析结果：`dict[str, Any]`

### 7.3 降级策略

```python
def parse_yaml(text: str) -> dict:
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        return _minimal_yaml_parse(text)  # 内置子集
```

同理 TOML：优先用 `tomli`（Python 3.11+ 内置 `tomllib`），降级到内置解析器。

---

## 八、增量构建哈希策略

### 8.1 参与哈希的内容

```
md_hash = MD5(
    文件级指令原文 +
    每个代码块的语言 + 指令 + 内容（按顺序拼接）
)

block_hash[i] = MD5(语言 + 指令 + 代码内容)
```

### 8.2 增量判断

```
if md_hash == build.yaml.md_hash and artifact_exists(all_blocks):
    skip = True  # 全部跳过
elif block_hash[i] == build.yaml.blocks[i].source_hash and artifact_exists(block_i):
    skip_block[i] = True
else:
    rebuild_block[i] = True
```

### 8.3 哈希计算时机

- `parse_md()` 阶段：计算 md_hash 和 block_hash
- `run_md()` 阶段：与 build.yaml 对比，决定 skip/rebuild
- `--force` 时忽略所有哈希，全量重跑

---

## 九、执行报告 JSON Schema

```json
{
  "md_path": "script.md",
  "md_hash": "abc123...",
  "build_dir": ".mdbuild",
  "config": { "key": "value" },
  "deps_status": { "missing": ["lua 5.4"], "ok": ["python 3.10"] },
  "blocks": [
    {
      "index": 0,
      "language": "python",
      "tag": null,
      "directives": ["run", "export=main"],
      "status": "ok",           // ok | failed | timeout | skipped | error
      "duration_ms": 12,
      "stdout": "hello\n",
      "stderr": "",
      "exit_code": 0,
      "artifacts": [
        {"name": "main", "path": ".mdbuild/artifacts/main.zip", "hash": "def456..."}
      ],
      "output_file": null
    }
  ],
  "artifacts_table": {
    "main": {"path": "...", "hash": "...", "source_block": 0}
  },
  "total_duration_ms": 45,
  "manifest_path": ".mdbuild/build.yaml"
}
```

---

## 十、完整示例脚本

### script.md

```markdown
#!config config.lua
#!deps   deps.toml
#!entry  main

# 我的多语言脚本

## 配置

```lua #!config
return {
  version = "1.0",
  output_dir = ".mdbuild/tmp"
}
```

## 入口

```python #!run export=main tag=main
import sys

def greet(name):
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet(sys.argv[1] if len(sys.argv) > 1 else "World"))
```

## 编译 C 库

```c #!compile export=calc tag=build
#include <stdio.h>

int add(int a, int b) {
    return a + b;
}
```

## 使用编译产物

```python #!run import=calc tag=test
import ctypes

# MD_IMPORT_calc 环境变量指向 .mdbuild/artifacts/calc.dll
lib = ctypes.CDLL(os.environ["MD_IMPORT_calc"])
lib.add.argtypes = [ctypes.c_int, ctypes.c_int]
lib.add.restype = ctypes.c_int
print(lib.add(3, 4))  # 7
```

## 清理

```shell #!run skip
echo "Cleanup would run here"
```
```

### deps.toml

```toml
# 运行时依赖
[runtime]
python = ">=3.6"
lua = ">=5.1"

# 编译器依赖（编译型语言需要）
[compilers]
gcc = "optional"
```

### config.lua

```lua
return {
  version = "1.0",
  output_dir = ".mdbuild/tmp"
}
```

---

## 十一、子包结构与模块职责

```
bridges/vools/bridge/md/
├── __init__.py      公共 API + __all__（延迟导出）
├── README.md        文档
├── __main__.py      CLI 入口
├── parser.py        md 解析：文件级指令 + 代码块提取
├── directives.py    指令定义/解析/校验
├── config.py        lua 配置加载（复用 bridge.lua）
├── deps.py          toml 依赖解析与检查
├── manifest.py      yaml 清单读写
├── runner.py        执行编排 + 报告
└── artifacts.py     产物目录/hash/增量/清理
```

### 模块接口契约

#### parser.py

```python
def parse_md(md_path: str) -> ParsedMD:
    """解析 md 文件，返回结构化结果。"""

@dataclass
class FileDirectives:
    config: str | None       # config.lua 路径
    deps: str | None         # deps.toml 路径
    build_dir: str           # 默认 ".mdbuild"
    entry: str | None        # 入口 tag
    only: list[str]          # 默认只跑的 tag 列表

@dataclass
class CodeBlock:
    index: int               # 块序号
    language: str            # 语言标识符
    directives: dict[str, str]  # 解析后的块级指令
    content: str             # 代码内容（不含指令行）
    tag: list[str]           # 从指令中提取的 tag

@dataclass
class ParsedMD:
    path: str
    file_directives: FileDirectives
    blocks: list[CodeBlock]
    md_hash: str             # MD5 of 全部块内容
    block_hashes: list[str]  # 每块的 MD5
```

#### directives.py

```python
def parse_block_directives(line: str) -> dict[str, str]:
    """解析代码块内第一行的 #! 指令。"""

def validate_directives(directives: dict[str, str], language: str) -> list[str]:
    """校验指令合法性，返回错误列表。"""

FILE_DIRECTIVE_KEYS: set[str] = {"config", "deps", "build-dir", "entry", "only"}
BLOCK_DIRECTIVE_KEYS: set[str] = {
    "run", "compile", "only-code", "skip",
    "export", "import", "env", "workdir",
    "args", "stdin", "timeout", "tag", "output"
}
```

#### config.py

```python
def load_config(config_path: str | None, md_dir: str) -> dict:
    """加载 lua 配置，返回 dict。config_path 为 None 时自动查找。"""

def load_config_from_block(block: CodeBlock, helper) -> dict:
    """从 #!config 代码块加载配置。"""
```

#### deps.py

```python
def parse_toml(text: str) -> dict[str, dict[str, Any]]:
    """极简 TOML 解析器（或用 tomli/tomllib）。"""

def check_deps(deps_path: str | None, md_dir: str) -> DepsReport:
    """检查依赖，返回报告。"""

@dataclass
class DepsReport:
    ok: list[str]        # 已满足的依赖
    missing: list[str]   # 缺失的依赖
    warnings: list[str]  # 非阻断性警告
```

#### manifest.py

```python
def write_manifest(build_dir: str, report: dict) -> str:
    """原子写入 build.yaml。"""

def read_manifest(build_dir: str) -> dict | None:
    """读取 build.yaml，不存在返回 None。"""

def minimal_yaml_parse(text: str) -> dict:
    """内置极简 YAML 子集解析器。"""

def minimal_yaml_dump(data: dict) -> str:
    """内置极简 YAML 序列化器。"""
```

#### artifacts.py

```python
def ensure_build_dir(build_dir: str) -> None:
    """创建 .mdbuild/ 及子目录。"""

def compute_artifact_hash(path: str) -> str:
    """计算产物文件 MD5。"""

def is_artifact_stale(build_dir: str, block_idx: int, block_hash: str) -> bool:
    """判断块产物是否需要重建。"""

def clean_build(build_dir: str, stale: bool = False, keep: list[str] | None = None) -> None:
    """清理产物目录。"""

def register_artifact(table: dict, name: str, path: str, block_idx: int, tag: str | None) -> None:
    """注册产物到共享表。"""
```

#### runner.py

```python
def run_md(
    md_path: str,
    only: list[str] | None = None,
    force: bool = False,
    debug: bool = False,
    build_dir: str | None = None,
) -> dict:
    """执行 md 脚本，返回执行报告（JSON schema 见第九章）。"""

def run_block(
    block: CodeBlock,
    index: int,
    context: dict,
    artifacts_table: dict,
    config: dict,
) -> BlockResult:
    """执行单个代码块。"""
```

#### __main__.py（CLI）

```python
# python -m vools.bridge.md run script.md [--only tag] [--force] [--debug]
# python -m vools.bridge.md info script.md
# python -m vools.bridge.md code script.md
# python -m vools.bridge.md check script.md
# python -m vools.bridge.md clean script.md [--stale] [--keep tag]
```

#### __init__.py

```python
from .parser import parse_md, ParsedMD, CodeBlock, FileDirectives
from .runner import run_md, run_block
from .manifest import write_manifest, read_manifest
from .artifacts import clean_build, register_artifact
from .deps import check_deps, DepsReport

__all__ = [
    'parse_md', 'ParsedMD', 'CodeBlock', 'FileDirectives',
    'run_md', 'run_block',
    'write_manifest', 'read_manifest',
    'clean_build', 'register_artifact',
    'check_deps', 'DepsReport',
]
```

---

## 十二、M1 任务拆分（逐文件）

| # | 文件 | 任务 | 依赖 |
|---|------|------|------|
| 1 | `parser.py` | 文件级指令提取 + 代码块提取 + 哈希计算 | 无 |
| 2 | `directives.py` | 指令常量 + 解析/校验函数 | 无 |
| 3 | `config.py` | lua 配置加载（复用 bridge.lua helper） | bridge.lua |
| 4 | `deps.py` | 极简 TOML 解析 + 依赖检查 | 无 |
| 5 | `manifest.py` | 极简 YAML 解析/序列化 + 原子读写 | 无 |
| 6 | `artifacts.py` | 目录创建 + hash + 增量判断 + clean | 无 |
| 7 | `runner.py` | 执行编排 + 块执行 + 报告生成 | 1-6 |
| 8 | `__main__.py` | CLI 入口（run/info/code/check/clean） | 1-7 |
| 9 | `__init__.py` | 公共 API + 延迟导出 | 1-7 |
| 10 | `README.md` | 文档 | 全部 |
| 11 | `test_md_bridge.py` | 测试 | 1-10 |

### M1 范围（单文件 MVP）

**必须有**：
- parser：文件级指令 + 代码块提取 + 哈希
- directives：run/compile/only-code/skip + env/tag/export/import/timeout
- config：lua 配置加载
- deps：极简 TOML 解析 + 基础检查
- manifest：极简 YAML 读写（原子写）
- artifacts：目录创建 + hash + 基础增量
- runner：顺序执行 + 报告 + export/import 传参
- CLI：run + info + code

**M2 补齐**：
- 指令全集（workdir/args/stdin/output）
- clean/check CLI
- 增量完善（block_hash 对比）
- 测试补全

---

## 十三、设计决策确认

1. **子包位置与结构**：`bridges/vools/bridge/md/`，多模块拆分
2. **格式分工**：lua 配置、toml 依赖、yaml 清单、py 胶水
3. **产物管理**：`.mdbuild/` + 增量哈希 + 原子写 + .gitignore
