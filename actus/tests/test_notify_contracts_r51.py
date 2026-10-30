"""notify.py 契约测试（Round 47）。

契约:
- NotifyLevel / NotifyChannel 枚举
- NotifyMessage: timestamp 自动填充
- ConsoleSender: 打印格式 + 返回 True
- SystemSender: 各平台路径 + 异常返回 False
- WebhookSender: 无 url 返回 False + 有 url 发 HTTP
- FileSender: 写入文件
- NotificationManager: notify/configure/get_history/stats
- 单例: get_notification_manager
"""

import io
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from vools.actus.notify import (
    ConsoleSender,
    FileSender,
    NotificationManager,
    NotifyChannel,
    NotifyLevel,
    NotifyMessage,
    SystemSender,
    WebhookSender,
    get_notification_manager,
)


class TestNotifyMessage:
    """NotifyMessage 数据类。"""

    def test_default_level(self):
        m = NotifyMessage(title="t", body="b")
        assert m.level == NotifyLevel.INFO

    def test_default_channel(self):
        m = NotifyMessage(title="t", body="b")
        assert m.channel == NotifyChannel.CONSOLE

    def test_timestamp_auto_set(self):
        m = NotifyMessage(title="t", body="b")
        assert m.timestamp != ""

    def test_explicit_timestamp(self):
        m = NotifyMessage(title="t", body="b", timestamp="2024-01-01")
        assert m.timestamp == "2024-01-01"

    def test_metadata_default(self):
        m = NotifyMessage(title="t", body="b")
        assert m.metadata == {}

    def test_explicit_metadata(self):
        m = NotifyMessage(title="t", body="b", metadata={"k": "v"})
        assert m.metadata["k"] == "v"

    def test_all_levels(self):
        for lvl in NotifyLevel:
            m = NotifyMessage(title="t", body="b", level=lvl)
            assert m.level == lvl

    def test_all_channels(self):
        for ch in NotifyChannel:
            m = NotifyMessage(title="t", body="b", channel=ch)
            assert m.channel == ch


class TestConsoleSender:
    """ConsoleSender。"""

    def test_send_success(self, capsys):
        s = ConsoleSender()
        msg = NotifyMessage(title="Test", body="Hello")
        result = s.send(msg)
        assert result is True
        out = capsys.readouterr()
        assert "Test" in out.out
        assert "Hello" in out.out

    def test_send_with_metadata(self, capsys):
        s = ConsoleSender()
        msg = NotifyMessage(title="Test", body="Hello", metadata={"k": "v"})
        s.send(msg)
        out = capsys.readouterr()
        assert "k: v" in out.out

    def test_send_with_body(self, capsys):
        s = ConsoleSender()
        msg = NotifyMessage(title="Test", body="Body text")
        s.send(msg)
        out = capsys.readouterr()
        assert "Body text" in out.out

    def test_send_no_body(self, capsys):
        s = ConsoleSender()
        msg = NotifyMessage(title="Test", body="")
        s.send(msg)
        out = capsys.readouterr()
        assert "Test" in out.out

    def test_send_no_metadata(self, capsys):
        s = ConsoleSender()
        msg = NotifyMessage(title="Test", body="Body")
        s.send(msg)
        out = capsys.readouterr()
        # 不应有 metadata 行
        assert "k: v" not in out.out

    def test_level_icons(self):
        s = ConsoleSender()
        # 所有 level 都应有图标
        for lvl in NotifyLevel:
            icon = s.LEVEL_ICONS.get(lvl, "📌")
            assert icon != ""


