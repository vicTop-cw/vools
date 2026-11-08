"""vools.actus 剪贴板能力示例 B：监控（真实系统剪贴板事件流）。

演示目标（对齐 docs/DEVELOPMENT_STANDARDS.md r1-doc-as-impl）：
    只提供配置（interval / backend / filter_self / on_text）启动监控，
    clip_watch 自动完成 选后端 -> 启动 Dispatcher -> 事件分发 -> 可 stop 停止。

运行：
    python examples/clipboard_watch.py

说明：使用 polling 后端 + interval=0.05 提速演示；filter_self=False
使 clip_write 的写入也触发分发。脚本会对系统剪贴板做真实写入。
"""
from __future__ import print_function

import os
import queue
import sys
import time

# vools.actus 位于 actus/vools/actus，vools.reactive 位于 rx/vools/reactive，
# 两者都要可导入（命名空间包合并）。
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))             # actus 根 -> vools.actus
sys.path.insert(1, os.path.join(_HERE, "..", "..", "rx"))  # rx 根 -> vools.reactive

from vools.actus import clip_watch, clip_write  # noqa: E402

_MARK = "actus-example-watch-%d" % int(time.time())


def main():
    received = queue.Queue()

    # 动作：监控（构造即启动；filter_self=False 让 clip_write 写入也分发）
    w = clip_watch(
        interval=0.05,
        backend="polling",
        filter_self=False,
        on_text=lambda cd: received.put(cd),
    )
    try:
        # 排空 polling 首次分发可能带来的剪贴板残留
        time.sleep(0.2)
        while True:
            try:
                received.get_nowait()
            except queue.Empty:
                break

        # 动作：写（触发监控事件）
        clip_write(_MARK, tags=["actus", "example"])

        try:
            cd = received.get(timeout=3.0)
        except queue.Empty:
            w.stop()
            raise SystemExit("3 秒内未收到写入事件，监控链路失败")

        print("[watch]", cd.change_type.name, repr(cd.content))
        if cd.content != _MARK:
            raise SystemExit("watch 收到内容与写入不一致: %r != %r" % (cd.content, _MARK))
        print("CLIP_WATCH_OK")
    finally:
        w.stop()


if __name__ == "__main__":
    main()
