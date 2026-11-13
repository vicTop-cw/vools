# R114-B — 环境级启动优化对照实验（A/B 量化）

> 生成：2026-11-13（统帅轮 23 时）｜用户拍板选项 **2**｜基线报告：`analysis/R114_CLI_STARTUP_DIAGNOSIS.md`
> **结论先行**：手段 **A（绕过 UWP 别名、直接用真实 `python3.13.exe`）有稳定但有限的收益**
> （`--help` 769 → 692 ms，**-77 ms / -10%**；解释器基线 437 → 353 ms，**-84 ms / -19%**）。
> 手段 **B（非 editable wheel + 独立 venv）在本机实测没有收益，反而略慢**（`--help` 692 → 711 ms，
> import 657 → 710 ms）。**R114 对 B 的 ~88 ms 预期收益被证伪**。
> 真正的大头是解释器启动 + `site` + 标准库导入，三者环境下「CLI 层增量」几乎恒为 **~330 ms**。

---

## 1. 护栏（G1–G6 中本实验相关项）

| # | 约束 | 本实验状态 |
|---|---|---|
| G3 | **绝不改用户系统 PATH / 不安装系统级 Python** | ✅ 未改；量化仅用系统 Temp 下的临时 venv |
| G5 | 状态声明 = 实测，不美化 | ✅ 含一组**被污染作废**的数据与**证伪结论**，如实记录 |
| 代码侧 | 零产品代码改动 | ✅ 本轮唯一代码改动在 `tests/`，与启动路径无关 |

