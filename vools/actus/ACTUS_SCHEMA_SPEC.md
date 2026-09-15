# `.actus.schema.md` 硬性约定格式规范

> **状态**: v0.1 — 内部规范草案  
> **替代目标**: `contracts/action.schema.json`、`#!cfg` 内联元数据块、`#!entry` 等文件级指令  
> **核心原则**: 单一 `.md` 文件 = 完全自包含的动作定义，**无 JSON 文件、无外部 schema 引用**

---

## 1. 文件命名与位置

```
actions/
  convert-file-to-markdown.actus.schema.md
  send-email.actus.schema.md
  scrape-webpage.actus.schema.md
```

- 后缀固定为 `.actus.schema.md`
- 放置在 `actions/` 子目录中（按平台/功能可再分子目录）
- 文件名本身不参与动作标识，`id` 字段由 front-matter 定义

---

## 2. 文件结构总览（顺序不可调换）

一个合法的 `.actus.schema.md` 文件**必须**按以下顺序组成：

```
┌─────────────────────────────────────────────┐
│ 区域 0: AIGC 合规 front-matter (YAML)        │  ← strip_frontmatter 剥离
├─────────────────────────────────────────────┤
│ 区域 1: 动作元数据 (YAML front-matter)        │  ← 替代 #!cfg JSON
├─────────────────────────────────────────────┤
│ 区域 2: 描述文档 (Markdown 正文)              │  ← 人类可读说明
├─────────────────────────────────────────────┤
│ 区域 3: 输入契约 (JSON Schema 代码块)         │  ← 替代 args JSON
├─────────────────────────────────────────────┤
│ 区域 4: 依赖声明 (YAML 代码块)                │  ← pip 依赖 / 系统依赖
├─────────────────────────────────────────────┤
│ 区域 5: 触发器声明 (YAML 代码块)              │  ← cron/watch/webhook/hotkey
├─────────────────────────────────────────────┤
│ 区域 6: 权限声明 (YAML 代码块)                │  ← 所需权限白名单
├─────────────────────────────────────────────┤
│ 区域 7: 实现代码 (带 tag 的代码块)            │  ← 替代 #!entry 指向的块
└─────────────────────────────────────────────┘
```

---

## 3. 区域 0: AIGC 合规 front-matter

```markdown
---
aigc: true
generated-by: atomcode
generated-at: 2026-09-15T10:30:00Z
---
```

**规则**:
- 必须位于文件**第一行**
- 以 `---` 开始、`---` 结束
- 由 `strip_frontmatter()` 剥离，**不参与动作解析**
- 仅作合规留痕，不影响动作语义

---

## 4. 区域 1: 动作元数据 (YAML front-matter)

```markdown
---
id: convert-file-to-markdown
name: Convert File to Markdown
version: 1.0.0
trust: sandbox
entry: main
description: Convert PDF/Word/PPT/Excel/image/audio files to Markdown via MarkItDown
author: vools
platform: desktop
tags: [convert, markdown, ocr, document]
max_instances: 1
deprecated: false
---
```

**规则**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 全局唯一动作标识，kebab-case |
| `name` | string | ✅ | 人类可读名称 |
| `version` | string | ✅ | semver 格式 |
| `trust` | enum | ✅ | `audit` / `trusted` / `sandbox` |
| `entry` | string | ✅ | 实现代码块的 tag 名 |
| `description` | string | ✅ | 一句话描述 |
| `author` | string | ❌ | 作者标识 |
| `platform` | enum | ❌ | `desktop` / `web` / `macos` / `harmonyos` / `linux` |
| `tags` | list | ❌ | 分类标签 |
| `max_instances` | int | ❌ | 最大并发实例数，0=无上限 |
| `deprecated` | bool | ❌ | 是否已弃用 |

**硬性约束**:
- 此 front-matter 是**唯一权威元数据来源**，不再读取 `#!cfg` JSON 块
- `entry` 值必须匹配区域 7 中某个代码块的 `tag`
- `trust` 取值必须在 `('audit', 'trusted', 'sandbox')` 中

---

## 5. 区域 2: 描述文档 (Markdown 正文)

```markdown
# Convert File to Markdown

Convert any supported file format to Markdown using Microsoft's MarkItDown library.

## Supported Formats

- PDF (.pdf)
- Word (.docx)
- PowerPoint (.pptx)
- Excel (.xlsx)
- Images (.jpg, .png, .gif) — with OCR
- Audio (.mp3, .wav) — with transcription
- HTML, CSV, JSON, XML, EPub

## Usage

```python
result = convert_file_to_markdown("report.pdf", enable_ocr=True)
print(result)
```

## Notes

- Requires `pip install markitdown[all]`
- OCR requires additional system dependencies (tesseract)
- Audio transcription requires whisper
```

**规则**:
- 自由格式 Markdown，人类可读
- 由 `vools.md` 解析器处理
- 不参与机器校验，但建议包含 Supported Formats / Usage / Notes 段

---

## 6. 区域 3: 输入契约 (JSON Schema 代码块)

