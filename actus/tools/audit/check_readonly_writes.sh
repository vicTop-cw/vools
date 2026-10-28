#!/bin/bash
# 审计：只读命令是否写仓库/写 _meta。用标记文件 + find -newer 比对。
set -u
cd "$(dirname "$0")/../.." || exit 1
ROOT=$(pwd)
MARK=$(mktemp)
sleep 1
run() {
  local label="$1"; shift
  touch "$MARK"
  "$@" >/dev/null 2>&1
  local rc=$?
  local changed
  changed=$(find "$ROOT" -type f -newer "$MARK" 2>/dev/null \
    | grep -v '/\.git/' | grep -v '/tools/audit/' | grep -v '__pycache__' | grep -v '\.pyc$')
  if [ -z "$changed" ]; then
    printf '%-22s rc=%s  写入: (无)\n' "$label" "$rc"
  else
    printf '%-22s rc=%s  写入:\n' "$label" "$rc"
    echo "$changed" | sed 's/^/      /' | head -8
  fi
}
PY="python -m vools.actus.cli"
run "list"        $PY list
run "info"        $PY info actus.test.foo
run "status"      $PY status
run "events"      $PY events
run "records list" $PY records list
run "health"      $PY health
run "validate"    $PY validate
run "search"      $PY search foo
run "deps"        $PY deps actus.test.foo
run "dep-tree"    $PY dep-tree actus.test.foo
run "runtimes"    $PY runtimes
run "viz"         $PY viz
run "probe"       $PY probe
rm -f "$MARK"