> E2 的全部产物位于 `%TEMP%\r114_wheel\` 与 `%TEMP%\r114_venv\`，不接触用户主环境、不写入仓库。

---

## 2. 三组对照环境

| 组 | 解释器 | 安装形态 | 验证目标 |
|---|---|---|---|
| **E0**（基线） | `C:\Users\victo\AppData\Local\Microsoft\WindowsApps\python.exe`（UWP 应用执行别名） | 可编辑安装（源码 `E:/IDEProjects/AI/vools/actus`） | 复现用户真实体感 |
| **E1** | `C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.3824.0_x64__qbz5n2kfra8p0\python3.13.exe`（真实 exe，**绕过别名**） | 可编辑安装（同 E0） | 手段 **A** 的净收益 |
| **E2** | `%TEMP%\r114_venv\Scripts\python.exe` | **非 editable wheel** 安装 | 手段 **B** 的净收益（消除 finder 钩子） |

**E2 构建与核验**：

```bash
python -m pip wheel --no-deps --no-build-isolation -w "$WHEEL_OUT" .
python -m venv "$VENV"
"$VENV/Scripts/python.exe" -m pip install --no-deps "$WHEEL"
```

- wheel：`vools_actus-0.9.1-py3-none-any.whl`，837,506 bytes，23:04 由**当前源码**现构。
- wheel 只含 `vools/actus` 子包，缺 `vools.core` 等核心模块 → 从仓库根 `E:/IDEProjects/AI/vools/vools`
  复制非 `actus` / 非 `__pycache__` 的核心模块到 venv site-packages，使 `vools` 命名空间完整。
- `pyvenv.cfg`：`home = ...PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0`、
  `include-system-site-packages = false`、`version = 3.13.14`。
- site-packages 内 **无 `__editable__*` 目录、无 `.pth` 文件** → E0/E1 里 `cypyc` 与
  `vools-actus` 两个 editable finder 钩子在 E2 中**确实被消除**（B 的前提成立）。

**preflight（neutral cwd，确认三组导入源正确）**：

```text
WindowsApps -> E:\IDEProjects\AI\vools\actus\vools\actus\cli.py
Program     -> E:\IDEProjects\AI\vools\actus\vools\actus\cli.py
Scripts     -> C:\Users\victo\AppData\Local\Temp\r114_venv\Lib\site-packages\vools\actus\cli.py
```

---

## 3. 测量协议

- **口径**：进程墙钟时间（spawn → exit），非 `-c` 内部 `perf_counter`，含解释器启动。
- **取样**：每项 **7 次取中位数**；7 次原始值全部列出，不隐藏离群点。
- **空载**：测量时**无后台 pytest / 无并发重负载**。
  > 早先一组在后台跑嫌疑集合（`GLZKUg`）期间测得的数据出现 E1 反而更慢、
  > `actus.exe --help` 波动到 2021 ms，判定**不可用于结论、已整组作废**；本文数据为等待
  > 后台任务结束、CPU 空闲后重测的结果。
- **cwd**：统一 neutral cwd，排除仓库根目录 `sys.path[0]` 差异。

> ⚠️ **跨报告绝对值不可直接比较**：R114 的 `python --version` 260–313 ms 使用另一套计时夹具，
> 本文 437 ms 为进程墙钟口径。**只有本文同一夹具内的 A/B 差值有意义**。

---

## 4. 原始数据（单位 ms，7 次 + 中位数）

| 测量项 | 组 | median | raw（7 次） |
|---|---|---:|---|
| **1) `python --version`**（解释器基线） | E0 alias | **437** | 437 / 400 / **2889** / 808 / 390 / 409 / 532 |
| | E1 direct-exe | **353** | 339 / 351 / 353 / 345 / 382 / 400 / 415 |
| | E2 venv-wheel | **388** | 380 / 379 / 388 / 422 / 360 / 390 / 409 |
| **2) `import vools.actus.cli`**（进程墙钟） | E0 alias+editable | **670** | 730 / 648 / 648 / 670 / 708 / 656 / 706 |
| | E1 direct+editable | **657** | 645 / 734 / 767 / 657 / 635 / 657 / 639 |
| | E2 venv+wheel | **710** | 679 / 825 / 849 / 673 / 704 / 712 / 710 |
| **3) CLI `--help`**（进程墙钟） | E0 alias+editable | **769** | 755 / 813 / 794 / 1051 / 754 / 726 / 769 |
| | E1 direct+editable | **692** | 746 / 732 / 668 / 692 / 674 / 689 / 695 |
| | E2 venv+wheel | **711** | 719 / 711 / 734 / 721 / 694 / 702 / 685 |

> E0 基线首跑 2889 ms 为冷盘离群点；中位数对其稳健。E2 的 import 两项 825/849 ms
> 同属波动上沿，未剔除，如实保留。

---

## 5. 派生分析

### 5.1 手段 A（E0 → E1）：稳定但有限

| 项 | E0 | E1 | Δ | 幅度 |
|---|---:|---:|---:|---:|
| `python --version` | 437 | 353 | **-84 ms** | **-19.2%** |
| `import vools.actus.cli` | 670 | 657 | -13 ms | -1.9%（噪声内） |
| CLI `--help` | 769 | 692 | **-77 ms** | **-10.0%** |

→ 收益几乎全部落在**别名解析 / 进程启动**这一段；进入 Python 之后的 import 树基本不变。
→ 与 R114 判断一致：UWP 别名是环境侧最大**固定**项，但把它拿掉只省约 80 ms，
**不足以把 700 ms 级启动变成"快"**。

### 5.2 手段 B（E1 → E2）：证伪

| 项 | E1 | E2 | Δ | 判定 |
|---|---:|---:|---:|---|
| `python --version` | 353 | 388 | +35 ms | 略慢 |
| `import vools.actus.cli` | 657 | 710 | **+53 ms** | 变慢 |
| CLI `--help` | 692 | 711 | **+19 ms** | 变慢（噪声边缘） |

E2 **已经确实消除了** `__editable___cypyc_0_1_0_finder`（88 ms）与 vools-actus 自身 finder，
却仍比 E1 慢。可归因的反向成本：

1. venv 的 `python.exe` 启动需额外解析 `pyvenv.cfg`、切换 `sys.prefix`；
2. `include-system-site-packages = false` 下 `site` 初始化路径更长，且 wheel 安装后
   `vools` 包从 Temp 目录加载（与源码盘不同的缓存 locality）；
3. finder 的 88 ms 是 **`-X importtime` 累计值**（含它传递导入的子模块），
   并非可从墙钟里整额减掉的净成本。

→ **净效果 <= 0，且差值落在 7 次取样 ~60–200 ms 的波动带内**，
故严谨表述是「**B 无可测收益**」，而非「B 一定有害」。

### 5.3 关键不变量：CLI 层增量 ≈ 330 ms

用同组 `--help` 减去 `python --version` 近似 CLI 层（site 之后 + vools 导入 + argparse）：

| 组 | `--help` | `--version` | 差值 |
|---|---:|---:|---:|
| E0 | 769 | 437 | **332 ms** |
| E1 | 692 | 353 | **339 ms** |
| E2 | 711 | 388 | **323 ms** |

三组的 CLI 层增量几乎相同（323–339 ms，组内噪声量级）。
→ **无论别名、editable、venv 怎么换，这 ~330 ms 都不动**；它才是启动主体，
且按 R114 §4.2 结论，代码侧已无可避免的重依赖可砍。

---

## 6. 对 R114 手段表的修订

| 手段 | R114 预期 | R114-B 实测 | 结论 |
|---|---|---|---|
| **A** 非 Store 直接 exe 绕过 UWP 别名 | 约省 ~200 ms | `--help` **-77 ms**、基线 **-84 ms** | ✅ 方向正确，**幅度需下修**（原估计偏乐观） |
| **B** 非 editable wheel + 独立 venv | 消除 88 ms finder | 无收益，中位数反慢 19–53 ms | ❌ **不建议为启动性能而做** |
| **C** 保持解释器温态 | 消除 1–2.6 s 冷首跑 | 本轮 7 次取样中 E0 首跑 2889 ms 再次佐证 | ✅ **仍是最大杠杆** |
| 代码侧改 `model`/`core` 懒加载 | 省 ~50 ms、爆破半径大 | 未做（R114 §6 已否决） | 维持否决 |

---

## 7. 建议（**仅建议，不代用户执行**；G3 不改动系统）

1. **只采纳 A，且用非侵入方式**：不改系统 PATH、不装新 Python。
   在用户自己的 shell 配置里给 `actus` 建一个指向**已有**真实 exe 的本地包装，例如
   PowerShell profile 中定义函数调用
   `& "C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.3824.0_x64__qbz5n2kfra8p0\python3.13.exe" -m vools.actus.cli @args`。
   收益约 80 ms，风险为零、可随时撤销。
2. **不要为启动速度引入第二套 venv / 非 editable 安装**：B 无收益且增加维护成本
   （wheel 只含 actus 子包，还需手工补齐 `vools` 核心模块，本次为实验临时拼接，非可用发行形态）。
3. **C 的收益远大于 A**：空闲后首跑 1–2.6 s 是 OS 磁盘/导入缓存现象；
   保持解释器温态（常驻轻量进程、或避免长时间空闲后首次调用）比换运行时更划算。
4. **代码侧维持现状**：R114 §4.2 已证明子命令懒加载到位、启动链零可避免重依赖；
   本轮再次确认 CLI 层 ~330 ms 与环境无关。为 ~50 ms 改 `model`/`core` 顶层导入不值得。
5. **「用 lz 换芯」仍不优先**：瓶颈是 CPython 解释器 + `site` + 标准库导入，
   不是业务逻辑计算；换语言只有在完全脱离 Python 栈时才可能带来数量级变化，
   代价是 6006 用例的契约体系全部重做。**当前不建议**。

---

## 8. 局限与清理

- 单机单 OS（Windows 11 / Windows Store Python 3.13.14）、单次 7 样本、墙钟口径；
  不同机器的磁盘缓存与 `sitecustomize` 差异会改变绝对值，**结论只对本机成立**。
- 三组的中位数来自**不同轮次**，`--help − --version` 的派生差值仅作量级参考，不作精确归因。
- 临时产物保留于 `%TEMP%\r114_wheel\`、`%TEMP%\r114_venv\`（系统 Temp，用户可随时删除）；
  仓库内**零新增运行时文件**，本实验不产生需要提交的代码。
