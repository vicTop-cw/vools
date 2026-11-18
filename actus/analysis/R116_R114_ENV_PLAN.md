# R116 + R114-B 执行计划（2026-11-13 22时）

> 用户拍板：选项 **1**（收口整段连续会话 4 个既有 F）+ **2**（R114 环境级优化量化）。
> 基线 commit `f6e8fee`。工作树仅 `.workbuddy/` untracked。

## 0. 护栏与熔断（先立，后动）

| # | 约束 | 判红条件 |
|---|---|---|
| G1 | **绝不改动真实 `~/.actus/keys/*`**（用户密钥） | 任何对该目录的写操作 |
| G2 | **绝不改写仓库内 4 个种子动作及其 `.sig`** | `git diff` 出现 `actions/basics/*.actus.schema.md*` |
| G3 | **绝不改用户系统 PATH / 不安装系统级 Python** | 任何系统级变更；量化用临时 venv |
| G4 | 仅改本批次变更文件，禁止整仓格式化 | 范围 diff 审计 |
| G5 | 状态声明 = 实测；不美化 RC=1 | 报告数字与实测不符 |
| G6 | 用例数单一真值：整段连续全量 **6006** | 收集数漂移 |

**可判红基线（本次会话实测，WindowsApps Python 3.13.14 / pytest 9.0.2）**：
整段连续 `pytest tests/` → 6006 用例 / **5997 passed / 5 skipped / 4 failed** / RC=1 / 29m03s / 无 SIGTERM。
验收目标：**RC=0，用例数 6006 不变，无新增 F**。

## 1. R116-A：种子签名 3 例（任务 #7）

**已取证**：`trust_model.KeyManager.load_public_key`（trust_model.py:129-135）为
「HOME `~/.actus/keys` 优先 → 包内置 `keys/` 回退兜底」。
`tests/conftest.py::_pin_isolated_dirs` 用 `shutil.copytree` 把**真实** keys 复制进会话 HOME。
真实 `~/.actus/keys/default.key|pub` mtime = **21:19**（本会话某次测试运行期间），
而种子动作 `.sig` 签发于 11-07 → HOME 新公钥遮蔽包内置旧公钥 → 验签失败。

**待验证假设**：
- H1 包内置 `vools/actus/keys/default.pub` 存在且能验签 4 个种子动作。
- H2 21:19 的 keys 写入者是测试（违反 conftest 隔离）还是人工轮换。
- H3 会话 HOME 不带 `default.pub` 时，`test_seed_signatures.py` 3 例转绿。

**候选修法（按侵入度升序，先验证再择一）**：
1. **A1（首选）**：conftest 复制 keys 时**排除 `default.*`**，让 default 走包内置兜底；
   `test.*` 仍复制供自签用例。仅改 `tests/conftest.py`。
2. A2：完全不复制 keys（最干净，但需确认无其它测试依赖 HOME keys）。
3. A3（不推荐，需 G2 豁免）：用当前 `default.key` 重签 4 个种子动作 —— 改产品产物。

**验证**：`pytest tests/test_seed_signatures.py` 3 例转绿；整段连续全量无回归。

## 2. R116-B：连续会话 state 泄漏（任务 #8）

**已取证**：`test_validate_contracts_r32.py::test_action_path_of` 期望
`V.action_path_of({"path": "actions/a.actus.md"}) == "actions/a.actus.md"`，
整段连续会话实测返回 `E:\IDEProjects\AI\vools\actus\actions/a.actus.md`（被拼上 repo root）。
隔离单跑通过 → 前置测试污染模块级状态（疑似 `validate._REPO_ROOT` / `ACTUS_REPO_ROOT`
/ `os.getcwd` 未还原）。

**方法**：① 读 `validate.action_path_of` 实现定位被污染的全局量；
② 用「前缀文件集合 + 目标文件」二分最小触发组合；
③ 在**责任测试**（而非 conftest 全局兜底）做最小隔离修复，或补 autouse 状态还原夹具。
④ 验证：最小组合复现 → 修复后转绿 → 整段连续全量 RC=0。

## 3. R116-C：整段连续全量门禁 + 记录 + 提交（任务 #9）

- 用 **WindowsApps Python 3.13** 跑 `pytest tests/`（**不得用 aider-venv**：缺
  `cryptography`/`uvicorn`/`paramiko`/`keyring`，会产生成片假 F）。
- 门禁表：用例数 / passed / skipped / failed / RC / 耗时 / SIGTERM / git 污染。
- 范围 diff 审计 + `compileall` + 报告存档 `actus/analysis/` + CHANGELOG + memory + 提交。

## 4. R114-B：环境级优化对照实验（任务 #10）

**不改用户系统环境**（G3）。三组对照，各测 3 次取稳值：

| 组 | 解释器 | 安装形态 | 量化目标 |
|---|---|---|---|
| E0（基线） | UWP 别名 `WindowsApps\python.exe` | editable | 复现 R114 基线 ~620ms |
| E1 | 直接真实 exe `...Python3.13_x64__...\python3.13.exe` | editable | 绕过 UWP 别名的收益（手段 A） |
| E2 | 临时 venv + `pip install <wheel>` | **非 editable** | 消除 finder 钩子的收益（手段 B） |

测量项：`python --version`、`import vools.actus.cli`、`--help`。
**E2 的 wheel 用当前源码现构**（`python -m build` 或 `pip wheel`），装到
`build/r114_env_probe_venv/`，不接触用户主环境。产出
`actus/analysis/R114_ENV_OPT_MEASUREMENT.md`，给出 A/B 实测收益与可执行步骤。

## 5. 迭代顺序

1. R116-A 取证 → 最小修复 → 单文件验证 → 记录
2. R116-B 定位 → 最小修复 → 最小组合验证 → 记录
3. R116-C 整段连续全量 → 门禁表 → 报告/CHANGELOG/memory → 提交
4. R114-B 对照实验 → 量化报告 → 提交

> 任一阶段若超出护栏（G1–G6），立即停止并上报，不擅自扩大范围。
