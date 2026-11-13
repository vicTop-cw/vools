# R114 — actus CLI 启动慢诊断报告

> 生成：2026-11-13（统帅轮 21时）｜方法：`-X importtime` 画像 + 多运行时实测
> 结论先行：**代码侧已最优，主因在运行环境（Windows Store Python UWP 别名 + 可编辑安装 finder）。旧「import tax ~3.16s」不可复现，真实 warm 启动 620–920ms，冷首跑 1–2.6s。**

---

## 1. 定位真实运行时

用户实际执行的 `actus` 命令：

- 控制台脚本：`C:\Users\victo\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\Scripts\actus.exe`
- 解释器：**Windows Store Python 3.13**，经 **UWP 应用执行别名**（`C:\Users\victo\AppData\Local\Microsoft\WindowsApps\python.exe`）重定向启动。
- 安装方式：**可编辑安装**（`pip install -e`，源码在 `E:/IDEProjects/AI/vools/actus`）。

测试用 venv（`/e/Tools/aider-venv`）仅从 cwd 解析 `vools.actus`，**并非**真实运行时，故所有"用户体感"数字均用上述 Windows Store Python 取得。

---

## 2. 实测数据（warm，每项正确 3 次取稳值）

| 测量项 | 命令 | 耗时 |
|---|---|---|
| 解释器冷启动基线 | `python --version`（UWP 别名） | **260–313 ms** |
| vools 导入子树（含 site/sitecustomize/可编辑 finder + 全 vools） | `python -c "import vools.actus.cli"` | **~67 ms** |
| CLI 帮助 | `actus --help` | ~620 ms（首跑冷 ~1008 ms） |
| CLI 无参 | `actus` | ~634 ms |
| 轻命令（读索引） | `actus list` | ~622 ms warm / **~2619 ms 冷首跑** |
| 探测命令 | `actus runtimes` | ~920 ms |

> 说明：`python -c "import ..."` 的 67ms 由 `time.perf_counter()` 在 `-c` 代码内起算，
> **不含解释器启动**（那部分已先于 `-c` 完成），故 67ms = vools + site + sitecustomize + 可编辑 finder 的导入子树纯耗时。

---

## 3. import 树热点（`-X importtime`，累计 µs）

| 模块 | 累计 (µs) | 归属 |
|---|---|---|
| `site` | 218,311 | 解释器启动 |
| `sitecustomize` | 104,497 | 解释器启动（异常偏高，疑似某工具 sitecustomize 钩子） |
| `__editable___cypyc_0_1_0_finder` | 88,014 | **可编辑安装 finder（cypyc 包，actus 不用）** |
| `pathlib` / `pathlib._abc` | 72,922 / 64,501 | 标准库 |
| `vools.actus.cli` | 66,864 | 代码侧（CLI 入口子树） |
| `vools.actus.model` | 52,639 | 代码侧（最重 vools 模块） |
| `glob` | 39,317 | 标准库 |
| `vools.core` + `vools.core.dataclass_compat` | ~64,000 | 代码侧（基础类型） |
| `tempfile` / `re` / `dataclasses` / `functools` / `inspect` | 27,654 / 26,271 / 22,896 / 21,085 / 20,354 | 标准库 |
| `vools.actus.dependency` | 19,238 | 代码侧 |
| `ctypes` / `subprocess` | 17,838 / 8,988 | 标准库（`_proc` 引入） |

---

## 4. 结论分解

### 4.1 旧「3.16s」为何不可复现
真实 warm 启动稳定在 **620–920 ms**。所谓 3.16s 来自**空闲后冷盘/导入缓存失效的首跑**
（实测 `actus list` 冷首跑 2619ms，接近旧值量级）。属 OS 磁盘缓存现象，非代码退化。

### 4.2 代码侧已最优（无需动刀）
1. **子命令懒加载已落地**：`main()`→`_dispatch()` 在命令真正执行时才 `from .mcp_server import serve` 等
   （`cli.py:128-134` 可见 `mcp` 分支内联懒导入）；import 树未拉入任何重子命令模块（ai/scaffold/desktop…）。
2. **启动链零可避免重依赖**：在 `__init__`/`model`/`dependency`/`constants`/`frontmatter`/`errors` 顶层
   检索 `yaml|toml|numpy|pandas|lxml|requests|fastapi|uvicorn|pydantic` —— **零命中**。`model.py` 仅 import
   `json/os/sys/typing` + 内部模块。
3. vools 自身导入纯耗时 **~67 ms**，已是合理下限。

### 4.3 主因在环境（三项）
- **Windows Store Python UWP 别名 + 解释器启动 ~260 ms**（最大固定项；`python --version` 即 260–313ms）。
- **可编辑安装 finder 钩子**：`cypyc` 一个**与 actus 无关**的 editable 包，其 finder 每次启动白耗 **88 ms**；
  vools-actus 自身 editable finder 同理。
- **冷盘/导入缓存**：空闲后首跑 1–2.6 s，代码无法根治。

---

## 5. 可落地的降耗手段（环境级，非代码）

| 手段 | 做法 | 预期收益 | 风险 |
|---|---|---|---|
| **A（最大）** | hot CLI 路径改用「非 Store 标准 Python 3.13 直接 `python.exe`」，绕过 UWP 别名 | 基线约省 ~200 ms（→ 启动约 420–700ms） | 需另装 Python；改 PATH/别名 |
| **B** | vools-actus 以**非可编辑 wheel** 装入独立 venv 供日常 CLI（开发保留 editable） | 消除 cypyc 88ms + vools-actus 自身 finder | 双 venv 维护成本 |
| **C** | 保持解释器温态 / 避免空闲后首跑 | 消除 1–2.6s 冷首跑 | 仅缓解，不根治 |

---

## 6. 不建议的代码改动（护栏优先）

把 `model`/`core` 从 `__init__.py` 改为懒加载可省约 50ms，但爆破半径大：
全仓 `from vools.actus import Action, parse_cfg, parse_cfg_from_file` 等多处依赖顶层可用，
改动需同步全仓导入点，**风险 > 收益**，按「护栏优先」原则不做。

---

## 7. 下一步（待用户拍板）

- 若采纳 **A**：我可协助在该 Python 下 `python -m vools.actus.cli` 验证启动数字，并给出 PATH/别名切换步骤。
- 若采纳 **B**：我可协助构建 wheel 并装入独立 venv。
- 默认建议：**代码侧维持现状（已最优）**，体感优化走环境手段 A/B。
