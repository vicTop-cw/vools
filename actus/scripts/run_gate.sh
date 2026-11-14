#!/usr/bin/env bash
# run_gate.sh — vools-actus 整段连续全量门禁的规范入口（单一真值命令）
#
# 背景：pyproject.toml 的 addopts = "--tb=short -q" 与命令行 -q 叠加成 -qq，
#       导致 pytest 9 不打印末尾汇总行（RC 只能靠收集数 + 进度标记反推，易错）。
#       本脚本用 -o addopts="" 覆盖 addopts，恢复显式汇总行，并加 -ra 列出 skip 原因。
#
# 门禁口径（硬性要求）：
#   - 必须用 WindowsApps Store Python 3.13 真实运行时；aider-venv 缺 cryptography/
#     uvicorn/paramiko/keyring，跑全量会产生成片假 F。
#   - 零产品代码改动；零密钥/种子动作写入；状态声明 = 实测。
#
# 用法：
#   ./scripts/run_gate.sh                # 整段连续全量
#   ./scripts/run_gate.sh tests/foo.py   # 指定子集（其余参数透传 pytest）
#   ACTUS_GATE_PY=/path/to/python ./scripts/run_gate.sh
#
# 退出码：透传 pytest 的 RC（0 = 全绿，非 0 = 有失败/错误）。

set -u

# 默认解释器：WindowsApps Store Python（真实运行时）。
# 可经环境变量覆盖，避免在其它 venv 上跑出假 F。
DEFAULT_PY="/c/Users/victo/AppData/Local/Microsoft/WindowsApps/python.exe"
PY="${ACTUS_GATE_PY:-$DEFAULT_PY}"

# 仓库根 = 本脚本上一级目录（scripts/..）。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT" || { echo "无法切换到仓库根: $ROOT" >&2; exit 1; }

# -o addopts=""  覆盖 pyproject 的 --tb=short -q，恢复显式汇总行
# -p no:cacheprovider  避免 .pytest_cache 污染工作树
# -p no:warnings       屏蔽警告噪声（门禁看 passed/failed/skipped）
# --tb=line            失败仅打一行定位，保持日志紧凑
# -ra                  汇总 skipped/xfailed 原因，便于 37 skipped 逐项对账
"$PY" -m pytest tests/ \
  -o addopts="" \
  -p no:cacheprovider \
  -p no:warnings \
  --tb=line \
  -ra \
  "$@"
exit $?
