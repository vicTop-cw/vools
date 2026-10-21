---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 9f2a11add43fbf12a546606fb2b962ab_2daf2850c91011f18b7f525400393706
    ReservedCode1: ANnnPomoBcJy0xXcavETK7/MfZhrwdPOOzpFChwX8ENQ+5x9ag9V2XRH5ji6mOS7CzgFJuJzRMlr1dZYLCVe9AE7+wQVLUSLg1NbdoHWbMi0OONHfRC8BREYz6jeZjggOvgxBva+poeIfRZc2pMW+13vdtL0W7bj4Ley473V7fEazrSm1Xdy6azOOA4=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 9f2a11add43fbf12a546606fb2b962ab_2daf2850c91011f18b7f525400393706
    ReservedCode2: ANnnPomoBcJy0xXcavETK7/MfZhrwdPOOzpFChwX8ENQ+5x9ag9V2XRH5ji6mOS7CzgFJuJzRMlr1dZYLCVe9AE7+wQVLUSLg1NbdoHWbMi0OONHfRC8BREYz6jeZjggOvgxBva+poeIfRZc2pMW+13vdtL0W7bj4Ley473V7fEazrSm1Xdy6azOOA4=
---

# vools-bridges-md「富内容展示与文件链接」能力计划

- 文档版本：v0.1（评审稿）
- 角色：架构设计者（仅计划，不实现）
- 日期：2026-10-16
- 适用代码库：`bridges/vools/bridge/md`
- 宿主假定：内置 WebView2（Chromium）的桌面应用（与 `webview2.py` 现有 native 模式一致）
- 许可约束：Apache-2.0 兼容，不引入 GPL 传染依赖

---

## 1. 现状勘察

勘察基于对 `vools\bridges\vools\bridge\md\` 的实际源码阅读（2026-10-16）。所有结论均可回溯到文件与函数。

### 1.1 代码块解析、语言识别、路由入口

| 关注点 | 现状 | 位置 |
|---|---|---|
| 文件级指令提取 | 仅识别 `#!config / #!deps / #!build-dir / #!entry / #!only`，md 顶部连续 `#!` 行 | `parser.py:_extract_file_directives()` |
| 代码块提取 | fence 块提取，语言标识 + `#!` 指令 + `# tag:` 标签；优先复用 `vools.md.parser`，缺失时走内置 | `parser.py:_extract_blocks_builtin()` / `_extract_blocks_vools_md()` |
| 块级指令解析 | 支持 `#!key=value` 与裸键值；无显式指令时默认 `run` | `directives.py:parse_block_directives()` |
| 指令白名单 | `BLOCK_DIRECTIVE_KEYS` 含运行/产物/webview2 共 27 键 | `directives.py:BLOCK_DIRECTIVE_KEYS` |
| 语言路由 | builtin 语言直连执行（python/shell/bat/cmd/powershell/webview2/sigma），其余走桥接 | `runner.py:_execute_block()`（641-659 行） |
| 可路由语言真源 | `BUILTIN_BLOCK_LANGUAGES` 元组 + `known_languages()` 并集 | `runner.py`（663-720 行） |
| 主入口 | `run_md()` → `run_block()` → `_execute_block()`，带 manifest 增量构建 | `runner.py:run_md()` |

**关键事实**：
- `parser.py:parse_md()` 只产出代码块列表，**丢弃文档正文**（段落/内联内容不保留）。顶层内联 `<svg>...</svg>` 目前不会被解析到——需新增能力。
- `webview2` 已作为 builtin 语言存在（`webview2`/`webview`/`htmlview` 三个别名），路由到 `runner.py:_execute_webview2()` → `webview2.py:execute_webview2_block()`。
- 语言集合动态发现机制（`known_languages()`）对新增语言标记友好，新增 `svg`/`rich` 类标记只需进 `BUILTIN_BLOCK_LANGUAGES` 或注册进 BridgeManager。

### 1.2 `#!export` 与产物管理现状

| 关注点 | 现状 | 位置 |
|---|---|---|
| 产物目录结构 | `build_dir/`（默认 `.mdbuild`）下建 `artifacts/`、`sources/`、`tmp/` 三个子目录 | `artifacts.py:ensure_build_dir()` |
| export 落盘 | `#!export=name` 把块 stdout 写入 `build_dir/tmp/block_{index}_{name}.txt` | `runner.py:run_block()`（574-600 行） |
| 产物登记 | `register_artifact()` 写入共享表（name/path/hash/source_block/source_tag） | `artifacts.py:register_artifact()` |
| 增量与清理 | `compute_artifact_hash()` / `is_artifact_stale()` / `clean_build(stale=...)` | `artifacts.py` |
| manifest | 块级 source_hash + artifact 路径持久化 | `manifest.py` |

