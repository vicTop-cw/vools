"""Step 4 判据：配置驱动一键交互入口（config.py + interact.py）。

判据：一份配置（JSON/dict）描述密钥/角色/介质/动作集；
interact() 仅配置+动作名完成交互；handle_request 接收侧闭环回传。
"""

import json

import pytest

from vools.rhop import interact as interact_mod
from vools.rhop.interact import handle_request, interact
from vools.rhop.actions import run_action
from vools.rhop.config import RhopConfig, load_config
from vools.rhop.session import Role

KEY = "interact-key"
SHARED_WRITE = "interact-share"


def _shared_cfg(tmp_path):
    return {"write": str(tmp_path / SHARED_WRITE)}


def _base_cfg(tmp_path, role=Role.SEND, **extra):
    cfg = {
        "name": "test-cfg",
        "key": KEY,
        "role": role,
        "shared": _shared_cfg(tmp_path),
    }
    cfg.update(extra)
    return cfg


class TestRhopConfig:
    def test_from_dict_and_file(self, tmp_path):
        cfg = _base_cfg(tmp_path)
        c = RhopConfig.from_dict(cfg)
        assert c.name == "test-cfg"
        assert c.role == Role.SEND
        assert c.build_crypto() is not None

        path = tmp_path / "rhop.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        c2 = load_config(str(path))
        assert c2.key == KEY
        assert c2.to_dict()["has_key"] is True
        assert "password" not in json.dumps(c2.to_dict())

    def test_missing_key_rejected(self):
        with pytest.raises(ValueError):
            RhopConfig.from_dict({"role": "SEND"})

    def test_invalid_role_rejected(self):
        with pytest.raises(ValueError):
            RhopConfig.from_dict({"key": "k", "role": "X"})

    def test_build_session_roles(self, tmp_path):
        c = RhopConfig.from_dict(_base_cfg(tmp_path))
        send = c.build_session()
        assert send.role == Role.SEND
        recv = c.build_session(role=Role.RECV)
        assert recv.role == Role.RECV

    def test_action_cfg_passthrough(self, tmp_path):
        c = RhopConfig.from_dict(_base_cfg(tmp_path, sftp={"host": "h", "user": "u"}))
        acfg = c.action_cfg()
        assert acfg["sftp"]["host"] == "h"
        assert acfg["has_key"] is True

    def test_to_dict_masks_all_credentials(self, tmp_path):
        """导出配置不打密钥，并打码 sftp / online 通道 / relay 的全部凭据字段。"""
        cfg = _base_cfg(
            tmp_path,
            sftp={"host": "h", "password": "pw-sftp", "key_path": "kp-sftp"},
            online=[
                {"kind": "sftp", "host": "h2", "password": "pw-online"},
                {"kind": "relay", "host": "127.0.0.1", "port": 9999, "token": "tok-online"},
            ],
            relay={"host": "127.0.0.1", "port": 0, "token": "tok-relay"},
        )
        c = RhopConfig.from_dict(cfg)
        dumped = json.dumps(c.to_dict(), ensure_ascii=False)
        for secret in ("pw-sftp", "kp-sftp", "pw-online", "tok-online", "tok-relay", KEY):
            assert secret not in dumped
        assert c.to_dict()["has_key"] is True


class TestInteractExecute:
    def test_execute_unknown_action(self, tmp_path):
        result = interact(_base_cfg(tmp_path), "jump.nope")
        assert result["status"] == "error"
        assert "omega_gate" in result
        assert "未知动作" in result["omega_gate"]["error"]

    def test_execute_missing_sftp_host(self, tmp_path):
        result = interact(_base_cfg(tmp_path), "jump.push",
                          {"local_path": "x", "remote_path": "/x"})
        assert result["status"] == "error"
        assert "host" in result.get("message", "") or "host" in str(result.get("omega_gate"))


class TestInteractRoundtrip:
    def test_judge_roundtrip_shared(self, tmp_path):
        """判据：仅配置+动作名完成一次交互闭环（A 发请求包 -> B 执行 -> 回传）。"""
        cfg = _base_cfg(tmp_path)
        result = interact(cfg, "jump.probe", {}, mode="roundtrip")
        # T0r2.2.1：本机配置无 host，probe 反映真实不可达 -> 对端执行结果为 error 并回传
        assert result["status"] == "ok"  # 闭环本身成功
        assert result["result"] == "error"
        assert result["action_result"]["status"] == "error"
        assert result["action_result"]["omega_gate"]["action"] == "jump.probe"
        assert result["action_result"]["omega_gate"]["data"]["reachable"] is False

    def test_execute_probe_unreachable_propagates_error(self, tmp_path):
        """T0r2.2.1 回归：execute 模式 probe 不可达，Ω-gate 错误向外传播。"""
        cfg = _base_cfg(tmp_path, sftp={"host": "127.0.0.1", "port": 1, "timeout": 2})
        result = interact(cfg, "jump.probe", {})
        assert result["status"] == "error"
        assert "omega_gate" in result
        assert result["omega_gate"]["action"] == "jump.probe"

    def test_judge_request_and_handle(self, tmp_path):
        """request + handle_request：发送侧投递、接收侧解密执行并回传。"""
        cfg = _base_cfg(tmp_path)
        sent = interact(cfg, "jump.sync", {"local_path": "x", "remote_path": "/x"},
                        mode="request")
        assert sent["status"] == "ok"
        assert sent["transport"] == "shared"
        filename = sent["filename"]

        # 接收侧（对端进程/机器）处理
        recv_cfg = _base_cfg(tmp_path, role=Role.RECV)
        handled = handle_request(recv_cfg, filename)
        assert handled["status"] == "ok"
        assert handled["action"] == "jump.sync"
        # sync 缺 host -> 内层 error，omega_unwrap 判失败但回传流程完整
        assert handled["result"]["status"] == "error"
        assert handled["response_sent"] == "ok"

        # 发送侧取回响应
        sender = RhopConfig.from_dict(_base_cfg(tmp_path)).build_session(role=Role.SEND)
        fetched = sender.recv_package("res_" + filename)
        assert fetched["status"] == "ok"
        assert fetched["payload"]["action"] == "jump.sync"
        assert fetched["payload"]["result"] == "error"

    def test_handle_request_missing_action(self, tmp_path):
        cfg = _base_cfg(tmp_path, role=Role.RECV)
        sender = RhopConfig.from_dict(_base_cfg(tmp_path)).build_session(role=Role.SEND)
        sender.send_package("req_bad.rhop", {"payload": {}})
        handled = handle_request(cfg, "req_bad.rhop")
        assert handled["status"] == "error"
        assert "action" in handled["reason"]

    def test_roundtrip_payload_result(self, tmp_path):
        """roundtrip 后本端拿到对端执行的真实结果（含 files_transferred 等细节）。"""
        cfg = _base_cfg(tmp_path)
        result = interact(cfg, "jump.probe", {}, mode="roundtrip")
        ar = result["action_result"]
        assert ar["status"] == "error"  # T0r2.2.1：无 host -> 真实不可达
        assert "reachable" in ar["omega_gate"]["data"]


class TestHandleRequestDirect:
    def test_direct_run_action_consistency(self, tmp_path):
        """handle_request 的结果与直接 run_action 的 Ω-gate 解包语义一致。"""
        cfg = _base_cfg(tmp_path)
        cfg_obj = RhopConfig.from_dict(cfg)
        direct = run_action("jump.probe", cfg_obj.action_cfg(), {})
        assert direct["status"] == "ok"
        assert direct["data"]["status"] == "error"  # T0r2.2.1：无 host -> 真实不可达
