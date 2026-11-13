# R116 — 整段连续全量门禁 4 个既有 F 收口报告

> 生成：2026-11-13（统帅轮 23 时）｜用户拍板选项 **1**｜基线 commit `f6e8fee`
> 基线（R115 实测）：整段连续 `pytest tests/` → 6006 用例 / 5997 passed / 5 skipped /
> **4 failed** / RC=1 / 29m03s / 无 SIGTERM。
> 本轮目标：**4 个 F 全部转绿、RC=0、用例数 6006 不漂移、零 SIGTERM、零产品代码改动**。

---

## 1. 护栏（先立后动）

| # | 约束 | 判红条件 | 实测 |
|---|---|---|---|
| G1 | **绝不改动真实 `~/.actus/keys/*`** | 任何写操作 | ✅ mtime 保持 21:19:10，未写 |
| G2 | **绝不改写 4 个种子动作及其 `.sig`** | `git status actions/` 有输出 | ✅ clean |
| G3 | 不改系统 PATH / 不装系统级 Python | 系统级变更 | ✅ 无 |
| G4 | 仅改本批次变更文件，禁止整仓格式化 | 范围 diff | ✅ 2 文件 / +53 −22 |
| G5 | 状态声明 = 实测 | 数字与实测不符 | ✅ 门禁表见第 5 节 |
| G6 | 用例数单一真值 **6006** | 收集数漂移 | ✅ 见第 5 节 |

---

## 2. F 组 ①：种子签名 3 例（R116-A）

### 2.1 现象

`tests/test_seed_signatures.py` 3 例在整段连续会话中报
`Signature verification failed`；隔离单跑即复现，且把 R115 守卫关掉
（`ACTUS_TEST_ALLOW_WSL=1`）同样复现 → 与 wsl guard 无关。

### 2.2 根因：HOME 轮换公钥遮蔽了包内置真源

`vools/actus/trust_model.py::KeyManager.load_public_key` 的加载优先级是
**「HOME 密钥目录优先 → 包内置 `keys/` 回退兜底」**：

```python
def load_public_key(self, name: str = "default") -> Optional[bytes]:
    """加载公钥（HOME 密钥目录优先，包内置 keys/ 回退兜底）。"""
    pub_path = os.path.join(self._keys_dir, f"{name}.pub")
    if not os.path.isfile(pub_path):
        bundled = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            self._BUNDLED_KEYS_DIRNAME, f"{name}.pub",
        )
        if os.path.isfile(bundled):
            pub_path = bundled
        else:
            return None
```

种子动作的 `.sig` 是为**干净 checkout / pip 安装（HOME 无 `~/.actus/keys`）**签发的
（统帅轮-02时 T0r4.1），真源是**包内置** `vools/actus/keys/default.pub`。

而 `tests/conftest.py::_pin_isolated_dirs` 原先把**真实 HOME 的 keys 整个复制**进会话 HOME：

```python
shutil.copytree(real_keys, str(target_keys))
```

真实 `~/.actus/keys/default.key|pub` 的 mtime = **2026-11-13 21:19:10**（密钥被轮换过），
比种子 `.sig` 的签发时间（11-07）新。于是会话 HOME 里出现了一枚**不匹配的新 default.pub**，
优先级更高，把包内置真源**遮蔽**，4 个种子动作全部验签失败。

**哈希取证**（本轮 `sha256sum`）：

| 文件 | sha256 | 验签 4 个种子动作 |
|---|---|---|
| 真实 `~/.actus/keys/default.pub` | `2b613384c394d839…` | **4/4 失败** |
| 包内置 `vools/actus/keys/default.pub` | `3435d6300e503b18…` | **4/4 `ok`** |

### 2.3 修法（仅 `tests/conftest.py`）

复制 keys 时排除 `default.*`，让 default 走包内置兜底；`test.*` 等仍复制供自签用例：

```python
shutil.copytree(
    real_keys, str(target_keys),
    ignore=shutil.ignore_patterns("default.key", "default.pub"),
)
```

