# R110 收敛执行工具包（R112，统帅轮-18时）

> 性质：**拍板即可执行的备料**（diff 草稿 + 脚本草稿），本轮不擅自改产品代码。
> 来源：`API_CONVERGENCE_REVIEW_R110.md` 的 A/B 两个候选。

## 一、候选 B1：Action version/name property 补全（diff 草稿）

**落点**：`actus/vools/actus/model.py`，`id`/`trust`/`entry` property 块之后（约 Line 63）。

```diff
     @property
     def entry(self) -> str:
         return self.meta['entry']
 
+    @property
+    def version(self) -> str:
+         """版本号（语义化版本，如 1.2.3）。"""
+        return self.meta['version']
+
+    @property
+    def name(self) -> str:
+         """人类可读名称。"""
+        return self.meta['name']
+
     @property
     def args_schema(self) -> Optional[dict]:
         return self.meta.get('args')
```

**风险**：极低（纯增量，两行 property）。**执行**：`git apply` 该 diff → 跑
`pytest tests/test_model_security_props_r108.py tests/ -k "model or brief"`
→ 全量基线确认零回归。

## 二、候选 A：7 个降级候选的批量脚本草稿

R110 定案的 7 个零外部调用函数（降级 `_` 前缀）：

| 模块 | 函数 | 降级后 |
|---|---|---|
| catalog.py | union | `_union` |
| adapter.py | replacer | `_replacer` |
| cost.py | alert_budget_if_over | `_alert_budget_if_over` |
| selfdrive.py | strong_enabled | `_strong_enabled` |
| platform_tools.py | is_capability_item | `_is_capability_item` |
| vault.py | default_meta_dir | `_default_meta_dir` |
| vault2.py | default_vault_dir | `_default_vault_dir` |

**脚本草稿（改名 + 引用同步 + 校验）**：

```python
# exec_convergence.py —— 拍板后运行
import re, io, os, subprocess, sys

SRC = r"E:\IDEProjects\AI\vools\actus\vools\actus"
PAIRS = [
    ("catalog.py", "union"), ("adapter.py", "replacer"),
    ("cost.py", "alert_budget_if_over"), ("selfdrive.py", "strong_enabled"),
    ("platform_tools.py", "is_capability_item"),
    ("vault.py", "default_meta_dir"), ("vault2.py", "default_vault_dir"),
]

for fn, name in PAIRS:
    path = os.path.join(SRC, fn)
    t = io.open(path, encoding="utf-8").read()
    # 1) 定义改名（def name( → def _name(）
    t2 = re.sub(r"\bdef\s+%s\s*\(" % name, "def _%s(" % name, t)
    # 2) 模块内自引用改名（非 def 行的裸引用）
    t2 = re.sub(r"(?<![\w.])%s\s*\(" % name, "_%s(" % name, t2)
    io.open(path, "w", encoding="utf-8", newline="").write(t2)
    print("renamed:", fn, name)
# 3) 全仓 grep 残留引用 → 人工确认（应只有本模块）
# 4) 全量基线复跑确认零回归
```

**注意**（脚本使用前置）：
1. 先 `grep -rn "<name>"` 全仓确认零外部引用（R110 已定案，执行前复核一次防漂移）
2. 改名后跑 `python -m pytest tests/ -k "<涉及模块>"` + 全量基线
3. `__all__` 若有需同步（执行前 grep `__all__` 确认）

## 三、拍板动线

- 「B1 执行」→ 应用第一节 diff + 回归
- 「A 执行」→ 复核引用 + 跑第二节脚本 + 回归
- 「都执行」→ 顺序：B1（纯增量）→ A（改名）
- 「都不动」→ 本 kit 留档，R110 报告维持现状
