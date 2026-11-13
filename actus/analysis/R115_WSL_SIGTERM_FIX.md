# R115 — 修复 wsl 连续会话 SIGTERM 缺陷（诊断 + 修法 + 门禁）

> 生成：2026-11-13（统帅轮 22时）｜方法：源码调用点审计 + 进程实测 + 整段连续全量回归
> 结论先行：**整段连续 pytest 会话首次完整跑到 100%（29m03s，6006 用例），未再被 SIGTERM。**
> 但整段会话仍非全绿（4 个既有 F），已逐条归因，按范围纪律记录不改动。

---

## 1. 问题与根因精确化

沙箱对 `wsl.EXE` 设黑名单。整段连续 pytest 会话里，只要某个用例（或 state 泄漏）
**真实 spawn `wsl.exe`**，沙箱即 **SIGTERM 整个 pytest 进程**，门禁永远跑不完 ——
自 R110 起只能拆成 7 个隔离批次才能拿到绿。

真实 spawn 点：

- `vools/actus/probe/platform_tools.py::_probe_windows_wsl` → `_run([wsl.exe, "-l", "-v"])`
  → `subprocess.Popen(argv, ...)`（`platform_tools.py:138`）。
- `wsl` 在本机 `shutil.which('wsl') = C:\Windows\system32\wsl.EXE`（**文件存在**），
  所以 `_find_tool` 会命中并尝试执行 —— 正是黑名单触发条件。

**误归因纠正**：R110 记录把 `test_platform_enum_alignment.py` 列为触发源之一。
实测该文件是**纯 schema/枚举/校验逻辑，零 subprocess 调用**，只是在收集顺序上
恰好相邻；`test_language_entries.py` 的 `("bash","echo ok-bash")` 在本沙箱解析到
**Git Bash**（`...PortableGit\usr\bin\bash.EXE`），不是 WSL 网关，亦不触发 wsl.exe。
真凶是任何绕过打桩、真实跑到 `_probe_windows_wsl` 的路径。

---

## 2. 修法（仅测试侧，零产品代码改动）

`tests/conftest.py` 载入期把 `subprocess.Popen` 包一层：

```python
_ACTUS_ALLOW_WSL = os.environ.get("ACTUS_TEST_ALLOW_WSL") == "1"

if not _ACTUS_ALLOW_WSL and not getattr(_subprocess.Popen, "_actus_wsl_guard", False):
    _actus_orig_popen = _subprocess.Popen

    def _actus_guarded_popen(cmd, *args, **kwargs):
        exe = ...  # list/tuple 取 cmd[0]；str 取首 token
        if os.path.basename(exe).lower() in ("wsl", "wsl.exe"):
            raise FileNotFoundError("wsl.exe blocked by actus test guard ...")
        return _actus_orig_popen(cmd, *args, **kwargs)

    _actus_guarded_popen._actus_wsl_guard = True
    _subprocess.Popen = _actus_guarded_popen
```

**为什么抛 `FileNotFoundError`**：`platform_tools._run` 已捕获
`(FileNotFoundError, OSError, ValueError)` 并返回 `(None, b"")`，即产品代码既有的
「命令没跑起来 / WSL 不可用」优雅降级分支。守卫不改判定逻辑，只让该分支在沙箱内
**必然且快速**地发生，从而：

| 收益 | 说明 |
|---|---|
| 消除 SIGTERM | 沙箱内绝不真正 exec `wsl.exe` |
| 零产品代码改动 | 只在 pytest 进程生效，`actus` 运行时不受影响 |
| 语义真实 | 覆盖「WSL 不可用」路径 —— 正是沙箱 / 无 WSL 机的真实语义 |
| 可退出 | `ACTUS_TEST_ALLOW_WSL=1` 解除守卫，真机可跑 WSL 集成用例 |
| 爆破半径最小 | 仅拦 `wsl`/`wsl.exe`，`bash`/`cmd`/`python` 全部放行 |

---

## 3. 兼容性审计

| 审计项 | 结果 |
|---|---|
| 源码 subprocess 引入方式 | 8 处全部 `import subprocess`（模块属性访问），无 `from subprocess import Popen` → 模块级补丁全覆盖 |
| `subprocess.run` | 内部引用模块级 `Popen`，一并生效 |
| Popen 首参形式 | 8 处调用点全部**位置参数**，守卫签名 `(cmd, *args, **kwargs)` 兼容 |
| `shell=True` 字符串命令 | 首 token 检测覆盖直接以 `wsl` 开头；`bash -c '...'` 内嵌 wsl 属产品执行任意命令范畴，当前套件不涉及 |
| 测试内 monkeypatch | 20+ 处 `monkeypatch.setattr(subprocess, 'Popen', fake)` 在用例内覆盖守卫、teardown 自动恢复 —— 打桩用例不受影响 |
| CLI 子进程绕过风险 | `test_cli_surface` / `test_language_entries` / `test_kind_family_e2e` / `test_resolver_cli` 启动的子进程只测 `run`/`--version`/`--help`/参数错误，**无 `probe` 子命令**，不经 `_probe_windows_wsl` → 无绕过路径 |
| 幂等 | `_actus_wsl_guard` 标志位防重复包覆 |

