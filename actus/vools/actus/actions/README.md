# vools.actus.actions — 动作层

`vools.actus.actions` 是 vools-actus 的**基座种子动作**层（三层动作边界的第 1 层，
docs/08 §1）：动作定义随 wheel 分发，`pip install vools-actus` 后即有 4 个基线 GUI 动作。

## 单一真源

动作定义在**同目录的 `.actus.schema.md`**（YAML front-matter 元数据 + 带 tag 的代码块实现），
Python 侧只提供兼容 façade：

```
actions/
├── basics/                          # 内置基线动作（每个动作一个 .actus.schema.md）
│   ├── calculator.actus.schema.md   # ← 单一真源（元数据 + webview2 实现）
│   ├── todo-list.actus.schema.md
│   ├── text-editor.actus.schema.md
│   ├── image-viewer.actus.schema.md
│   └── __init__.py                  # ← 兼容 façade（惰性代理，不硬编码元数据）
├── __init__.py                      # 导出 + load_action
└── README.md                        # 本文件
```

**约定**：
- 每个动作一个 `.actus.schema.md`，`entry` 指向带 `tag=main` 的实现块；
- Python façade 只做「取元数据 + 转调引擎 execute」，元数据永远跟 `.md` 走；
- 新增动作 = 加一个 `.actus.schema.md`（引擎自动发现，无需改 Python）。

## 目录

```
actions/
├── basics/          # 内置基线动作（每个模块一个 Action）
├── __init__.py      # get_all_actions() 发现与注册入口
└── README.md        # 本文件
```

## 约定

- 每个含 `__init__.py` 的子目录必须有 `README.md`。
- 每个非 `__init__` 的 `.py` 必须显式声明 `__all__`。
- 动作元数据禁止在 Python 侧硬编码（单一真源是 `.actus.schema.md`）。

## 分类体系 v2.0

种子动作已带 5 维度分类（front-matter，docs/03 §2）：

| 动作 | kind | purpose | trigger |
|------|------|---------|---------|
| calculator | exec | [compute, control] | [manual] |
| todo-list | exec | [control, data-store] | [manual] |
| text-editor | exec | [control, data-store] | [manual] |
| image-viewer | exec | [source] | [manual] |
