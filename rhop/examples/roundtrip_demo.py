"""rhop 配置驱动交互示例 A：单机闭环（roundtrip）

演示目标（对齐 analysis/rhop-PLAN.md 附录 C「配置驱动 A/B/C 三角交互」）：
    只提供一份配置（密钥 + 角色 + 介质）+ 指定动作，
    rhop.interact() 自动完成
        「选通道 -> 加密 -> 传输 -> 解密验证 -> 执行动作 -> 加密回传 -> 取回验证」
    全链路，无需编写任何链路控制代码。

拓扑：A[发送端] 与 B[接收端] 复用同一份介质（shared path），
B 端由同进程模拟（handle_request），适合单机验证与演示；
双进程形态见 two_proc_send.py / two_proc_recv.py。

运行：
    python examples/roundtrip_demo.py
"""
from __future__ import print_function

import os
import sys

# vools.rhop 包位于 rhop/vools/rhop，vools.data 位于仓库根 vools/，两者都要可导入
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))      # rhop 目录 -> vools.rhop
sys.path.insert(1, os.path.join(_HERE, "..", ".."))  # 仓库根 -> vools.data

from vools.rhop.interact import interact  # noqa: E402

SHARE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_demo_share")


def main():
    # ---- 一份配置：密钥 + 本端角色 + 介质（shared path 写/读视图）----
    cfg = {
        "name": "demo-roundtrip",
        "key": "demo-key-2026-1107",
        "role": "SEND",
        "shared": {"write": SHARE_DIR, "read": SHARE_DIR},
    }
    os.makedirs(SHARE_DIR, exist_ok=True)

    # 形态 1：execute —— 本端直接执行公开动作（jump.probe 探测目标可达性）
    # T0r2.2.1 语义：probe 如实反映真实可达性；本示例未配置 sftp.host，
    # 因此返回 status=error（Ω-gate 收纳「缺少 sftp.host 配置（视为不可达）」）。
    # 配置了可达 host 时此处为 status=ok。
    probe = interact(cfg, action="jump.probe", mode="execute")
    print("[execute] jump.probe ->", probe)
    assert probe["status"] == "error", "execute 模式应如实传播 probe 不可达错误"
    assert probe["omega_gate"]["action"] == "jump.probe"
    assert probe["omega_gate"]["data"]["reachable"] is False

    # 形态 2：roundtrip —— 一次双方交互：A 发包 -> B 取包解密执行 -> 加密回传 -> A 取回验证
    # 闭环本身 status=ok；action_result 为 B 端真实执行结果（无 host -> error 并回传）。
    result = interact(cfg, action="jump.probe", mode="roundtrip")
    print("[roundtrip] ->", result)
    assert result["status"] == "ok", "roundtrip 链路失败"
    assert result["action_result"]["status"] == "error", "B 端动作执行结果应如实回传（无 host 不可达）"
    assert result["action_result"]["omega_gate"]["data"]["reachable"] is False
    print("roundtrip 全链路通过：A -> B -> A，无链路控制代码（动作结果如实回传）")


if __name__ == "__main__":
    main()
