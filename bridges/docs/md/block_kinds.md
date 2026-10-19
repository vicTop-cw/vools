# Block Kinds & Roles — 内嵌块三层分类

> 真源：`vools/bridges/vools/bridge/md/runner.py`（`LANGUAGE_KIND_MAP` / `DEFAULT_ROLE_MAP` / `ROLE_KIND_MAP`）
> 语义定义：`vools/docs/md/config-blocks.md`

## 1. 三层分离

| 层 | 名称 | 含义 | 示例 |
|---|---|---|---|
| L1 | **language** | 语法格式标记 | `python` `toml` `mermaid` `sql` |
| L2 | **role** | 语义用途（产出什么） | `deps` `runtime` `gen-config` |
| L3 | **kind** | 执行模式（怎么跑） | `exec` `static` `protocol` `bridge` |

**推导顺序**：`language → role → kind`，可用 `#!role=` 显式覆盖。

## 2. 语义角色（role）

| role | 含义 | 触发语言 | 处理方式 | kind |
|---|---|---|---|---|
| `deps` | 目标语言依赖声明 | toml | 写 `artifacts/config/deps/` | static |
| `runtime` | 目标语言运行配置 | yaml / yml | 写 `artifacts/config/runtime/` | static |
| `legacy` | 老旧配置 | ini | 写 `artifacts/config/legacy/` + 语法校验 | static |
| `gen-config` | 动态生成配置（脚本执行后 stdout 落盘） | lua | **执行**脚本 → `artifacts/config/gen/` | exec |
| `action-config` | actus 动作配置（`#!configs` 裸指令） | json + `#!configs` | 元数据解析，**不进 build_dir** | meta |
| `data` | 纯数据展示 | csv / tsv / xml / text | 写 `artifacts/data/` | static |
| `diagram` | 图表 | mermaid / plantuml / dot | 写 `artifacts/diagram/` | static |
| `math` | 数学公式 | latex / math / tex | 写 `artifacts/math/` | static |
| `build` | 构建/基础设施 | makefile / dockerfile / nginx | 写 `artifacts/build/` | static |
| `generic` | 默认 | 其他 | 按 language 决定 | — |

## 3. 执行模式（kind）

| kind | 含义 | 处理函数 |
|---|---|---|
| `exec` | 写临时文件 + 子进程直接跑 | `_dispatch_exec` |
| `bridge` | 通过 bridge 编译器执行 | `_execute_via_bridge` |
| `static` | 只写产物文件（可选语法校验） | `_dispatch_static` |
| `protocol` | 通过协议调用外部服务 | `_dispatch_protocol` |
| `database` | 执行数据库查询 | `_dispatch_database` |
| `render` | 富内容展示（sanitize + 卡片） | `_execute_rich_block` |
| `gui` | 桌面窗口渲染 | `_execute_webview2` |
| `sigma` | ΣLang 规约块 | `_execute_sigma` |
| `meta` | actus 元数据解析 | `_execute_action_config_block` |

## 4. 内置语言分类总表

### 4.1 exec（写临时文件 + 子进程）

```
python  shell/bash/sh  bat/batch/cmd  powershell/pwsh  node/nodejs/js/javascript
lua（role=gen-config）
```

### 4.2 static（只写文件）

```
css  json  toml  yaml  ini  csv  tsv  xml  text  plain
mermaid/mmd  plantuml/puml  dot/graphviz  latex/math/tex
makefile/make  dockerfile  docker-compose  nginx
```

### 4.3 protocol（协议调用）

```
mcp  http
```

### 4.4 database（数据库）

```
sql  sqlite  mysql  postgresql/pgsql
```

### 4.5 render（富内容展示）

```
html  svg  rich
```

### 4.6 gui（桌面窗口）

```
webview2  webview  htmlview
```

### 4.7 sigma（ΣLang）

```
sigma  sigma-spec  sigma-md
```

### 4.8 bridge（编译执行，31 种语言）

```
c  cpp/c++  csharp/c#  cangjie  cypy  dart  elixir  erlang  freebasic
go/golang  haskell  java  julia  kotlin  lua*  lz  mojo  moonbit  nim
pentad  perl  php  r  ruby/rs  rust  scala  swift  tnr  typescript/ts
vbnet  vbscript  zi  zig
```

> `lua*`：默认 role=gen-config → kind=exec；若显式 `#!role=generic` 则回落到 bridge。

## 5. 配置块语义（docs/md/config-blocks.md 对齐）

| 格式 | role | 含义 | 依赖策略 |
|---|---|---|---|
| `json` | generic（默认） | 通用静态配置 | stdlib `json` |
| `toml` | `deps` | 目标语言**依赖声明** | `tomllib`（3.11+）→ `tomli` fallback |
| `yaml` | `runtime` | 目标语言**运行配置** | `PyYAML`，未装则降级仅写文件 |
| `lua` | `gen-config` | **动态生成配置**（脚本执行，stdout → 配置文件） | bridge `lua` 编译器 → `lupa` fallback |
| `ini` | `legacy` | 老旧配置 | stdlib `configparser` |

`#!configs`（裸指令）→ `action-config` role：actus 动作配置块，只做元数据解析，不进 `build_dir`。

## 6. 新增指令

| 指令 | 作用 | 适用 |
|---|---|---|
| `#!role=...` | 覆盖语义角色 | 任意块 |
| `#!target=...` | 数据库连接串 / HTTP URL | sql / http |
| `#!method=GET/POST/...` | HTTP 方法 | http |
| `#!headers={...}` | HTTP 请求头（JSON） | http |
| `#!body=...` | HTTP 请求体（优先级高于块内容） | http |
| `#!url=...` | HTTP URL（与 target 同义） | http |
| `#!format=...` | 产物格式（如 yaml / json） | 静态块 |
| `#!schema=path` | JSON Schema 校验文件 | json / yaml |
| `#!validate=syntax/schema/none` | 静态块校验模式 | 静态块 |
| `#!render=...` | 渲染模式 | 静态块 |
| `#!on_error=fail/skip/report` | 错误处理策略 | 任意块 |
| `#!quiet` | 静默（不打印结果） | 任意块 |
| `#!out=path` | 输出文件名 | 静态块 / sqlite |
| `#!configs`（裸指令） | actus 动作配置块 | json |

## 7. 执行流程

```
parse_md → CodeBlock
    ↓
resolve_block_role(block)   # #!role > #!configs > DEFAULT_ROLE_MAP > generic
    ↓
resolve_block_kind(block)   # ROLE_KIND_MAP > LANGUAGE_KIND_MAP > bridge
    ↓
_execute_block → _execute_by_kind → 对应 handler
```

## 8. 向后兼容

- `_execute_block(block, context, config, args, timeout)` 签名不变，调用方零迁移。
- `css` 块保持历史输出路径 `artifacts/css/`。
- 所有未显式 `#!role` 的既有块（python/shell/mcp/sigma 等）行为与重构前一致。

## 9. 测试

- `tests/test_md_kinds.py`（39 条）：kind 路由 / role 推导 / 静态配置块 / `#!configs` / sqlite / http / 新指令校验。
- 既有 125 条（`test_md_enhanced.py` / `test_md_bridge.py` / `test_rich.py` / `test_webview2.py`）全量回归通过。