```markdown
## Input Schema

```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "输入文件路径（绝对或相对路径）"
    },
    "enable_ocr": {
      "type": "boolean",
      "default": false,
      "description": "是否启用 OCR 识别图片中的文字"
    },
    "output_path": {
      "type": "string",
      "description": "输出 Markdown 文件路径（可选，默认返回字符串）"
    }
  },
  "required": ["file_path"]
}
```
```

**规则**:
- 代码块语言标记为 `json`
- 代码块指令为 `#!args`（或 `#!input`）
- 内容必须是合法的 JSON Schema (Draft-7)
- 由 `check_args_schema()` 校验
- 运行时由 executor 用于参数校验和 UI 表单生成

---

## 7. 区域 4: 依赖声明 (YAML 代码块)

```markdown
## Dependencies

```yaml
pip:
  - markitdown[all]>=0.0.1
system:
  - tesseract-ocr  # 可选，OCR 时需要
  - ffmpeg         # 可选，音频转写时需要
env:
  - MARKITDOWN_CACHE_DIR=/tmp/markitdown
```
```

**规则**:
- 代码块语言标记为 `yaml`
- 代码块指令为 `#!deps` 或 `#!dependencies`
- `pip`: pip 包列表（支持版本约束）
- `system`: 系统包名（仅作声明，不自动安装）
- `env`: 环境变量声明
- 由 `dependency.py` 解析

---

## 8. 区域 5: 触发器声明 (YAML 代码块)

```markdown
## Triggers

```yaml
- type: watch
  path: ./inbox/
  pattern: "*.pdf"
  debounce_ms: 1000

- type: cron
  expr: "0 9 * * 1-5"
  timezone: Asia/Shanghai

- type: webhook
  path: "/hooks/convert"
  secret_header: "X-Actus-Secret"
```
```

**规则**:
- 代码块语言标记为 `yaml`
- 代码块指令为 `#!triggers`
- 每个触发器必须是合法对象：
  - `cron`: 5 字段 cron 表达式
  - `watch`: 有效路径字符串
  - `webhook`: 可选 `secret_header`
  - `hotkey`: 非空 `key`
  - `on_startup`: 无额外字段
- 由 `check_triggers()` 校验

---

## 9. 区域 6: 权限声明 (YAML 代码块)

```markdown
## Permissions

```yaml
permissions:
  - files:read
  - files:write
  - process:spawn
```
```

**规则**:
- 代码块语言标记为 `yaml`
- 代码块指令为 `#!permissions`
- 每个权限必须在 `PERMISSIONS` 白名单中
- 由 `check_secrets()` / `check_permissions()` 校验

---

## 10. 区域 7: 实现代码 (带 tag 的代码块)

```markdown
## Implementation

```python
# tag: main
from markitdown import MarkItDown
from pathlib import Path

def convert_file_to_markdown(file_path: str, enable_ocr: bool = False, output_path: str = None) -> str:
    """Convert a file to Markdown."""
    md = MarkItDown(enable_plugins=enable_ocr)
    result = md.convert(file_path)
    
    if output_path:
        Path(output_path).write_text(result.markdown, encoding='utf-8')
    
    return result.markdown
```

```python
# tag: helper
def _validate_file(path: str) -> bool:
    """Validate file exists and is supported."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return True
```
```

**规则**:
- 代码块语言标记为实际语言（`python` / `javascript` / `bash` 等）
- 代码块指令为 `#tag: <name>`（定义块标签）
- `entry` 字段值必须匹配某个代码块的 `tag`
- 由 `check_entry_block()` 校验
- 支持多代码块，通过 tag 区分入口和辅助函数

---

## 11. 完整示例

```markdown
---
aigc: true
generated-by: atomcode
generated-at: 2026-09-15T10:30:00Z
---

---
id: convert-file-to-markdown
name: Convert File to Markdown
version: 1.0.0
trust: sandbox
entry: main
description: Convert PDF/Word/PPT/Excel/image/audio files to Markdown via MarkItDown
author: vools
platform: desktop
tags: [convert, markdown, ocr, document]
max_instances: 1
deprecated: false
---

# Convert File to Markdown

Convert any supported file format to Markdown using Microsoft's MarkItDown library.

## Supported Formats

- PDF, Word, PowerPoint, Excel
- Images (with OCR)
- Audio (with transcription)
- HTML, CSV, JSON, XML, EPub

## Usage

```python
result = convert_file_to_markdown("report.pdf", enable_ocr=True)
print(result)
```

## Input Schema

```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "输入文件路径"
    },
    "enable_ocr": {
      "type": "boolean",
      "default": false,
      "description": "是否启用 OCR"
    },
    "output_path": {
      "type": "string",
      "description": "输出 Markdown 文件路径（可选）"
    }
  },
  "required": ["file_path"]
}
```

## Dependencies

```yaml
pip:
  - markitdown[all]>=0.0.1
system:
  - tesseract-ocr
env:
  - MARKITDOWN_CACHE_DIR=/tmp/markitdown
```

## Triggers

```yaml
- type: watch
  path: ./inbox/
  pattern: "*.pdf"
  debounce_ms: 1000
```

## Permissions

```yaml
permissions:
  - files:read
  - files:write
  - process:spawn
```

## Implementation

```python
# tag: main
from markitdown import MarkItDown
from pathlib import Path

def convert_file_to_markdown(file_path: str, enable_ocr: bool = False, output_path: str = None) -> str:
    """Convert a file to Markdown."""
    md = MarkItDown(enable_plugins=enable_ocr)
    result = md.convert(file_path)
    
    if output_path:
        Path(output_path).write_text(result.markdown, encoding='utf-8')
    
    return result.markdown
```

```python
# tag: helper
def _validate_file(path: str) -> bool:
    """Validate file exists and is supported."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return True
