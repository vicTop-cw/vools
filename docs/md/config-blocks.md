# 配置块（Config Blocks）

`vools/md` 支持在 Markdown 文档中嵌入多种配置格式，用于声明 Actus 引擎配置、嵌套语言依赖和配置代码。

## 配置块类型

| 块类型 | 用途 | 语言标识 |
|--------|------|----------|
| `#!config json` | Actus 动作引擎自身配置 | JSON |
| `#!lang toml` | 嵌套语言的依赖声明 | TOML |
| `#!lang yaml` | 嵌套语言的运行配置 | YAML |
| `#!lang lua` | 生成配置代码的配置代码 | Lua |

## 语法

配置块使用 fenced code block 语法，语言标识以 `#!` 开头：

### `#!config json` — Actus 引擎配置

```markdown
#!config json
{
  "actus": {
    "executor": "default",
    "timeout": 30,
    "registry": ["nim", "rust", "go"]
  }
}
```

### `#!lang toml` — 嵌套语言依赖

```markdown
#!lang toml
[dependencies]
nim = "0.9.0"
rust = { version = "1.70", features = ["async"] }
```

### `#!lang yaml` — 嵌套语言配置

```markdown
#!lang yaml
language: nim
compiler: nim
build_options: "-d:release"
```

### `#!lang lua` — 配置生成代码

```markdown
#!lang lua
-- 生成 TOML 依赖声明
local deps = {
  nim = "0.9.0",
  rust = "1.70"
}
local lines = {}
for name, ver in pairs(deps) do
  lines[#lines+1] = string.format('%s = "%s"', name, ver)
end
return table.concat(lines, '\n')
```

## API

### 解析配置块

```python
from vools.md import extract_configs, extract_config_blocks, extract_lang_blocks

# 提取所有配置块
configs = extract_configs(markdown_text)
for cfg in configs:
    print(f"{cfg['type']}/{cfg['subtype']}: {cfg['parsed']}")

# 仅提取 #!config 块
config_blocks = extract_config_blocks(markdown_text)

# 提取 #!lang 块（可按语言过滤）
lang_blocks = extract_lang_blocks(markdown_text, language="toml")
```

### 解析配置内容

```python
from vools.md import parse_config_block

# 解析 TOML
toml_data = parse_config_block('[deps]\nnim = "0.9.0"', "toml")
print(toml_data["deps"]["nim"])  # "0.9.0"

# 解析 YAML
yaml_data = parse_config_block('language: nim', "yaml")
print(yaml_data["language"])  # "nim"

# 解析 Lua
lua_data = parse_config_block('return { name = "test" }', "lua")
print(lua_data["name"])  # "test"
```

### 生成配置文本

```python
from vools.md import render_config

data = {"server": {"host": "localhost", "port": 8080}}

# 渲染为 JSON
json_text = render_config(data, "json")

# 渲染为 TOML
toml_text = render_config(data, "toml")

# 渲染为 YAML
yaml_text = render_config(data, "yaml")
```

### AST 操作

```python
from vools.md import parse, generate, to_html
from vools.md.parser import ConfigBlock, LangBlock

doc = parse(markdown_text)

# 遍历配置块
for node in doc.children:
    if isinstance(node, ConfigBlock):
        print(f"ConfigBlock: {node.config_type}")
        print(f"Content: {node.content}")
    elif isinstance(node, LangBlock):
        print(f"LangBlock: {node.language}")
        print(f"Content: {node.content}")

# 生成 Markdown
md_text = generate(doc)

# 生成 HTML
html_text = to_html(doc)
```

## 依赖策略

所有格式解析器均为**可选依赖**，核心零强制依赖：

| 格式 | 优先依赖 | 回退方案 |
|------|----------|----------|
| JSON | stdlib `json` | 无（始终可用） |
| TOML | `tomllib` (3.11+) | `tomli` → 简化解析器 |
| YAML | `PyYAML` | 简化解析器（缩进嵌套） |
| Lua | `lupa` | 字符串模板引擎 |

## Frontmatter 升级

`extract_metadata()` 已升级为支持嵌套结构、数组和类型推断：

```python
from vools.md import extract_frontmatter

md = '''---
title: Hello
meta:
  author: test
  version: 1.0
tags: [python, markdown]
---'''

result = extract_frontmatter(md)
# result = {
#     "title": "Hello",
#     "meta": {"author": "test", "version": 1.0},
#     "tags": ["python", "markdown"]
# }
```

## 完整示例

```markdown
---
title: 项目配置
meta:
  author: test
  version: 1.0
---

# 项目配置文档

## Actus 配置

```#!config json
{
  "actus": {
    "executor": "default",
    "timeout": 30
  }
}
```

## 依赖声明

```#!lang toml
[dependencies]
nim = "0.9.0"
rust = { version = "1.70" }
```

## 语言配置

```#!lang yaml
language: nim
compiler: nim
build_options: "-d:release"
```

## 动态配置

```#!lang lua
local config = {
  name = "myapp",
  version = "1.0"
}
return config
```
```

## 测试

```bash
# 运行配置解析器测试
pytest tests/md/test_config_parser.py

# 运行 Parser 配置块测试
pytest tests/md/test_parser_config.py

# 运行 Utils 配置测试
pytest tests/md/test_utils_config.py

# 运行 Generator/HTML 配置测试
pytest tests/md/test_generator_html_config.py
```