class TestSystemSender:
    """SystemSender。"""

    def test_send_success(self, monkeypatch):
        """send 成功路径：直接调用 _send_windows。"""
        s = SystemSender()
        def mock_send_windows(self, msg):
            return None
        monkeypatch.setattr(SystemSender, "_send_windows", mock_send_windows)
        msg = NotifyMessage(title="Test", body="Hello")
        result = s.send(msg)
        assert result is True

    def test_send_failure(self, monkeypatch):
        """send 失败路径：_send_windows 抛异常应返回 False。"""
        s = SystemSender()
        def raise_err(self, msg):
            raise RuntimeError("boom")
        monkeypatch.setattr(SystemSender, "_send_windows", raise_err)
        msg = NotifyMessage(title="Test", body="Hello")
        result = s.send(msg)
        assert result is False

    def test_send_macos(self, monkeypatch):
        """macOS 路径：直接调用 _send_macos。"""
        s = SystemSender()
        captured = {}
        def mock_run_cmd_safe(cmd, **kw):
            captured['cmd'] = cmd
        import vools.actus.notify as notify_mod
        monkeypatch.setattr(notify_mod, "run_cmd_safe", mock_run_cmd_safe)
        msg = NotifyMessage(title="Test", body="Hello")
        s._send_macos(msg)
        assert captured['cmd'][0] == "osascript"

    def test_send_linux(self, monkeypatch):
        """Linux 路径：直接调用 _send_linux。"""
        s = SystemSender()
        captured = {}
        def mock_run_cmd_safe(cmd, **kw):
            captured['cmd'] = cmd
        import vools.actus.notify as notify_mod
        monkeypatch.setattr(notify_mod, "run_cmd_safe", mock_run_cmd_safe)
        msg = NotifyMessage(title="Test", body="Hello")
        s._send_linux(msg)
        assert captured['cmd'][0] == "notify-send"

    def test_send_windows_powershell_fallback(self, monkeypatch):
        """win10toast 不可用时回退到 PowerShell。"""
        s = SystemSender()
        # 强制 ImportError
        import sys
        sys.modules['win10toast'] = None
        captured = {}
        def mock_run_cmd_safe(cmd, **kw):
            captured['cmd'] = cmd
        import vools.actus.notify as notify_mod
        monkeypatch.setattr(notify_mod, "run_cmd_safe", mock_run_cmd_safe)
        msg = NotifyMessage(title="Test", body="Hello")
        s._send_windows(msg)
        assert captured['cmd'][0] == "powershell"

    def test_send_windows_injection_protection(self, monkeypatch):
        """Windows PowerShell 路径应转义单引号。"""
        s = SystemSender()
        import sys
        sys.modules['win10toast'] = None
        captured = {}
        def mock_run_cmd_safe(cmd, **kw):
            captured['cmd'] = cmd
        import vools.actus.notify as notify_mod
        monkeypatch.setattr(notify_mod, "run_cmd_safe", mock_run_cmd_safe)
        msg = NotifyMessage(title="Test's", body="Hello")
        s._send_windows(msg)
        # 单引号应被转义为双单引号
        assert "Test''s" in ''.join(captured['cmd'])


class TestWebhookSender:
    """WebhookSender。"""

    def test_send_no_url(self):
        s = WebhookSender()
        msg = NotifyMessage(title="Test", body="Hello")
        result = s.send(msg)
        assert result is False

    def test_send_with_url(self, monkeypatch):
        """有 url 时应发送 HTTP。"""
        s = WebhookSender(url="http://example.com/notify")
        captured = {}
        def mock_urlopen(req, timeout=0):
            captured['req'] = req
            return MagicMock()
        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        msg = NotifyMessage(title="Test", body="Hello")
        result = s.send(msg)
        assert result is True
        assert captured['req'].method == "POST"

    def test_send_url_error(self, monkeypatch):
        """urlopen 失败应返回 False。"""
        s = WebhookSender(url="http://example.com/notify")
        def raise_err(req, timeout=0):
            raise RuntimeError("connection refused")
        monkeypatch.setattr("urllib.request.urlopen", raise_err)
        msg = NotifyMessage(title="Test", body="Hello")
        result = s.send(msg)
        assert result is False

    def test_send_custom_headers(self):
        s = WebhookSender(url="http://example.com", headers={"X-Custom": "yes"})
        assert s.headers["X-Custom"] == "yes"


