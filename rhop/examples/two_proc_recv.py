"""rhop 配置驱动交互示例 B2：双进程 B 端（接收端/执行端）

演示目标：B 端角色 RECV，handle_request() 完成
「取包 -> 解密验证 -> 执行动作 -> 加密回传」闭环，无需链路控制代码。

用法（先开 B 端再开 A 端，或 A 先投递、B 后处理均可）：
    python examples/two_proc_recv.py --poll   # 终端 1：B 端轮询处理
    python examples/two_proc_send.py --wait   # 终端 2：A 端投递并取回结果
"""
from __future__ import print_function

import argparse
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))       # rhop 目录 -> vools.rhop
sys.path.insert(1, os.path.join(_HERE, "..", ".."))  # 仓库根 -> vools.data

from vools.rhop.interact import handle_request  # noqa: E402

SHARE_DIR = os.path.join(_HERE, "_demo_share")
REQ = "req_two_proc.rhop"


def build_cfg():
    """B 端配置：RECV 角色 + shared path 介质（与 A 端共用写/读视图）。"""
    return {
        "name": "two-proc-B",
        "key": "demo-key-2026-1107",
        "role": "RECV",
        "shared": {"write": SHARE_DIR, "read": SHARE_DIR},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", action="store_true", help="轮询直到出现请求包")
    args = ap.parse_args()
    os.makedirs(SHARE_DIR, exist_ok=True)

    if args.poll:
        deadline = time.time() + 30
        while time.time() < deadline:
            if os.path.exists(os.path.join(SHARE_DIR, REQ)):
                break
            time.sleep(0.5)
        else:
            print("[B] 30 秒内未收到请求包（请确认 A 端已投递）")
            return

    # 一键处理：取包 -> 解密验证 -> 执行动作 -> 加密回传
    result = handle_request(build_cfg(), REQ)
    print("[B] 处理 ->", result)


if __name__ == "__main__":
    main()
