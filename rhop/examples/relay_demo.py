"""rhop 配置驱动交互示例 C：三角拓扑 A->C->B 中转（relay）

演示目标（对齐 analysis/rhop-PLAN.md 附录 C「配置驱动 A/B/C 三角交互」）：
    A[发送端] 与 B[接收端] 不可直连时，C[中转]（临时自建 HTTP RelayServer）
    暂存/转交动作包。本示例同进程自建 C，A 经 C 投递 jump.probe 请求包，
    B 从 C 取包解密执行并加密回传，A 再从 C 取回验证。

拓扑：A(SEND) -> C(RELAY) -> B(RECV)，通道选择链「中转优先」命中 relay。
配置只多一项 "relay"（host/port/token），其余（密钥/角色/动作）与 roundtrip 一致；
本示例未配置 sftp.host，probe 在 B 端如实返回不可达 error 并回传（T0r2.2.1 语义）。

运行（零外部依赖，中转为本机自建）：
    python examples/relay_demo.py
"""
from __future__ import print_function

import os
import sys

# vools.rhop 包位于 rhop/vools/rhop，vools.data 位于仓库根 vools/，两者都要可导入
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))      # rhop 目录 -> vools.rhop
sys.path.insert(1, os.path.join(_HERE, "..", ".."))  # 仓库根 -> vools.data

from vools.rhop.interact import handle_request, interact  # noqa: E402
from vools.rhop.transport.relay import RelayServer  # noqa: E402
from vools.rhop.config import RhopConfig  # noqa: E402

TOKEN = "relay-demo-token"
REQ = "req_relay_probe.rhop"
RESP = "res_" + REQ


def main():
    # ---- C 端：自建中转（A/B 不可直连时的暂存/转交）----
    server = RelayServer(host="127.0.0.1", port=0, token=TOKEN, ttl=60).start()
    relay_cfg = {"host": server.host, "port": server.port, "token": TOKEN}
    try:
        # ---- A 端：SEND 角色 + relay 中转地址，interact(mode="request") 一键投递 ----
        cfg_a = {
            "name": "relay-demo-A",
            "key": "demo-key-2026-1107",
            "role": "SEND",
            "relay": relay_cfg,
        }
        sent = interact(cfg_a, action="jump.probe", mode="request",
                        request_filename=REQ)
        print("[A] 经 C 投递 ->", sent)
        assert sent["status"] == "ok", "A 投递失败"
        assert sent["transport"] == "relay", "通道选择链应命中中转"

        # ---- B 端：RECV 角色 + 同一中转地址，handle_request 取包执行回传 ----
        cfg_b = {
            "name": "relay-demo-B",
            "key": "demo-key-2026-1107",
            "role": "RECV",
            "relay": relay_cfg,
        }
        handled = handle_request(cfg_b, REQ)
        print("[B] 处理 ->", handled)
        assert handled["status"] == "ok", "B 处理闭环失败"
        assert handled["transport"] == "relay"
        assert handled["response_sent"] == "ok"

        # ---- A 端取回 B 加密回传并验证（仍走 C 中转）----
        sess_a = RhopConfig.from_dict(cfg_a).build_session(role="SEND")
        fetched = sess_a.recv_package(RESP)
        print("[A] 取回 ->", fetched)
        assert fetched["status"] == "ok", "A 取回失败"
        assert fetched["transport"] == "relay"
        payload = fetched["payload"]
        assert payload["action"] == "jump.probe"
        assert payload["action_result"]["status"] == "error"  # 无 host -> 如实不可达
        assert payload["action_result"]["omega_gate"]["data"]["reachable"] is False
        print("relay 三角拓扑全链路通过：A -> C -> B -> A，无链路控制代码")
    finally:
        server.stop()


if __name__ == "__main__":
    main()
