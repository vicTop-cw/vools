# R116 收尾④ — 惰性 import 深化（package `__init__` 收口）

## 0. 授权与范围

- 用户 `确认授权你做`（2026-11-14）批准"惰性 import"这一比手段 A 更大的 CLI 改善杠杆。
- 这是**已授权的产品代码改动**（突破此前 G1 纪律）；其余纪律（不动系统 PATH/Python、不写真实 HOME 密钥/种子动作、只动本批次文件）维持。
- 本批次文件：`vools/actus/__init__.py`（唯一改动）+ 本计划 + CHANGELOG 条目 + 记忆。

## 1. 当前状态（已查实）

`vools/actus/__init__.py` **已经实现 PEP 562 惰性加载**：
- 存在 `_LAZY` 字典（80+ 符号 → 子模块映射）。
- 存在模块级 `__getattr__(name)`（按 `_LAZY` 解析）。
- 存在 `__dir__()`、`__all__`（由 `_base/_model/_exec/...` 字符串分组聚合）。

但两个最重的符号被**留在了顶层 eager import**，且**未进入 `_LAZY`**：

```python
# vools/actus/__init__.py 顶层（约 23-24 行）
from .model import Action, parse_cfg, parse_cfg_from_file          # ← eager
from .dependency import Dependency, DependencyResolver, get_resolver  # ← eager
```

这两个名字出现在 `__all__` 的 `_model` 分组里，却**不在** `_LAZY` 中——所以它们被立即绑定，绕过了惰性路径。

## 2. 根因（importtime 实测，Store Python 3.13.14）

`python -X importtime -c "import vools.actus.cli"` 累计（µs）：

| 模块 | 累计 |
|---|---|
| `vools.actus.cli` | 153,373 |
| `vools.actus`（包 `__init__`） | 151,438 |
| **`vools.actus.model`** | **126,688** ← 主导 |
| `vools.core` | 84,336（被 model 拉动） |
| `vools.core.dataclass_compat` | 70,059（被 core/model 拉动） |
| `vools.actus.dependency` | 40,553 |
| `vools.actus._proc` | 36,737（被 dependency 拉动） |

结论：`cli.py` 的 80 个子命令 handler **早已在 `_dispatch` 分支内惰性 import**（首个 `from vools.actus.X` 在 806 行）。真正的剩余 eager 成本**仅来自包 `__init__` 对 `model`/`dependency` 的重导出**。把这两者收口进惰性，即可在 `actus --help` / 无参 / `--version` 路径省掉 model 子树（≈150 ms 量级，含 core/dataclass_compat/_proc）。

## 3. 改动（外科手术式，仅 2 处）

### 3.1 删除两条顶层 eager import
```python
# 删除：
from .model import Action, parse_cfg, parse_cfg_from_file
from .dependency import Dependency, DependencyResolver, get_resolver
```

### 3.2 在 `_LAZY` 中补齐这 6 个名字
在 `_LAZY` 字典内新增（建议紧邻 `_model` 语义分组）：
```python
# model（此前 eager，现收口惰性）
'Action': '.model', 'parse_cfg': '.model', 'parse_cfg_from_file': '.model',
# dependency（此前 eager，现收口惰性）
'Dependency': '.dependency', 'DependencyResolver': '.dependency',
'get_resolver': '.dependency',
```

### 3.3 不动的部分
- `__getattr__` / `__dir__` / `__all__` 已通过 `_model` 分组覆盖这 6 个名字，无需改。
- `cli.py` 与各 handler 的 `from vools.actus.model import …` 均为分支内惰性，行为不变。
- 外部 `from vools.actus import Action / parse_cfg / get_resolver / …` 因 PEP 562 `__getattr__` 仍可用，仅改为首次访问时导入。

## 4. 风险与缓解

| 风险 | 缓解 / 已查实 |
|---|---|
| 循环 import：`model`/`dependency` 顶层 `from vools.actus import Action` | 已查：`model.py` 仅 `from .errors` / `from .frontmatter`；`dependency.py` 仅 `from .constants`。均不反向 import `Action`，无环。 |
| 模块自身顶层引用这 6 个名字（NameError） | 已查：`__init__.py` 仅 import 行与 `_model` 字符串列表引用，无裸名使用。 |
| 测试 `mock.patch('vools.actus.Action')` 或 `from vools.actus import Action` 在收集期 | PEP 562 下 `from vools.actus import Action` 触发 `__getattr__`→import model→返回，行为等价；首次访问后名字入模块 dict，patch 正常。 |
| `model`/`dependency` 在缺依赖环境（aider-venv）无法导入 | `model`/`dependency` 仅依赖 `vools.core`（纯 Python），不触碰 cryptography/uvicorn/paramiko/keyring；门禁口径用 Store Python 3.13.14，无此问题。 |
| `import vools.actus` 后静态工具（mypy/IDE）看不到名字 | 通过 `__all__` 仍可见；运行时 `__getattr__` 兜底。可接受（与既有 80+ 惰性符号一致）。 |

## 5. 验证计划（改动后必须全跑）

1. **惰性生效检查**（改动后立即，读不污染门禁）：
   ```bash
   PY=.../WindowsApps/python.exe
   "$PY" -c "import sys, vools.actus; print('model eager?', 'vools.actus.model' in sys.modules)"  # 预期 False
   ```
2. **importtime 复核**：重跑 §2 命令，确认 `vools.actus.model`/`dependency`/`vools.core` 不再出现在 `import vools.actus.cli` 的 eager 链中（只在真正访问时才出现）。
3. **CLI 体感复核**：用 `actus_fast.sh` 测 `actus --help` 与 `actus`（无参）中位数耗时，与 R116-收尾③ 基线对比，预期进一步下降（省掉 model 子树）。
4. **零回归门禁**：改动后**重新**跑 `scripts/run_gate.sh`（带 Tcl、关 harness 沙箱），确认 RC=0、`passed/skipped/failed` 计数与 `OvrHaO` 权威值一致（预期 5997 passed / 5 skipped / 0 failed）。惰性改动属产品代码变更，必须以全门禁实测背书。

## 6. 预期收益

- `actus --help` / 无参 / `--version`：省掉 `model`(127ms)+`dependency`(40ms) 子树（含 `vools.core`/`dataclass_compat`/`_proc`），eager 导入 `vools.actus.cli` 自 153ms 量级显著下降。
- 真实业务命令（`run`/`scan`/`validate`…）首次执行时仍会导入 `model`/`dependency`（handler 内 `from vools.actus.model import …`），故**命令实际执行耗时不变**——收益集中在"首触/无操作"路径，正是 `--help` 这类最高频首屏体感。
- 与 R116-收尾③ `actus_fast.sh`（绕开 UWP 别名 ≈ −12%）叠加，进一步改善 CLI 冷启动。

## 7. 时序纪律

- 后台干净门禁 `OvrHaO`（关沙箱 + 带 Tcl，全量认证）仍在跑；它从磁盘读取模块。**在 `OvrHaO` 回填权威计数前，不改动 `__init__.py`**，避免污染那份认证。
- 顺序：①`OvrHaO` 跑完 → 回填 CHANGELOG/记忆终值；②按本计划实施 §3 改动；③执行 §5 验证；④零回归后提交并补 CHANGELOG 条目与记忆。
