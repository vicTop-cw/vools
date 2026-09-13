# vools.bridge.md

Markdown 即代码：让 .md 文件成为可直接运行的多语言脚本。

## 安装

```bash
pip install vools-bridge-md
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
| `#!tag a,b` | 打标签 |
| `#!breakpoint` | 断点调试 |

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

## 产物目录

```
.mdbuild/
├── build.yaml      构建清单
├── artifacts/      编译产物
├── sources/        展开的源码
└── tmp/            运行中间文件
```

## 许可证

MIT
