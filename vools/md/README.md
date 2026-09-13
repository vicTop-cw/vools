# vools.md — Markdown 处理子包

Markdown 解析、生成、HTML 转换与工具函数。

## 模块结构

| 模块 | 说明 |
|------|------|
| `parser` | Markdown 文本 → 结构化 AST |
| `generator` | AST → Markdown 文本 |
| `html` | AST / Markdown → HTML |
| `utils` | 工具函数（元数据提取、TOC 生成、代码块提取） |

## 快速上手

```python
from vools.md import parse, generate, to_html, extract_metadata, generate_toc

# 解析
ast = parse("# Hello\n\nWorld")

# 生成
md_text = generate(ast)

# HTML 转换
html = to_html(ast)

# 元数据
meta = extract_metadata(md_text)

# TOC
toc = generate_toc(ast)
```

## 详细文档

- [parser.md](parser.md) — 解析器
- [generator.md](generator.md) — 生成器
- [html.md](html.md) — HTML 转换
- [utils.md](utils.md) — 工具函数
