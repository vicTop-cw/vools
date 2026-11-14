#!/usr/bin/env bash
# actus_fast.sh — 绕开 UWP 别名、直接用 WindowsApps 真实 python3.13.exe 启动 actus CLI
#
# 背景（R114 / R114-B）：`actus` 控制台脚本回退到 PATH 上的 UWP 别名
#   `WindowsApps\python.exe`，其启动比同发行版的真实二进制 `python3.13.exe` 慢
#   ~77–84 ms（别名解析 + 进程启动开销，与业务计算无关；代码侧已最优）。
#   本包装直接用真实 exe，等价 `python -m vools.actus.cli`，体感更快。
#
# 用法（与 actus 完全一致）：
#   ./scripts/actus_fast.sh --help
#   ./scripts/actus_fast.sh list
#   ./scripts/actus_fast.sh run <id> --confirm
# 覆盖解释器：ACTUS_FAST_PY=/path/to/python3.13.exe ./scripts/actus_fast.sh ...
#
# 注意：必须用真实 exe（Program Files\WindowsApps\...\python3.13.exe），
#       不能用 WindowsApps\python.exe 别名，否则失去加速意义。
# 不改系统 PATH、不装系统 Python、不改任何产品代码（仅本地启动器）。

set -u

# 默认：WindowsApps 真实二进制（非 UWP 别名）。
DEFAULT_PY="/c/Program Files/WindowsApps/PythonSoftwareFoundation.Python.3.13_3.13.3824.0_x64__qbz5n2kfra8p0/python3.13.exe"
PY="${ACTUS_FAST_PY:-$DEFAULT_PY}"

exec "$PY" -m vools.actus.cli "$@"
