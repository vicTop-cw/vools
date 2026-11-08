"""T0r2.3.2 示例打磨：rhop/examples/ 子进程 smoke + 交互入口四动作覆盖。

判据（r1-doc-as-impl）：examples 下的交互示例必须可真实运行（子进程 smoke），
且交互入口层覆盖四个公开动作 jump.probe / jump.push / jump.pull / jump.sync。

覆盖示例：
- roundtrip_demo.py   单机闭环（execute + roundtrip 两形态）
- two_proc_send.py / two_proc_recv.py   双进程 A 投递 -> B 处理 -> A 取回
- relay_demo.py       三角拓扑 A(SEND) -> C(RELAY) -> B(RECV) -> A 中转闭环
"""

import os
import subprocess
import sys

import pytest

from vools.rhop.interact import interact

RHOP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES_DIR = os.path.join(RHOP_DIR, "examples")
SHARE_DIR = os.path.join(EXAMPLES_DIR, "_demo_share")

KEY = "smoke-key"
SHARE_WRITE = "smoke-share"


def _run_example(name, *args, timeout=60):
    """在 rhop 目录下以子进程运行 examples/<name>，返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, os.path.join(EXAMPLES_DIR, name), *args],
        cwd=RHOP_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _clean_share(*names):
    """清理示例共享目录中的运行产物（req/res 包），避免残留干扰。"""
    for n in names:
        p = os.path.join(SHARE_DIR, n)
        if os.path.exists(p):
            os.remove(p)


class TestExamplesSmoke:
    def test_roundtrip_demo_smoke(self):
        """roundtrip_demo.py 可真实运行：execute + roundtrip 全链路通过。"""
        proc = _run_example("roundtrip_demo.py")
        assert proc.returncode == 0, proc.stderr
        assert "roundtrip 全链路通过" in proc.stdout
        assert "[execute] jump.probe" in proc.stdout
        assert "[roundtrip]" in proc.stdout

    def test_two_proc_demo_smoke(self):
        """双进程示例三步串行：A 投递 -> B 处理回传 -> A 取回，均真实运行。"""
        _clean_share("req_two_proc.rhop", "res_req_two_proc.rhop")
        try:
            sent = _run_example("two_proc_send.py")
            assert sent.returncode == 0, sent.stderr
            assert "[A] 投递" in sent.stdout

            handled = _run_example("two_proc_recv.py")
            assert handled.returncode == 0, handled.stderr
            assert "[B] 处理" in handled.stdout

            fetched = _run_example("two_proc_send.py", "--wait")
            assert fetched.returncode == 0, fetched.stderr
            assert "[A] 取回" in fetched.stdout
        finally:
            _clean_share("req_two_proc.rhop", "res_req_two_proc.rhop")

    def test_relay_demo_smoke(self):
        """relay_demo.py 可真实运行：三角拓扑 A->C->B->A 中转闭环。"""
        proc = _run_example("relay_demo.py")
        assert proc.returncode == 0, proc.stderr
        assert "relay 三角拓扑全链路通过" in proc.stdout
        assert "[A] 经 C 投递" in proc.stdout
        assert "[B] 处理" in proc.stdout
        assert "[A] 取回" in proc.stdout


def _smoke_cfg(tmp_path):
    return {
        "name": "smoke-cfg",
        "key": KEY,
        "role": "SEND",
        "shared": {"write": str(tmp_path / SHARE_WRITE)},
    }


class TestFourActionsViaInteract:
    """交互入口层四个公开动作均可调用，Ω-gate 结构完备（补齐 jump.pull 入口覆盖）。"""

    @pytest.mark.parametrize("action", ["jump.probe", "jump.push", "jump.pull", "jump.sync"])
    def test_execute_mode_returns_structured_result(self, tmp_path, action):
        result = interact(_smoke_cfg(tmp_path), action, {})
        assert isinstance(result, dict)
        assert "status" in result
        # 无 sftp.host 的本地配置下，probe 如实不可达、其余动作缺参数被收纳为 error
        assert result["status"] == "error"
        assert result["omega_gate"]["action"] == action
        assert "error" in result["omega_gate"]

    def test_roundtrip_probe_result_structure(self, tmp_path):
        """roundtrip 模式返回结构含 transport/result/action_result（示例文档口径）。"""
        result = interact(_smoke_cfg(tmp_path), "jump.probe", {}, mode="roundtrip")
        assert result["status"] == "ok"
        assert result["transport"] == "shared"
        assert result["result"] == "error"
        assert result["action_result"]["status"] == "error"
        assert result["action_result"]["omega_gate"]["data"]["reachable"] is False