**关键事实**：
- export 产物当前写入 `tmp/` 而非 `artifacts/`，而 `clean_build(stale=True)` 会**清空 `tmp/`**——即增量清理会误删 export 产物（既有问题，本次计划建议一并修正）。
- 产物表以「名称」为键，未区分产物类型；富内容展示若引用产物，需要类型感知（图片/SVG/HTML/任意文件）。

### 1.3 现有 Markdown 渲染/预览路径

| 关注点 | 现状 | 位置 |
|---|---|---|
| MD→HTML 转换 | 存在基础转换器，支持标题/段落/代码块/列表/行内样式/链接 | `vools/md/html.py`（`_inline_to_html()` / `_escape()`） |
| 图片语法 | **不支持**：`_inline_to_html()` 仅输出 `<a>`，无 `<img>` 分支 | `vools/md/html.py` |
| 文档级预览 | **不存在**：`__main__.py` 只有 run/info/code/check/clean 五个子命令，无 preview/rich 命令 | `md/__main__.py` |
| WebView2 渲染 | 已有完整 GUI 渲染引擎：窗口管理、双向通信、多实例、主题、事件 | `webview2.py`（1071 行，v2.0） |
| 渲染容器现状 | `WebView2Manager` 单例管理多窗口（block_id 维度），native/pywebview/fallback 三模式 | `webview2.py:WebView2Manager` |

**关键事实**：
- 「渲染/预览」现状仅覆盖「webview2 代码块打开独立窗口」，不覆盖「文档正文中的图片、内联 SVG、内嵌 HTML、文件链接」四类富内容。
- `webview2.py` 已具备完整的 sanitize / CSP / 资源加载能力（`_sanitize_html()`、`_build_csp()`、`_load_local_resource()`），是本计划最直接的复用基础。

### 1.4 与 actus 的关系

| 维度 | actus | bridges-md | 关系 |
|---|---|---|---|
| 语言 | Python + 任意语言入口 | Python 编排 + 任意语言块 | actus 的 action 本质是 `.actus.md` 文件，由 md runner 执行 |
| 产物 | 动作出参（JSON 优先） | export 产物（文件） | 动作出参可映射为 md 的 export 产物 |
| 展示 | 无展示层（纯 CLI/JSON） | webview2 代码块 | actus 动作若要可视化输出，需借用 md 的展示层 |
| 本计划影响面 | 间接（动作可产出富内容） | 直接（新增富内容解析与渲染） | bridges-md 是执行面，actus 是动作定义面 |

---

## 2. 目标能力

### 2.1 富内容展示

让 Markdown 文档中的富内容（图片、SVG、HTML）能**内联预览**，而不是只支持代码块和文字：

| 形态 | 现状 | 目标 |
|---|---|---|
| Markdown 图片 `![](path)` | 不渲染（`_inline_to_html` 无 img 分支） | 支持本地路径、`data:` URI、http(s)（受配置控制） |
| 内联 SVG 代码块 ```svg``` | 无路由（`svg` 不在 `BUILTIN_BLOCK_LANGUAGES`） | 新增 builtin 路由，在预览中内联渲染 |
| 顶层 SVG（文档正文中直接写 `<svg>...</svg>`） | 被丢弃（正文不保留） | 新增正文扫描，提取并渲染 |
| 内嵌 HTML 代码块 ```html``` / ```webview2``` | 已有（`webview2` builtin） | 增强：支持热更新（L1/L2 粒度）、状态保持 |
| HTML 代码块内引用的本地文件 | 部分支持（`_load_local_resource`） | 完善：相对路径解析、类型白名单、符号链接校验 |

### 2.2 文件链接

让 Markdown 中的文件引用能**安全打开**：

| 形态 | 现状 | 目标 |
|---|---|---|
| Markdown 链接 `[text](file://...)` | 仅 `<a>` 标签，浏览器环境才能打开 | 新增文件链接路由：检测本地文件 → 调用系统默认程序打开 |
| Markdown 链接 `[text](relative/path)` | 同上 | 同上，相对路径基于 md 文件所在目录解析 |
| 产物引用（`#!artifact=name`） | 产物登记但无展示层消费 | 新增 artifact 链接：在预览中显示产物缩略/元信息，点击打开 |

### 2.3 配置入口

新增文件级指令 `#!rich`（与现有 `#!config` 并列），控制富内容行为：

