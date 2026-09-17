# vools.bridge.md — Markdown 即代码

让一个 `.md` 文件成为可直接运行的多语言脚本。

- **py 是胶水** — 解析、编排、依赖检查、产物管理
- **md 是载体** — 代码块承载各语言代码，`#!` 指令控制行为

## 安装

```bash
pip install vools-bridge-md
```

或从源码安装：

```bash
git clone https://github.com/vools/vools-bridge-md.git
cd bridges
pip install -e .
```

## 核心功能

### 1. 支持 31 种桥接语言

| 类型 | 语言 |
|------|------|
| **编译型** | C, C++, Nim, Rust, Go, 仓颉, Mojo, MoonBit, Zig, Swift, Dart, Haskell, C#, VB.NET, Java, Scala, Kotlin, FreeBASIC |
| **解释型** | Python, Shell/Bash, Julia, R, Lua, Perl, Ruby, PHP, TypeScript, PowerShell, VBScript, Erlang, Elixir, Tnr, LZ, Zi, Cypy |
| **GUI 渲染** | WebView2 (Chromium 内核) |

### 2. WebView2 GUI 渲染

在 Markdown 中嵌入 **WebView2 (Chromium)** 控件，渲染 GUI 并支持事件交互。

> **重要**：这不是旧的 IE WebBrowser，而是 **Edge Chromium 内核**！

```markdown
```webview2 title="我的应用" width=800 height=600
<!DOCTYPE html>
<html>
<body>
  <button onclick="sendToPython('clicked')">点击我</button>
  <script>
    function sendToPython(msg) {
      window.chrome.webview.postMessage({ type: 'event', data: msg });
    }
  </script>
</body>
</html>
```
```

## 快速上手

```markdown
#!config config.lua
#!deps   deps.toml
#!entry  main

# 入口

```python #!run export=main tag=main
print("Hello, World!")
```

## 清理

```shell #!skip
echo "Cleanup"
```
```

## 使用

```bash
# 执行
python -m vools.bridge.md run script.md

# 只执行指定 tag
python -m vools.bridge.md run script.md --only main

# 干跑（查看块/指令/依赖）
python -m vools.bridge.md info script.md

# 只展开源码
python -m vools.bridge.md code script.md

# 依赖检查
python -m vools.bridge.md check script.md

# 清理产物
python -m vools.bridge.md clean script.md
```

## Python API

```python
from vools.bridge.md import run_md, parse_md, clean_build

# 执行
result = run_md("script.md", only=["main"])
print(result['blocks'][0]['stdout'])

# 解析
parsed = parse_md("script.md")
for block in parsed.blocks:
    print(block.language, block.directives)
```

## #! 指令

### 文件级

| 指令 | 说明 |
|------|------|
| `#!config <path>` | 配置文件 |
| `#!deps <path>` | 依赖文件 |
| `#!build-dir <path>` | 产物目录 |
| `#!entry <tag>` | 入口块 tag |
| `#!only a,b` | 默认只跑的 tag |

### 块级

| 指令 | 说明 |
|------|------|
| `#!run` | 执行（默认） |
| `#!compile` | 仅编译不执行 |
| `#!only-code` | 只展开源码 |
| `#!skip` | 跳过 |
| `#!export <name>` | 注册产物 |
| `#!import <name>` | 引用产物 |
| `#!env KEY=VAL` | 环境变量 |
| `#!workdir <path>` | 工作目录 |
| `#!args <val>` | 命令行参数 |
| `#!stdin <val>` | 标准输入 |
| `#!timeout 30` | 超时秒数 |
| `#!output <file>` | 输出文件 |
| `#!breakpoint` | 断点调试 |

### WebView2 专用指令

| 指令 | 说明 | 默认值 |
|------|------|--------|
| `title` | 窗口标题 | "WebView2 Window" |
| `width` | 窗口宽度 | 800 |
| `height` | 窗口高度 | 600 |
| `resizable` | 是否可调整大小 | true |
| `blocking` | 是否阻塞等待 | true |
| `devtools` | 是否启用开发者工具 | false |
| `theme` | 主题 (light/dark/blue/minimal) | light |
| `html` | 外部 HTML 文件 | - |
| `inject` | 注入的 JS 代码 | - |

## WebView2 JS API

### 发送消息到 Python

```javascript
// 基本发送
sendToPython('event', { foo: 'bar' });

// 带回调的发送
sendToPython('request', { id: 1 }, function(response) {
    console.log('收到回调:', response);
});
```

### 接收来自 Python 的消息

```javascript
// 方式 1: 回调函数
window.onPythonMessage = function(data) {
    console.log('收到:', data);
};

// 方式 2: 事件监听
window.addEventListener('pythonMessage', function(e) {
    console.log('收到:', e.detail);
});
```

### 便捷 API

```javascript
// 触发事件
triggerEvent('click', { x: 100, y: 200 });

// 等待页面就绪
window.webview.ready().then(function() {
    console.log('页面已就绪');
});

// 发送消息（别名）
window.webview.send('message', data);
window.webview.onMessage(callback);
window.webview.trigger('eventName', data);
```

## 增量构建

基于 `block_hash` 对比：

- 未变块自动跳过（`status=skipped`）
- `--force` 强制全量重跑
- `.mdbuild/build.yaml` 记录上次执行状态

## 多文件支持

### #!import

从其他 md 文件导入代码块：

```markdown
#!entry main

```python #!run import=utils.md tag=main
```
```

### 跨文件产物引用

```markdown
# 文件 a.md
```python #!run export=data tag=main
print("data")
```

# 文件 b.md
```python #!run import=data tag=main
```
```

## 库级支持

### 扫描目录

```python
from vools.bridge.md import scan_library

md_files = scan_library("/path/to/library")
```

### 构建库级 manifest

```python
from vools.bridge.md import build_library_manifest

manifest = build_library_manifest("/path/to/library")
```

### 执行整个库

```python
from vools.bridge.md import run_library

result = run_library("/path/to/library", only=["main"])
```

## 高级调试与性能分析

### 断点调试

```bash
python -m vools.bridge.md run script.md --debug
```

### 性能分析

```python
from vools.bridge.md import run_md

result = run_md("script.md", profile=True)
```

### 并行执行

```python
from vools.bridge.md import run_md

result = run_md("script.md", parallel=True)
```

## 示例

| 文件 | 说明 |
|------|------|
| `examples/hello.md` | Hello World |
| `examples/pipeline.md` | 数据管道 |
| `examples/multi_language.md` | 多语言混合 |
| `examples/library.md` | 库级示例 |
| `examples/webview2.md` | WebView2 GUI 渲染示例 |

## 产物目录

```
.mdbuild/
├── build.yaml      构建清单
├── artifacts/      编译产物
├── sources/        展开的源码
└── tmp/            运行中间文件
```

## 依赖安装

### WebView2 (Chromium)

```bash
pip install pythonnet  # 原生 SDK（推荐）
# 或
pip install pywebview   # 轻量级方案
```

> **注意**：Windows 10/11 已预装 WebView2 运行时。

### 其他桥接语言

根据需要安装对应的编译器：

```bash
# Nim
curl https://nim-lang.org/choosenim/init.sh -sSf | sh

# Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Go
go version  # 检查是否已安装

# 其他语言...
```

## 许可证

MIT