- **零产品代码改动**、**零真实 HOME 写入**、**零种子动作 / `.sig` 改写**。
- 语义上是把会话 HOME 恢复成种子签名设计时的「干净 checkout」前提，
  而不是给测试开后门。

### 2.4 增量验证

```text
pytest tests/test_seed_signatures.py \
       tests/test_trust_model_contracts_r32.py \
       tests/test_trust_model_contracts_r96.py \
       tests/test_trust_model_keys_contracts_r32.py \
       tests/test_registry_contracts_r32.py \
       -q -p no:cacheprovider -p no:warnings --tb=line
........................................................................ [ 80%]
.................                                                        [100%]
RC=0     # 89 用例全绿
```

---

## 3. F 组 ②：`test_action_path_of`（R116-B）

### 3.1 现象

`tests/test_validate_contracts_r32.py::test_action_path_of` 断言

```python
assert V.action_path_of({"path": "actions/a.actus.md"}) == "actions/a.actus.md"
```

整段连续会话实测返回 `E:\IDEProjects\AI\vools\actus\actions/a.actus.md`
（被拼上了 repo root）；**隔离单跑通过** → 典型连续会话 state 泄漏。

### 3.2 根因：`_apply_env_injections` 裸写 `ACTUS_REPO_ROOT` 未还原

`vools/actus/validate.py::action_path_of` 依赖环境变量：

```python
def action_path_of(meta: Dict) -> str:
    abs_path = meta.get('_path') or meta.get('_abs_path') or meta.get('path') or ''
    if abs_path and not os.path.isabs(abs_path):
        env = os.environ.get('ACTUS_REPO_ROOT')
        if env:
            abs_path = os.path.join(env, abs_path)
    return abs_path
```

`vools/actus/executor.py::_apply_env_injections` 会**直接裸写** `os.environ`：

```python
os.environ[f'{prefix}REPO_ROOT'] = _repo_root()
os.environ[f'{prefix}META_DIR'] = meta_dir or _paths_meta_dir()
```

`monkeypatch` 追踪不到产品代码在用例内后设的键，因此 teardown 不会还原。
`tests/test_executor_contracts_r69.py` 原先只在部分用例里对 5 个 `ACTUS_*` 键做
**裸 `os.environ.pop`**，而抛异常的路径「先注入再抛」根本没有清理。

**运行期探针实锤**（autouse fixture 记录每个用例前后 `ACTUS_REPO_ROOT`）：

```text
LEAK tests/test_executor_contracts_r69.py::TestEnv::test_apply_env_vault_conflict
     : None -> 'E:\\IDEProjects\\AI\\vools\\actus'
```

裸 `pop` 还有第二个危害：会把 conftest session 钉死的 `ACTUS_META_DIR` /
`ACTUS_VAULT2_DIR` 一并删掉，破坏后续用例的隔离前提。

### 3.3 修法（仅 `tests/test_executor_contracts_r69.py`）

4 个调用 `_apply_env_injections` 的用例统一改用**产品既有手势**，
与 `executor._build_child_env` 一致：

```python
def _env_restore(snap: dict) -> None:
    """把进程环境逐字回写到快照那一刻（先删新增，再复原改动/缺失）。"""
    for key in [k for k in os.environ if k not in snap]:
        del os.environ[key]
    for key, value in snap.items():
        if os.environ.get(key) != value:
            os.environ[key] = value
```

```python
snap = ex._env_snapshot()
try:
    with pytest.raises(ActionError) as ei:
        ex._apply_env_injections(a, {}, 'e-2', str(tmp_path),
                                 sandboxed=False, meta_dir=None)
    assert ei.value.code == 'vault_secret_conflict'
finally:
    ex._env_restore(snap)
```

`try/finally` 保证**抛异常路径同样还原**；`_env_restore` 逐字回写，
既不残留新增键、也不误删 session 钉死的键。第 5 个用例
`test_apply_env_sandboxed_build_dir` 本就用 snapshot，保持原样。

### 3.4 增量验证

