"""rhop 配置驱动交互示例 B1：双进程 A 端（发送端）

演示目标：两个独立进程、各自持一份配置（同一份密钥 + 同一介质），
A 端只调 interact(mode="request") 投递动作包，链路控制全部由 rhop 完成。

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

from vools.rhop.config import RhopConfig  # noqa: E402
from vools.rhop.interact import interact  # noqa: E402

SHARE_DIR = os.path.join(_HERE, "_demo_share")
REQ = "req_two_proc.rhop"
RESP = "res_" + REQ


def build_cfg():
    """A 端配置：SEND 角色 + shared path 介质（与 B 端共用写/读视图）。"""
    return {
        "name": "two-proc-A",
        "key": "demo-key-2026-1107",
        "role": "SEND",
        "shared": {"write": SHARE_DIR, "read": SHARE_DIR},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", action="store_true", help="投递后轮询取回 B 端处理结果")
    args = ap.parse_args()
    os.makedirs(SHARE_DIR, exist_ok=True)

    # 一键投递：选通道 -> 加密 -> 传输，无需链路控制代码
    sent = interact(build_cfg(), action="jump.probe", mode="request",
                    request_filename=REQ)
    print("[A] 投递 ->", sent)
    if not args.wait:
        return

    # 取回 B 端加密回传并解密验证（B 端 handle_request 已回传 res_<包名>）
    sess = RhopConfig.from_dict(build_cfg()).build_session(role="SEND")
    deadline = time.time() + 30
    while time.time() < deadline:
        if os.path.exists(os.path.join(SHARE_DIR, RESP)):
            got = sess.recv_package(RESP)
            if got["status"] == "ok":
                print("[A] 取回 ->", got)
                return
            print("[A] 解密失败:", got.get("reason"))
            return
        time.sleep(0.5)
    print("[A] 30 秒内未取回 B 端结果（请确认 B 端已运行）")


if __name__ == "__main__":
    main()