```
#!rich=allow-local=true,allow-remote=false,max-inline-size=1048576,svg-sanitize=true,hot-reload=l2
```

---

## 3. 架构设计

### 3.1 新增模块

```
vools/bridges/vools/bridge/md/
├── parser.py              # 改造：新增 scan_rich()，不破坏 parse_md() 契约
├── directives.py          # 改造：新增 #!rich 文件级指令解析
├── runner.py              # 改造：新增 svg/rich builtin 路由
├── webview2.py            # 复用：渲染容器
├── artifacts.py           # 改造：export 产物落盘位置修正 + 类型感知
├── rich/                  # 新增包
│   ├── __init__.py        # RichContent 数据结构
│   ├── scanner.py         # 正文扫描：提取顶层 SVG / 内嵌 HTML / 图片引用
│   ├── sanitizer.py       # SVG/HTML 净化（白名单 + 黑名单）
│   ├── renderer.py        # 富内容 → HTML 片段（嵌入预览文档）
│   ├── linker.py          # 文件链接路由（类型检测 → 打开策略）
│   └── hotreload.py       # 热更新状态保持（L1/L2 粒度）
└── __main__.py            # 改造：新增 `rich` 子命令
```

### 3.2 数据流

```
┌─────────────────────────────────────────────────────────────┐
│ md 文件                                                       │
│   ├─ 文件级指令 (#!rich, #!config, ...)                       │
│   ├─ 正文 (段落, 内联 SVG, 图片, 链接)                         │
│   └─ 代码块 (```python, ```svg, ```html, ...)                 │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ parse_md()  →  ParsedMD (代码块列表)  ← 现有，不变            │
│ scan_rich() →  RichDoc (正文+富内容)   ← 新增，独立入口        │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ renderer.render(RichDoc, config) → HTML 文档                   │
│   ├─ 正文 → HTML (复用 vools/md/html.py + 扩展 img/link)       │
│   ├─ 代码块 → 执行/展开/渲染 (现有 runner)                     │
│   ├─ SVG → sanitize → 内联 HTML                               │
│   ├─ HTML → sanitize → iframe (srcdoc)                        │
│   └─ 图片/文件 → file:// 或 data: URI                         │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ WebView2Manager.open_preview(html, config)                    │
│   ├─ CSP 注入                                                  │
│   ├─ 本地资源加载 (_load_local_resource 扩展)                  │
│   └─ 热更新钩子 (L1: 全文替换 / L2: 受控区域刷新)               │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 关键设计决策

#### D1: 富内容扫描独立于代码块解析

`parse_md()` 的契约是「只提取代码块」，不保留正文。为了不破坏现有契约，新增独立的 `scan_rich()` 函数：

```python
def scan_rich(md_path: str) -> RichDoc:
    """扫描 md 文件，提取正文与富内容。不修改 parse_md() 的行为。"""
```

`scan_rich()` 与 `parse_md()` 可独立调用，也可在 `renderer` 中组合使用。

#### D2: SVG 作为 builtin 语言

`svg` 加入 `BUILTIN_BLOCK_LANGUAGES`，路由到 `_execute_svg()`：
- 默认行为：sanitize 后内联到预览文档
- 带 `#!webview2=true` 时：开独立窗口（与现有 webview2 块一致）
- 带 `#!export=name` 时：同时落盘到 `artifacts/rich/`

#### D3: HTML 代码块的热更新

| 粒度 | 行为 | 状态保持 | 适用场景 |
|---|---|---|---|
| L1（默认） | 全文替换 iframe srcdoc | 无 | 纯展示型 HTML |
| L2 | 仅刷新受控区域（`data-rich-l2` 标记区域） | 保留表单输入、滚动位置、选中状态 | 交互式表单、工具面板 |

L2 通过 WebView2 的 `ExecuteScript` 在 iframe 内定位受控区域，用 `DOMParser` + `replaceChildren` 更新，不重建整个 iframe。

#### D4: 文件链接安全模型

```
链接目标分类：
  ├─ 本地文件（绝对路径、相对路径、file:// URI）
  │   ├─ 在 md 文件所在目录树内 → 允许打开
  │   ├─ 在产物目录内 → 允许打开
  │   ├─ 其它本地路径 → 默认拒绝，需 #!rich=allow-absolute=true
  │   └─ 符号链接 → 校验 realpath 是否在允许范围内
  ├─ data: URI → 允许（类型白名单：image/*, text/html, application/json）
  ├─ http(s) → 默认拒绝，需 #!rich=allow-remote=true
  └─ 其它协议 → 拒绝
```