```text
=== r69 env group isolated ===
........................................................................ [ 98%]
.                                                                        [100%]
RC=0

=== minimal reproducing combo (r69 + test_validate_contracts_r32.py) + leak probe ===
........................................................................ [ 63%]
.........................................                                [100%]
RC=0
=== leaks ===
NONE (clean)
```

---

## 4. 范围与兼容性

- **改动面**：`tests/conftest.py`（+19 −2 含注释）、
  `tests/test_executor_contracts_r69.py`（+37 −20）→ 合计 **2 文件 / +53 −22**，
  全部在 `tests/` 内，**零产品代码、零种子动作、零密钥写入**。
- **语法**：`python -m py_compile tests/conftest.py tests/test_executor_contracts_r69.py` → EXIT=0。
- **R115 守卫未受影响**：`ACTUS_TEST_ALLOW_WSL=1` 解除开关、`subprocess.Popen` 包覆逻辑原样保留。
- **公开覆盖口径不受影响**：本轮未增删/改名任何公开函数，R113 终态
  「493 个公开顶层函数、零测试引用 = 0」仍成立。
- **门禁口径**：必须用 **WindowsApps Python 3.13.14 / pytest 9.0.2**；
  `aider-venv` 缺 `cryptography`/`uvicorn`/`paramiko`/`keyring`，跑全量会产生成片假 F。

---

## 5. R116-C 整段连续全量门禁（实测）

### 5.1 命令与环境

```bash
cd /e/IDEProjects/AI/vools/actus
/c/Users/victo/AppData/Local/Microsoft/WindowsApps/python.exe \
  -m pytest tests/ -q -p no:cacheprovider -p no:warnings --tb=line
```

```text
C:\Users\victo\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe
3.13.14 (tags/v3.13.14:fd17997, Jun 10 2026, 13:03:48) [MSC v64 bit (AMD64)]
pytest 9.0.2
GATE_RC=0
```

### 5.2 门禁表

| 项 | R115 基线 | **R116-C 实测** | 判定 |
|---|---|---|---|
| 整段连续 `pytest tests/` | 跑到 100%、29m03s、无 SIGTERM | **跑到 100%、27m32s、无 SIGTERM** | ✅ |
| 收集用例数 | 6006 | **6006**（213 文件求和） | ✅ G6 无漂移 |
| 进度标记 | — | **`.` 5969 / `s` 37 / `F` 0 / `E` 0 = 6006** | ✅ 与收集数吻合 |
| passed | 5997 | **5969** | 见 §5.4 对账 |
| skipped | 5 | **37** | ⚠ 见 §5.4 |
| failed | **4** | **0** | ✅ **目标达成** |
| **RC** | **1** | **0** | ✅ **目标达成** |
| 原 4 个 F 显式复跑 | — | `.....` **5/5 通过，RC=0** | ✅ |
| `py_compile`（仅变更文件） | — | EXIT=0 | ✅ G4 |
| 仓库污染 | 无 | `git status actions/ vools/actus/keys/` **clean** | ✅ G2 |
| 真实 HOME 密钥 | 未写 | mtime 仍 **21:19:10**，未写 | ✅ G1 |

> **计数口径说明（重要）**：`pyproject.toml:160` 的 `addopts = "--tb=short -q"` 与命令行
> `-q` 叠加为 `-qq`，pytest 9 在 `-qq` 下**不打印末尾 `N passed ...` 汇总行**
> （已用单文件对照 `-q` / `-qq` 复验）。故本表计数由两条独立证据交叉核对：
> ① `pytest tests/ --collect-only -q` 输出 213 个文件的用例数求和 = **6006**；
> ② 本次运行进度流逐字符统计 = **5969 `.` + 37 `s` + 0 `F`/`E` = 6006**，且 RC=0。
> 日志末尾另有一行 `[safe-delete][SAFE_DELETE_FAIL_CLOSED]`（pytest 临时目录回收告警），
> 非测试失败，RC=0 已确认。**后续门禁建议加 `-o addopts=""` 或 `-ra` 以显式打印汇总行。**