```
```

---

## 12. 校验流水线适配

现有 7 步校验流水线需适配新格式：

| 步骤 | 原逻辑 | 新逻辑 |
|------|--------|--------|
| 1. parse_cfg | 解析 `#!cfg` JSON 块 | 解析 YAML front-matter |
| 2. schema_validate | 对照 `action.schema.json` | 对照内置 YAML schema 校验 |
| 3. entry_block | 检查 `#!entry` 与 tag 一致 | 检查 `entry` 字段与 tag 一致 |
| 4. args_schema | 校验 args JSON Schema | 校验 `Input Schema` 代码块 |
| 5. graph_validate | 依赖图无环 | 依赖图无环（不变） |
| 6. dry_run | 展示将要执行的块 | 展示将要执行的块（不变） |
| 7. sandbox_trial | 沙箱试跑 | 沙箱试跑（不变） |

---

## 13. 迁移路径

1. **新动作**: 直接按本规范编写 `.actus.schema.md`
2. **旧动作**: 提供迁移脚本 `migrate_actus_format.py`
   - 读取 `#!cfg` JSON → 提取为 YAML front-matter
   - 读取 `#!entry` → 写入 `entry` 字段
   - 读取 `args` JSON → 写入 `## Input Schema` 代码块
   - 保留原文件作为 `.bak`
3. **兼容性**: 过渡期同时支持 `#!cfg` 和 front-matter，优先 front-matter

---

## 14. 硬性约束清单

| # | 约束 | 校验位置 |
|---|------|----------|
| C01 | 文件后缀必须为 `.actus.schema.md` | 文件扫描器 |
| C02 | 区域 0 front-matter 必须存在 | `strip_frontmatter()` |
| C03 | 区域 1 front-matter 必须存在且合法 | `parse_cfg()` |
| C04 | `id` 必填、全局唯一 | `validate_action()` |
| C05 | `trust` ∈ {audit, trusted, sandbox} | `validate_action()` |
| C06 | `entry` 值必须匹配某个代码块的 tag | `check_entry_block()` |
| C07 | `## Input Schema` 代码块必须是合法 JSON Schema | `check_args_schema()` |
| C08 | `## Dependencies` 代码块必须是合法 YAML | `check_dependencies()` |
| C09 | `## Triggers` 代码块中每个触发器必须合法 | `check_triggers()` |
| C10 | `## Permissions` 代码块中每个权限必须在白名单 | `check_permissions()` |
| C11 | 区域 7 必须存在至少一个代码块 | `check_entry_block()` |
| C12 | 代码块 tag 必须唯一 | `validate_action()` |

---

## 15. 与现有系统的关系

```
┌─────────────────────────────────────────────────────────────┐
│  旧系统                                                      │
│  ┌──────────────┐    ┌────────────────┐    ┌──────────────┐ │
│  │ #!cfg JSON   │    │ action.schema  │    │ #!entry      │ │
│  │ (内联元数据)  │    │ .json (外部)   │    │ (文件级指令) │ │
│  └──────────────┘    └────────────────┘    └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 迁移
┌─────────────────────────────────────────────────────────────┐
│  新系统                                                      │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ .actus.schema.md (单一文件)                               ││
│  │  ├── YAML front-matter (元数据)                          ││
│  │  ├── ## Input Schema (JSON Schema 代码块)                ││
│  │  ├── ## Dependencies (YAML 代码块)                       ││
│  │  ├── ## Triggers (YAML 代码块)                           ││
│  │  ├── ## Permissions (YAML 代码块)                        ││
│  │  └── ## Implementation (带 tag 的代码块)                 ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## 16. 常见问题

**Q: 为什么不用 JSON 文件？**  
A: JSON 无法内联注释，无法承载 Markdown 文档，无法自描述。`.actus.schema.md` 是单一来源，diff 友好，PR review 友好。

**Q: 为什么不用纯 YAML？**  
A: YAML 无法承载代码块语法高亮，无法直接嵌入 JSON Schema。Markdown 是超集。

**Q: 区域 0 和区域 1 都是 front-matter，为什么分开？**  
A: 区域 0 是 AIGC 合规留痕（机器生成标记），区域 1 是动作语义元数据。剥离区域 0 后，区域 1 成为正文的第一个 front-matter，由 `parse_cfg()` 处理。

**Q: 旧动作需要手动迁移吗？**  
A: 提供迁移脚本 `migrate_actus_format.py`，一键转换。过渡期双格式兼容。