---

## 4. 门禁实测（真实运行时：WindowsApps Python 3.13.14 / pytest 9.0.2）

| 项 | 结果 |
|---|---|
| **整段连续全量** `pytest tests/` | **6006 用例跑到 100% 完整结束，29m03s，无 SIGTERM** ✅ |
| 计数 | **5997 passed / 5 skipped / 4 failed**（RC=1，见 §5） |
| wsl/probe 12 文件连续批次 | RC=0 |
| R113 新增文件 | 6/6 RC=0 |
| 守卫单元验证 | `Popen(['wsl.exe','-l','-v'])` → `FileNotFoundError`；`_actus_wsl_guard=True` |
| 真实仓库污染 | `git status` 无 `actions/*.actus.md` / `_meta` 变更 ✅ |

> 对照：修复前整段连续会话会被 SIGTERM 杀死（R110 记录），只能拆 7 个隔离批次。
> 本轮为**首次整段连续跑完**。

---

## 5. 4 个 F 的归因（全部与守卫无关，按范围纪律记录、不改动）

| # | 用例 | 现象 | 归因 | 与守卫无关的证据 |
|---|---|---|---|---|
| 1-3 | `test_seed_signatures.py` ×3 | 4 个种子动作 `Signature verification failed` | 真实 `~/.actus/keys/default.key|pub` 于 **21:19 被轮换**，种子动作由旧公钥签发 | **隔离单跑即复现**；`ACTUS_TEST_ALLOW_WSL=1`（守卫关闭）**同样复现**；且该文件零 subprocess |
| 4 | `test_validate_contracts_r32.py::test_action_path_of` | `E:\...\actus\actions/a.actus.md` ≠ `actions/a.actus.md` | 连续会话 state 泄漏（cwd / `ACTUS_REPO_ROOT` 未还原），R110 注释记载的同族既有缺陷 | **隔离单跑通过、仅整段连续失败**；纯字符串断言，守卫只拦 `wsl.exe` 的 Popen |

> 这 4 个 F 此前被「整段会话必被 SIGTERM」掩盖，从未暴露。守卫让整段会话能跑完，
> 才首次把它们显形 —— 属**暴露既有缺陷**，非引入回归。

---

## 6. 口径纠正（重要，避免后续验收踩坑）

- **必须用 WindowsApps Python 3.13 跑门禁**（R110 基线口径）。该解释器具备
  `pytest / uvicorn / paramiko / keyring / cryptography / jsonschema / fastapi` 全套依赖。
- **`/e/Tools/aider-venv` 缺 `cryptography`/`uvicorn`/`paramiko`/`keyring`**，用它跑全量会
  产生成片假 F（实测 `test_kek_rotation_crash_matrix` 29 例全挂、
  `test_desktop_contracts_r65` 3 例 `No module named 'uvicorn'`、
  `test_jump_contracts_r58` 1 例 `No module named 'paramiko'`）。
  一次误用的 aider-venv 全量（14m20s、44%、含成片假 F）已终止作废。
- 该解释器差异也解释了 R114 中 `import vools.actus` 0.15s（aider-venv）
  vs 0.457s（WorkBuddy 内置 3.13.14）vs 真实运行时 67ms 子树的分歧。

---

## 7. 结论与下一步

**R115 目标达成**：整段连续门禁可在沙箱**跑通**（不再 SIGTERM，能完整跑完 6006 用例）。
**未达成**：整段连续会话**全绿** —— 4 个既有 F 已逐条归因，按范围纪律记录不改动，
不作虚假「全绿」声明。

下一步候选（待用户拍板）：

1. 收口 §5 的 4 个既有 F（重签种子动作 / 定位并隔离 state 泄漏前置用例），
   使整段连续会话达到 RC=0；
2. 保持范围纪律，4 个 F 仅记录，转入 R114 的环境级优化（A：非 Store Python；
   B：非可编辑 wheel）；
3. 二者都做。

---

## 附：本次涉及文件

- `tests/conftest.py` —— 新增 R115 守卫（唯一代码改动）
- `CHANGELOG.md` —— 22时 R115 条目 / 21时 R114 条目
- `analysis/R114_CLI_STARTUP_DIAGNOSIS.md` —— R114 诊断报告
- `analysis/R115_WSL_SIGTERM_FIX.md` —— 本报告
