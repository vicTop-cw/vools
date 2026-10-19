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
| `build` | 构建/基础设施 | makefile / dockerfile / docker-compose / nginx / terraform / ansible | 写 `artifacts/build/` | static |
| `template` | 模板语言 | jinja / mako / handlebars / ejs / pug | 写 `artifacts/templates/` | static |
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
makefile/make  dockerfile  docker-compose  nginx  terraform/tf  ansible
jinja/jinja2  mako  handlebars  ejs  pug
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
| `#!target=...` | 数据库连接串 / HTTP URL / mcp 目标 / makefile 目标 | sql / http / mcp / makefile |
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
| `#!out=path` | 输出文件名（支持相对子路径 `config/app.toml`，防 `../` 穿越；绝对路径直接用） | 静态块 / sqlite |
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

## 9. bridge 可用语言盘点（D1）

`bridge/manager.py` 共注册 **27 种语言**（本机实测）：

- **可用（23 种，编译器已装）**：python / c / nim / rust / cpp / go / java / csharp /
  vbnet / julia / freebasic / cangjie / scala / lz / zi / bat / cmd / batch /
  powershell / pwsh / erlang / elixir / haskell
- **不可用（4 种，编译器未装）**：r / mojo / tnr / pentad

静态/协议/渲染类语言（mermaid / dot / latex / jinja / mcp / sigma / html 等）不走
bridge manager，由 `kind` 路由直接分发到对应 handler（`is_available=False` 属正常，
无需编译器）。

## 10. 纯数据块（D2）

| 格式 | role | 产物路径 | 语法校验 |
|---|---|---|---|
| `csv` | data | `artifacts/data/block_N.csv` | stdlib `csv` |
| `tsv` | data | `artifacts/data/block_N.tsv` | stdlib `csv` (delimiter=tab) |
| `xml` | data | `artifacts/data/block_N.xml` | stdlib `ElementTree` |
| `text` / `plain` | data | `artifacts/data/block_N.txt` | 无 |
| `#!out=path` | 覆盖产物文件名 | 任意路径 | — |

## 11. 边界行为（E1）

- **空块**：内容为空则跳过语法校验，正常写空文件。
- **未注册语言**：走 bridge 路径，找不到编译器时 `rc=1`，stderr 含「未知语言」或「不可用」。
- **NUL 字节**：写文件时正常，不做额外处理。
- **超长内容**：10 万字符级写入正常，无特殊上限。
- **大 JSON `#!configs`**：解析正常，不限制嵌套深度。

## 12. 测试

- `tests/test_md_kinds.py`（66 条）：kind 路由 / role 推导 / 静态配置块 / `#!configs` / sqlite /
  http / P1 图表·数学·构建·模板 / P2 纯数据 / 新指令校验 / 边界审视。
- `tests/test_md_review_fixes.py`（17 条）：复核修复覆盖（bridge/python timeout / shell argv / MySQL MYSQL_PWD / bridge 错误标记 / import 菱形 visited / #!import 空格值 / target 白名单 / #!out 子路径 / makefile target / render / sigma）。
- 既有 125 条（`test_md_enhanced.py` / `test_md_bridge.py` / `test_rich.py` /
  `test_webview2.py`）全量回归通过。**合计 208 绿**（201 + 17，1 skip Windows shell）。

## 13. 2026-10 复核发现的真实缺陷（已修复）

独立 MCP 复核发现并修复的真实 bug（按严重度）：

| 编号 | 严重度 | 问题 | 修复 |
|---|---|---|---|
| C1 | **Critical** | bridge 调用无强制兜底超时；python 块 timeout 被静默丢弃 | `_execute_via_bridge` + `_execute_python` 加 ThreadPoolExecutor 软超时 rc=124（线程无法硬 kill，文档注明） |
| M1 | Major | `_execute_shell` 用 `shell=True` + 拼接 args → 命令注入面 | 改 argv 数组 `[bash/sh, -c, content]` |
| M2 | Major | MySQL 密码 `-p<password>` argv 明文（`ps` 可见） | 改 `MYSQL_PWD` 环境变量 |
| M3 | Major | `_execute_via_bridge` 恒返回 exit 0（bridge helper 无 rc API，错误被掩盖） | 错误标记启发式检测，明显错误返回 rc=1 |
| M4 | Major | `resolve_imports` 用 `visited.copy()`，菱形依赖重复展开（A→B/A→C/B→D/C→D 时 D 展开两次；循环 A→B→A 重解析 A） | 改共享引用 + 根文件预置 visited（`root_path` 参数） |
| C2 | Major | lua gen-config bridge 不可用时无 fallback | 实现 `execute_code_lupa`（`pip install lupa` 可选依赖，注入 print/io 重定向） |
| C3 | Major | `#!out` 不支持相对子路径（如 `config/app.toml`），且 `../` 无防护 | 相对路径支持子目录 + `normpath` 穿越阻断；绝对路径向后兼容 |
| C4 | Major | makefile `#!target=xxx` 被 `validate_directives` 拦截（实现支持但校验没放行） | target 白名单补 `makefile / make` |
| m1 | Minor | `#!target` 白名单缺 `mcp` | 已补入 |
| — | Bug | `parse_block_directives` 不支持 `#!import d.md`（空格分隔值，regex 只匹配 `key=val`） | 补 `_SPACE_VALUE_RE`，同时支持 `#!key value` 和无 `#!` 前缀的空格值 |

> 详见 commit `3443c05` / `d1bb1de` / `e59a31a`。