### 5.3 4 个既有 F 全部转绿

```text
pytest tests/test_seed_signatures.py \
       tests/test_validate_contracts_r32.py::test_action_path_of \
       -q -p no:cacheprovider -p no:warnings --tb=line -rs
.....                                                                    [100%]
RC=0
```

整段连续会话中同样零 `F` 标记 → R116-A（3 例种子签名）与 R116-B（`test_action_path_of`）
在**整段连续**这一唯一曾失败的形态下均已收口，不只是隔离单跑通过。

### 5.4 skipped 5 → 37 的漂移归因（如实披露，不美化）

**不是新增失败、也不是用例丢失**，而是 32 个 GUI 契约用例在本轮被环境守卫跳过：

- 进度流 87% 处出现 **32 连 `s`**；收集序位 5197→5229（86.5%–87.0%）
  精确对应 `tests/test_tkdialog_gui_contracts_r77.py`（**恰好 32 用例**）。
- 该文件模块级守卫（统帅轮-09时）先真建一次 `tk.Tk()` 探测 Tcl/Tk 运行库，
  失败则 `pytestmark = skipif(...)` 整文件跳过，避免 32 个 ERROR。
  本轮 Tcl 库不可用（日志曾出现 `Can't find a usable init.tcl` /
  `C:/Program Files/WindowsApps/.../tcl/tk8.6/tk.tcl` 路径错误）→ 32 skip。
- **与本轮改动无因果关系**：`tests/conftest.py`、`tests/test_executor_contracts_r69.py`
  及其本轮 diff 中 `tcl|tk|display` **零命中**；conftest 的 HOME 钉死逻辑未改；
  GUI 守卫发生在收集期（模块 import），早于任何用例执行。
- **环境依赖性实测**：隔离跑该文件一次在沙箱下复现 Tcl 错误，另一次在 Tcl 可用环境下
  `................................ [100%] RC=0`（32 用例全过）。属 R113 已记载的
  「tkdialog GUI 回调 Tcl 环境 skip」同族现象，非 R116 引入。
- **数量对账**：`5997 passed + 4 修复转绿 − 32 GUI skip = 5969 passed`，
  `5 skipped + 32 = 37 skipped`，`4 failed → 0`，总数恒为 **6006**。零用例丢失。

> 严格口径下须注明：**本轮 GUI 契约用例未实际执行**（32 skip）。如需复核该族契约，
> 在 Tcl 可用环境单独跑 `tests/test_tkdialog_gui_contracts_r77.py` 即可（已验 RC=0）。

---

## 6. 结论

- **R116 目标完全达成**：整段连续 `pytest tests/` **RC=0**、**0 failed**、**6006 用例不漂移**、
  **无 SIGTERM**，4 个既有 F 全部消失，且**零产品代码改动**、零密钥/种子动作写入。
- 与 R115 的关系：R115 解决「**跑得完**」（不再 SIGTERM），R116 解决「**跑得绿**」（不再 RC=1）。
  至此沙箱内的整段连续全量门禁可单次、无拆分、无隔离批次地作为唯一权威门禁使用。
- 唯一残留是**环境级**：`tkdialog` 32 个 GUI 用例的 Tcl 可用性随沙箱波动，
  以及 `-qq` 吞掉汇总行。二者都不影响 RC=0 结论，但已在报告中如实标注，
  不作为「全绿无保留」宣称。

---

## 7. 交付物清单

| 文件 | 性质 |
|---|---|
| `tests/conftest.py` | R116-A 修法（keys 复制排除 `default.*`） |
| `tests/test_executor_contracts_r69.py` | R116-B 修法（env snapshot/restore） |
| `analysis/R116_CONTIGUOUS_GATE_FIX.md` | 本报告 |
| `analysis/R114_ENV_OPT_MEASUREMENT.md` | 同轮 R114-B 环境 A/B 量化报告 |
| `CHANGELOG.md` [Unreleased] 23时 条目 | 变更记录 |
| `.workbuddy/memory/2026-11-13.md` | 工作台日志 |