#### D5: 产物类型感知

产物登记增加 `type` 字段：

```python
# artifacts.py:register_artifact()
type_hint = directives.get("artifact-type") or guess_type(path)
# type ∈ { "text", "image", "svg", "html", "json", "binary" }
```

富内容渲染器据此决定：
- `image`/`svg`/`html` → 内联预览
- `json` → 折叠展示（`<details>` + `<pre>`）
- `text`/`binary` → 仅元信息（大小、修改时间）+ 打开链接

---

## 4. 安全设计

### 4.1 SVG 净化

基于白名单 + 黑名单双重策略：

**允许元素**（白名单）：
`svg, g, path, rect, circle, ellipse, line, polyline, polygon, text, tspan, title, desc, defs, linearGradient, radialGradient, stop, clipPath, mask, pattern, use, symbol, marker, filter, feGaussianBlur, feOffset, feMerge, feColorMatrix, feBlend, feComposite, image`

**禁止特性**（黑名单）：
- `<script>` / `<foreignObject>` / `<animate>` 带脚本表达式
- `on*` 事件属性
- `style` 属性（仅允许 `<style>` 块内的白名单 CSS 属性）
- `href`/`xlink:href` 指向 `javascript:` / `data:text/html` / 外部 URL
- `foreignObject` 内的 HTML（XSS 面）

**实现**：自研纯 Python 解析器（`xml.etree.ElementTree` + 白名单遍历），不依赖 lxml/BeautifulSoup。

### 4.2 HTML 净化

复用 `webview2.py:_sanitize_html()` 现有能力，扩展：
- iframe `srcdoc` 模式（不直接注入主文档，隔离脚本上下文）
- CSP 注入（`default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob: file:;`）
- 禁止 `<iframe>` 嵌套（防二级 sandbox 逃逸）
- 禁止 `<object>`/`<embed>`/`<applet>`

### 4.3 路径安全

| 检查 | 实现 |
|---|---|
| 路径穿越 | 相对路径解析后 `realpath` 校验是否在允许根内 |
| 符号链接逃逸 | `os.path.realpath()` 展开后再次校验 |
| 设备路径 | 拒绝 `CON`/`NUL`/`COM1` 等 Windows 设备名 |
| UNC 路径 | 拒绝 `\\server\share` 形式（网络共享） |
| 路径长度 | 上限 4096 字符 |
| 文件类型白名单 | 图片（.png/.jpg/.gif/.svg/.webp）、HTML（.html/.htm/.xhtml）、文本（.txt/.md/.json/.xml）、其它（需显式允许） |

### 4.4 资源加载隔离

WebView2 预览使用独立 `CoreWebView2Environment`（与代码块渲染窗口隔离），CSP 按预览内容动态生成，不继承宿主应用权限。

---

## 5. 接口设计

### 5.1 `scan_rich()` 返回值

```python
@dataclass
class RichDoc:
    """md 文件的富内容视图。"""
    source_path: str
    body_html: str            # 正文 → HTML（含 img/link 标签）
    inline_svgs: list[SVGFragment]  # 顶层内联 SVG
    inline_htmls: list[HTMLFragment]  # 顶层内嵌 HTML 片段
    file_links: list[FileLink]  # 文件链接列表
    artifacts: list[ArtifactRef]  # 产物引用
    config: RichConfig       # #!rich 解析结果
```

### 5.2 `render()` 返回值

```python
def render(doc: RichDoc, *, interactive: bool = False,
           hot_reload: str = "l1") -> RenderResult:
    """渲染富内容文档为 HTML 字符串。"""
    return RenderResult(
        html=...,              # 完整 HTML 文档
        csp=...,               # CSP 头
        links=...,             # 文件链接列表（供宿主路由打开）
        open_requests=...,     # 待打开请求（需宿主执行）
    )
```

### 5.3 CLI 子命令

```
vools md rich <path> [--output <html>] [--open] [--serve]
  --output   导出为 HTML 文件（不打开 WebView2）
  --open     渲染后用系统默认程序打开（或 WebView2）
  --serve    启动本地 HTTP 服务，支持热更新
  --config   覆盖 #!rich 配置（命令行参数优先）
```

### 5.4 文件链接路由接口

```python
class FileLinkRouter:
    """宿主可替换的文件链接路由。"""
    def open(self, link: FileLink) -> bool:
        """打开文件链接，返回是否成功。"""
    def can_open(self, link: FileLink) -> bool:
        """判断能否打开该链接。"""
```