class TestFileSender:
    """FileSender。"""

    def test_send_default_path(self, tmp_path, monkeypatch):
        """默认路径应创建目录并写入。"""
        monkeypatch.chdir(tmp_path)
        s = FileSender()
        msg = NotifyMessage(title="Test", body="Hello")
        result = s.send(msg)
        assert result is True
        assert os.path.exists("_meta/notifications.log")

    def test_send_custom_path(self, tmp_path):
        s = FileSender(path=str(tmp_path / "test.log"))
        msg = NotifyMessage(title="Test", body="Hello")
        result = s.send(msg)
        assert result is True
        content = open(tmp_path / "test.log").read()
        assert "Test" in content
        assert "Hello" in content

    def test_send_append(self, tmp_path):
        """多次写入应追加。"""
        path = tmp_path / "test.log"
        s = FileSender(path=str(path))
        msg1 = NotifyMessage(title="First", body="One")
        msg2 = NotifyMessage(title="Second", body="Two")
        s.send(msg1)
        s.send(msg2)
        lines = open(path).readlines()
        assert len(lines) == 2
        assert "First" in lines[0]
        assert "Second" in lines[1]


class TestNotificationManager:
    """NotificationManager。"""

    def test_notify_console(self, capsys):
        mgr = NotificationManager()
        result = mgr.notify("Test", "Hello")
        assert result['delivered'] is True
        assert result['channel'] == 'console'

    def test_notify_unknown_channel(self):
        mgr = NotificationManager()
        result = mgr.notify("Test", "Hello", channel=NotifyChannel.EMAIL)
        assert result['delivered'] is False
        assert 'error' in result

    def test_notify_with_metadata(self):
        mgr = NotificationManager()
        result = mgr.notify("Test", "Hello", metadata={"k": "v"})
        assert result['delivered'] is True

    def test_notify_system(self, monkeypatch):
        """SYSTEM 通道：直接 mock _send_windows。"""
        mgr = NotificationManager()
        def mock_send_windows(self, msg):
            return None
        monkeypatch.setattr(SystemSender, "_send_windows", mock_send_windows)
        result = mgr.notify("Test", "Hello", channel=NotifyChannel.SYSTEM)
        assert result['delivered'] is True

    def test_notify_system_exception(self, monkeypatch):
        """SYSTEM 通道 sender 抛异常应返回 delivered=False。"""
        mgr = NotificationManager()
        def raise_err(self, msg):
            raise RuntimeError("boom")
        monkeypatch.setattr(SystemSender, "_send_windows", raise_err)
        result = mgr.notify("Test", "Hello", channel=NotifyChannel.SYSTEM)
        assert result['delivered'] is False
        assert 'error' in result

    def test_notify_sender_raises_exception(self):
        """sender.send() 抛异常应在 notify 中被捕获。"""
        mgr = NotificationManager()
        # 用一个会抛异常的自定义 sender
        class BadSender:
            def send(self, msg):
                raise ValueError("bad sender")
        mgr._senders[NotifyChannel.CONSOLE] = BadSender()
        result = mgr.notify("Test", "Hello", channel=NotifyChannel.CONSOLE)
        assert result['delivered'] is False
        assert 'error' in result

    def test_get_history_with_error(self):
        """get_history 应包含 error 字段。"""
        mgr = NotificationManager()
        mgr.notify("Test", "Hello", channel=NotifyChannel.EMAIL)
        history = mgr.get_history()
        assert len(history) == 1
        assert 'error' in history[0]

    def test_evaluate_condition_empty(self):
        """空条件应返回 True。"""
        mgr = NotificationManager()
        assert mgr._evaluate_condition("", {}) is True

    def test_evaluate_condition_eq(self):
        """key == 'value' 条件。"""
        mgr = NotificationManager()
        assert mgr._evaluate_condition("status == 'done'", {"status": "done"}) is True
        assert mgr._evaluate_condition("status == 'done'", {"status": "running"}) is False

    def test_evaluate_condition_ne(self):
        """key != 'value' 条件。"""
        mgr = NotificationManager()
        assert mgr._evaluate_condition("status != 'done'", {"status": "running"}) is True
        assert mgr._evaluate_condition("status != 'done'", {"status": "done"}) is False

    def test_evaluate_condition_no_match(self):
        """无条件表达式应返回 False。"""
        mgr = NotificationManager()
        assert mgr._evaluate_condition("no operators", {}) is False

    def test_evaluate_condition_missing_key(self):
        """key 不在 context 中应返回 False。"""
        mgr = NotificationManager()
        assert mgr._evaluate_condition("missing == 'val'", {}) is False

    def test_notify_file(self, tmp_path):
        mgr = NotificationManager()
        mgr.configure(NotifyChannel.FILE, path=str(tmp_path / "test.log"))
        result = mgr.notify("Test", "Hello", channel=NotifyChannel.FILE)
        assert result['delivered'] is True
        assert os.path.exists(tmp_path / "test.log")

    def test_notify_webhook_no_url(self):
        mgr = NotificationManager()
        mgr.configure(NotifyChannel.WEBHOOK, url="")
        result = mgr.notify("Test", "Hello", channel=NotifyChannel.WEBHOOK)
        assert result['delivered'] is False

    def test_configure_webhook(self):
        mgr = NotificationManager()
        mgr.configure(NotifyChannel.WEBHOOK, url="http://example.com")
        assert mgr._senders[NotifyChannel.WEBHOOK].url == "http://example.com"

    def test_configure_file(self, tmp_path):
        mgr = NotificationManager()
        mgr.configure(NotifyChannel.FILE, path=str(tmp_path / "test.log"))
        assert mgr._senders[NotifyChannel.FILE].path == str(tmp_path / "test.log")

    def test_get_history(self):
        mgr = NotificationManager()
        mgr.notify("Test1", "Hello1")
        mgr.notify("Test2", "Hello2")
        history = mgr.get_history()
        assert len(history) == 2
        assert history[0]['title'] == "Test1"
        assert history[1]['title'] == "Test2"

    def test_get_history_limit(self):
        mgr = NotificationManager()
        for i in range(30):
            mgr.notify(f"Test{i}", f"Hello{i}")
        history = mgr.get_history(limit=5)
        assert len(history) == 5

    def test_stats(self):
        mgr = NotificationManager()
        mgr.notify("Test1", "Hello1")
        mgr.notify("Test2", "Hello2")
        stats = mgr.stats()
        assert stats['total_sent'] == 2
        assert stats['total_recorded'] == 2
        assert 'console' in stats['channels']

    def test_stats_failed(self):
        mgr = NotificationManager()
        mgr.notify("Test1", "Hello1", channel=NotifyChannel.EMAIL)  # 无 sender
        stats = mgr.stats()
        assert stats['total_sent'] == 0
        assert stats['total_failed'] == 1

    def test_history_limit_trim(self):
        mgr = NotificationManager()
        mgr._history_limit = 3
        mgr.notify("Test1", "Hello1")
        mgr.notify("Test2", "Hello2")
        mgr.notify("Test3", "Hello3")
        mgr.notify("Test4", "Hello4")
        history = mgr.get_history()
        assert len(history) == 3
        assert history[0]['title'] == "Test2"


class TestSingleton:
    """get_notification_manager。"""

    def test_get_manager(self):
        mgr = get_notification_manager()
        assert isinstance(mgr, NotificationManager)

    def test_same_instance(self):
        mgr1 = get_notification_manager()
        mgr2 = get_notification_manager()
        assert mgr1 is mgr2


class TestModuleExports:
    """模块导出。"""

    def test_all_exports(self):
        import vools.actus.notify as n
        assert 'ConsoleSender' in n.__all__
        assert 'FileSender' in n.__all__
        assert 'NotificationManager' in n.__all__
        assert 'NotifyChannel' in n.__all__
        assert 'NotifyLevel' in n.__all__
        assert 'NotifyMessage' in n.__all__
        assert 'SystemSender' in n.__all__
        assert 'WebhookSender' in n.__all__
        assert 'get_notification_manager' in n.__all__
