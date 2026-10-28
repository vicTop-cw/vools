"""clipboard 测试：后端探测 / push-pull 文件协议 / 守护退出。

剪贴板真机读写只做 win32 冒烟；协议测试全部注入假 backend，不依赖真机剪贴板。
"""

import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, r'E:\IDEProjects\AI\vools')
sys.path.insert(0, r'E:\IDEProjects\AI\vools\rhop')

from vools.rhop.clipboard import (
    CLIP_FILE,
    ClipboardFileSync,
    get_clipboard_backend,
    last_read_reason,
    read_clipboard,
    write_clipboard,
)


def _clipboard_usable(backend=None) -> bool:
    """真机剪贴板是否**确实**可用（探针写一次）。

    后端能探测到不等于能用：无交互桌面 / 剪贴板被其他进程占用时，
    PowerShell 的 Set-Clipboard 会抛 ExternalException，write 返回 False。
    这类是「机器不可用」而非「代码回归」——协议层已由假 backend 用例覆盖，
    真机冒烟在没有可用剪贴板时应跳过而不是把全量测试染红。
    """
    if backend is None:
        backend = get_clipboard_backend()
    if backend is None:
        return False
    try:
        return bool(backend[1]("rhop-clip-probe"))
    except Exception:
        return False


class FakeClip:
    """内存假剪贴板（测试注入）。"""

    def __init__(self, text=""):
        self.text = text

    def backend(self):
        return (lambda: self.text, lambda t: setattr(self, "text", t) or True)


class TestBackendDetection:
    def test_get_backend_returns_tuple_or_none(self):
        got = get_clipboard_backend()
        assert got is None or (callable(got[0]) and callable(got[1]))

    def test_read_clipboard_no_backend(self, monkeypatch):
        monkeypatch.setattr("vools.rhop.clipboard.get_clipboard_backend", lambda: None)
        assert read_clipboard() == ""
        assert "无可用" in last_read_reason()

    def test_write_clipboard_no_backend(self, monkeypatch):
        monkeypatch.setattr("vools.rhop.clipboard.get_clipboard_backend", lambda: None)
        assert write_clipboard("x") is False

    def test_real_clipboard_smoke(self):
        """真机冒烟：写→读回一致（后端缺失则跳过）。"""
        pair = get_clipboard_backend()
        if pair is None:
            pytest.skip("本机无可用剪贴板后端")
        if not _clipboard_usable(pair):
            pytest.skip("剪贴板存在但不可写（无交互桌面/被占用），真机冒烟跳过")
        marker = "rhop-clip-smoke-%d" % os.getpid()
        assert write_clipboard(marker) is True
        assert read_clipboard() == marker

    def test_powershell_backend_forced_roundtrip(self):
        """强制 PowerShell 后端（绕过 pyperclip）：写→读精确回环 + 尾部换行归一化。

        本机实测 Get-Clipboard -Raw 会附带尾部 \r\n，不归一化会把 \r\n 写进共享文件。
        """
        from vools.rhop.clipboard import _powershell_backend
        ps = _powershell_backend()
        if ps is None:
            pytest.skip("无 powershell.exe")
        if not _clipboard_usable(ps):
            pytest.skip("PowerShell 剪贴板不可写（无交互桌面/被占用），回环跳过")
        marker = "rhop-ps-regression-中文-\u00e9"
        assert write_clipboard(marker, backend=ps) is True
        assert read_clipboard(backend=ps) == marker  # 尾部 \r\n 已剥离


@pytest.fixture
def fake_clip():
    return FakeClip("")


class TestPushRole:
    def test_push_writes_file_on_change(self, tmp_path, fake_clip):
        fake_clip.text = "hello-local"
        fs = ClipboardFileSync(str(tmp_path), role="push", backend=fake_clip.backend())
        out = fs.sync_once()
        assert out["changed"] is True
        with open(str(tmp_path / CLIP_FILE), encoding="utf-8") as fh:
            body = json.load(fh)
        assert body["text"] == "hello-local"
        assert body["writer"] == "rhop"

    def test_push_no_change_skips(self, tmp_path, fake_clip):
        fake_clip.text = "same"
        fs = ClipboardFileSync(str(tmp_path), role="push", backend=fake_clip.backend())
        fs.sync_once()
        out2 = fs.sync_once()
        assert out2["changed"] is False
        assert "一致" in out2["reason"]

    def test_push_empty_clipboard_writes_empty(self, tmp_path, fake_clip):
        """空剪贴板也是合法内容（覆盖文件为空串）——显式语义而非跳过。"""
        fake_clip.text = "will-be-cleared"
        fs = ClipboardFileSync(str(tmp_path), role="push", backend=fake_clip.backend())
        fs.sync_once()
        fake_clip.text = ""
        out = fs.sync_once()
        assert out["changed"] is True
        with open(str(tmp_path / CLIP_FILE), encoding="utf-8") as fh:
            assert json.load(fh)["text"] == ""

    def test_invalid_role_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            ClipboardFileSync(str(tmp_path), role="both")


