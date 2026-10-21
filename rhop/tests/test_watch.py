"""MVP 判据 4: 接收方用 vools-rx 触发器监控到新文件并成功解密验证。"""

import os
import subprocess
import sys
import threading
import time

import pytest

from vools.rhop.crypto import RhopCrypto
from vools.rhop.transport import LocalSharedPath
from vools.rhop.watch import RhopWatcher

KEY = "watch-key"

_WRITER_SCRIPT = r"""
import os, sys
sys.path[:0] = os.environ["RHOP_PYTHONPATH"].split(os.pathsep)
from vools.rhop.crypto import RhopCrypto

shared_root = sys.argv[1]
c = RhopCrypto.from_key("watch-key")
token = c.encrypt_json({"task": "triggered", "seq": 1})
with open(os.path.join(shared_root, "pkg.rhop"), "w", encoding="utf-8") as fh:
    fh.write(token)
print("WROTE")
"""


def _env():
    env = dict(os.environ)
    roots = [p for p in sys.path if p and "vools" in p.replace("\\", "/").lower()]
    env["RHOP_PYTHONPATH"] = os.pathsep.join(roots)
    return env


def test_watcher_triggers_on_new_file(tmp_path):
    shared_root = str(tmp_path / "shared")
    os.makedirs(shared_root, exist_ok=True)
    shared = LocalSharedPath(shared_root)
    crypto = RhopCrypto.from_key(KEY)

    got = {}
    done = threading.Event()

    def on_packet(filename, result):
        got["filename"] = filename
        got["ok"] = result.ok
        got["reason"] = result.reason
        got["payload"] = result.payload
        done.set()

    watcher = RhopWatcher(shared, crypto, on_packet=on_packet, backend="polling", interval=0.1)
    try:
        watcher.start()
        # 发送方（独立进程）写入 shared path
        proc = subprocess.run(
            [sys.executable, "-c", _WRITER_SCRIPT, shared_root],
            capture_output=True,
            text=True,
            env=_env(),
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "WROTE"

        # 等待触发器回调（vools-rx 事件驱动）
        assert done.wait(timeout=10), "watcher 未在超时内收到触发器事件"
        assert got["filename"] == "pkg.rhop"
        assert got["ok"] is True
        assert got["reason"] == "OK"
        assert got["payload"] == {"task": "triggered", "seq": 1}
    finally:
        watcher.stop()


def test_watcher_ignores_non_rhop_and_bad_token(tmp_path):
    shared_root = str(tmp_path / "shared")
    os.makedirs(shared_root, exist_ok=True)
    shared = LocalSharedPath(shared_root)
    crypto = RhopCrypto.from_key(KEY)

    events = []

    def on_packet(filename, result):
        events.append((filename, result.ok, result.reason))

    watcher = RhopWatcher(shared, crypto, on_packet=on_packet, backend="polling", interval=0.1)
    try:
        watcher.start()
        # 非目标文件：不触发回调
        with open(os.path.join(shared_root, "note.txt"), "w", encoding="utf-8") as fh:
            fh.write("plain text")
        # 目标后缀但密文无效：触发回调且验证失败
        with open(os.path.join(shared_root, "bad.rhop"), "w", encoding="utf-8") as fh:
            fh.write("not-a-real-token")
        deadline = time.time() + 8
        while len(events) < 1 and time.time() < deadline:
            time.sleep(0.2)
        assert any(fn == "bad.rhop" for fn, _, _ in events), "bad.rhop 应触发回调"
        bad = [e for e in events if e[0] == "bad.rhop"][0]
        assert bad[1] is False
        assert bad[2] in ("MALFORMED", "BAD_TOKEN", "NOT_JSON")
    finally:
        watcher.stop()