默认实现：Windows 用 `os.startfile()`，Linux 用 `xdg-open`，macOS 用 `open`。宿主可注入自定义实现（如用 WebView2 内置查看器）。

---

## 6. 与现有能力的映射

| 现有能力 | 本计划如何使用 | 改动 |
|---|---|---|
| `webview2.py` 渲染容器 | 预览容器 | 复用，不修改 |
| `webview2.py:_sanitize_html()` | HTML 净化 | 复用，扩展 iframe srcdoc 支持 |
| `webview2.py:_build_csp()` | CSP 生成 | 复用，扩展 per-preview 动态 CSP |
| `webview2.py:_load_local_resource()` | 本地资源加载 | 扩展：支持 SVG/HTML/data URI |
| `vools/md/html.py:_inline_to_html()` | 正文 HTML 转换 | 扩展：新增 img/link 分支 |
| `parser.py:parse_md()` | 代码块提取 | 不修改（契约保持） |
| `parser.py:_extract_file_directives()` | 文件级指令 | 扩展：新增 `#!rich` |
| `runner.py:BUILTIN_BLOCK_LANGUAGES` | 语言路由 | 扩展：新增 `svg` |
| `artifacts.py:register_artifact()` | 产物登记 | 扩展：新增 type 字段 |
| `artifacts.py:ensure_build_dir()` | 产物目录 | 扩展：新增 `rich/` 子目录 |

---

## 7. 实施阶段

| 阶段 | 内容 | 出口 |
|---|---|---|
| P0 | 基础解析：`scan_rich()` + `RichDoc` 数据结构 + `#!rich` 指令 | 可提取正文与富内容 |
| P1 | 基础渲染：`render()` + img/link 扩展 + 预览 CLI | 图片/链接可预览 |
| P2 | SVG 支持：`svg` builtin 路由 + sanitizer + 内联渲染 | SVG 可内联预览 |
| P3 | HTML 热更新：L1/L2 粒度 + 状态保持 | 交互式 HTML 可用 |
| P4 | 文件链接：FileLinkRouter + 系统打开 + 安全校验 | 文件链接可安全打开 |
| P5 | 产物集成：export 位置修正 + 类型感知 + artifact 链接 | 产物可预览可打开 |
| P6 | 宿主集成：内置查看器 + WebView2 隔离 + 热更新服务 | 完整体验 |

依赖关系：P0 → P1 → (P2, P3 可并行) → P4 → P5 → P6。

---

## 8. 风险与开放问题

| # | 问题 | 选项 | 推荐 |
|---|---|---|---|
| 1 | SVG 代码块语言标记命名 | A) 直接用 `svg` 进 BUILTIN_BLOCK_LANGUAGES；B) 用 `rich-svg` 避免未来与其它桥接冲突 | A：`svg` 语义清晰，进 builtin 即唯一路由；冲突面由 `known_languages()` 并集去重兜底 |
| 2 | `parse_md()` 是否保留文档正文 | A) 新增独立 `scan_rich()` 不动现有契约；B) 在 `ParsedMD` 增加 `body` 字段 | A：契约零破坏，正文扫描按需触发 |
| 3 | export 落盘位置是否纳入本次修正 | A) 修正到 `artifacts/rich/` 并兼容旧路径读取；B) 保持 `tmp/` 不动 | A：否则增量清理误删产物，富内容引用产物不可靠 |
| 4 | 远程图片默认策略 | A) 默认禁 + opt-in；B) 默认允许 | A：安全优先，隐私面可控 |
| 5 | 文件打开方式 | A) 系统默认程序优先，内置查看器留接口；B) 优先内置查看器 | A：首期零新增渲染依赖，查看器作为 P6 试点 |
| 6 | 富内容配置入口 | A) 新增文件级指令 `#!rich`；B) 全部并入 `#!config` TOML | A：与现有文件级指令风格一致，解析零成本 |
| 7 | L2 热更新状态保持粒度 | A) 仅受控表单控件+滚动位置；B) 全量组件状态 | A：可测、可控；自定义组件状态标注为不保证 |
| 8 | SVG `style` 属性策略 | A) 默认禁 style 属性，仅受控 `<style>` 块；B) 允许 style 白名单 | A：缩小攻击面，简化 sanitize |
| 9 | 符号链接逃逸校验 | A) 本期做 `realpath` 校验；B) 列为遗留风险 | A：路径穿越防护完整性要求（如成本可控） |
| 10 | CLI `rich` 预览入口 | A) 本期新增；B) 仅宿主通道 | A：便于手工验收与可测试性 |
*（内容由AI生成，仅供参考）*