class TestPullRole:
    def test_pull_sets_clipboard_from_file(self, tmp_path, fake_clip):
        with open(str(tmp_path / CLIP_FILE), "w", encoding="utf-8") as fh:
            json.dump({"text": "from-p0", "updated_at": "t", "writer": "p0"}, fh)
        fs = ClipboardFileSync(str(tmp_path), role="pull", backend=fake_clip.backend())
        out = fs.sync_once()
        assert out["changed"] is True
        assert out["from_writer"] == "p0"
        assert fake_clip.text == "from-p0"

    def test_pull_no_file(self, tmp_path, fake_clip):
        fs = ClipboardFileSync(str(tmp_path), role="pull", backend=fake_clip.backend())
        out = fs.sync_once()
        assert out["changed"] is False
        assert "不存在" in out["reason"]

    def test_pull_idempotent(self, tmp_path, fake_clip):
        with open(str(tmp_path / CLIP_FILE), "w", encoding="utf-8") as fh:
            json.dump({"text": "same", "updated_at": "t", "writer": "p0"}, fh)
        fs = ClipboardFileSync(str(tmp_path), role="pull", backend=fake_clip.backend())
        fs.sync_once()
        out2 = fs.sync_once()
        assert out2["changed"] is False

    def test_pull_same_as_local_skips_write(self, tmp_path, fake_clip):
        fake_clip.text = "already-here"
        with open(str(tmp_path / CLIP_FILE), "w", encoding="utf-8") as fh:
            json.dump({"text": "already-here", "updated_at": "t", "writer": "p0"}, fh)
        fs = ClipboardFileSync(str(tmp_path), role="pull", backend=fake_clip.backend())
        out = fs.sync_once()
        assert out["changed"] is False
        assert "一致" in out["reason"]

    def test_pull_file_change_propagates(self, tmp_path, fake_clip):
        """p0 更新文件 → pull 端两次轮询间感知新内容。"""
        with open(str(tmp_path / CLIP_FILE), "w", encoding="utf-8") as fh:
            json.dump({"text": "v1", "updated_at": "t", "writer": "p0"}, fh)
        fs = ClipboardFileSync(str(tmp_path), role="pull", backend=fake_clip.backend())
        fs.sync_once()
        with open(str(tmp_path / CLIP_FILE), "w", encoding="utf-8") as fh:
            json.dump({"text": "v2", "updated_at": "t2", "writer": "p0"}, fh)
        out = fs.sync_once()
        assert out["changed"] is True
        assert fake_clip.text == "v2"


class TestEndToEndPushPull:
    def test_push_then_pull_roundtrip(self, tmp_path):
        """p0 push → 共享盘 → p1 pull 全链路（两个独立 FakeClip 模拟两台机器）。"""
        clip_p0, clip_p1 = FakeClip(""), FakeClip("")
        shared = tmp_path / "share"
        shared.mkdir()

        pusher = ClipboardFileSync(str(shared), role="push", backend=clip_p0.backend(),
                                   writer="p0")
        puller = ClipboardFileSync(str(shared), role="pull", backend=clip_p1.backend())

        clip_p0.text = "跨机文本-2026"
        assert pusher.sync_once()["changed"] is True
        assert puller.sync_once()["changed"] is True
        assert clip_p1.text == "跨机文本-2026"

        # 内容不变：两端再各跑一轮都应无变化
        assert pusher.sync_once()["changed"] is False
        assert puller.sync_once()["changed"] is False


class TestRunForever:
    def test_stops_via_event(self, tmp_path, fake_clip):
        stop = threading.Event()
        fs = ClipboardFileSync(str(tmp_path), role="push", backend=fake_clip.backend())
        stop.set()
        summary = fs.run_forever(poll_interval=0.01, stop_event=stop)
        assert summary["rounds"] >= 1
