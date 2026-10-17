# vools.actus.actions — 动作层

`vools.actus.actions` 是 vools-actus 的动作注册中心，负责把环境探测（`probe`）发现的
系统能力包装成**可执行动作**，供 CLI/交互工具调用。

## 设计

- **协议**：每个 Action 实现 `id / name / version / description / execute / preview`。
- **注册表**：`get_all_actions()` 扫描本目录下所有子模块并收集实现了 Action 协议的对象。
- **基线动作**：位于 `basics/` 子包（计算器、图片查看器、文本编辑器、待办清单等）。

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
