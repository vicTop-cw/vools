"""notify.py — 通知系统 (Phase N3)。

支持多种通知渠道：
- 控制台输出（默认）
- 系统通知（Windows toast / macOS notify / Linux notify-send）
- Webhook（HTTP POST）
- 邮件（SMTP）
- 文件日志

通知触发条件：
- 动作执行完成/失败
- 工作流节点状态变化
- 文件监控事件
- 自定义条件
"""

import json
import os
import logging
import subprocess
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class NotifyLevel(Enum):
    """通知级别。"""
    DEBUG = "debug"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotifyChannel(Enum):
    """通知渠道。"""
    CONSOLE = "console"
    SYSTEM = "system"
    WEBHOOK = "webhook"
    EMAIL = "email"
    FILE = "file"


@dataclass
class NotifyMessage:
    """通知消息。"""
    title: str
    body: str
    level: NotifyLevel = NotifyLevel.INFO
    channel: NotifyChannel = NotifyChannel.CONSOLE
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class NotifyRule:
    """通知规则。"""
    name: str
    condition: str          # 条件表达式（如 "status == 'failed'"）
    channel: NotifyChannel
    template: str           # 消息模板
    enabled: bool = True
    cooldown: float = 0.0   # 冷却时间（秒）
    _last_fired: float = 0.0


# ── 通知发送器 ──────────────────────────────────────────────────────────────

class ConsoleSender:
    """控制台通知。"""

    LEVEL_ICONS = {
        NotifyLevel.DEBUG: "🔍",
        NotifyLevel.INFO: "ℹ️",
        NotifyLevel.SUCCESS: "✅",
        NotifyLevel.WARNING: "⚠️",
        NotifyLevel.ERROR: "❌",
    }

    def send(self, msg: NotifyMessage):
        icon = self.LEVEL_ICONS.get(msg.level, "📌")
        print(f"{icon} [{msg.timestamp}] {msg.title}")
        if msg.body:
            print(f"   {msg.body}")
        if msg.metadata:
            for k, v in msg.metadata.items():
                print(f"   {k}: {v}")


class SystemSender:
    """系统级通知。"""

    def send(self, msg: NotifyMessage):
        """发送系统通知。"""
        try:
            if os.name == 'nt':
                self._send_windows(msg)
            elif os.uname().sysname == 'Darwin':
                self._send_macos(msg)
            else:
                self._send_linux(msg)
        except Exception as e:
            logger.warning(f"系统通知失败: {e}")

    def _send_windows(self, msg: NotifyMessage):
        """Windows 系统通知。"""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(msg.title, msg.body, duration=5)
        except ImportError:
            # 回退到 PowerShell
            cmd = [
                "powershell", "-Command",
                f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
                f"$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
                f"$text = $template.GetElementsByTagName('text');"
                f"$text[0].AppendChild($template.CreateTextNode('{msg.title}'));"
                f"$text[1].AppendChild($template.CreateTextNode('{msg.body}'));"
                f"$toast = [Windows.UI.Notifications.ToastNotification]::new($template);"
                f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Actus').Show($toast)"
            ]
            subprocess.run(cmd, capture_output=True, timeout=10)

    def _send_macos(self, msg: NotifyMessage):
        """macOS 系统通知。"""
        cmd = [
            "osascript", "-e",
            f'display notification "{msg.body}" with title "{msg.title}"'
        ]
        subprocess.run(cmd, capture_output=True, timeout=10)

    def _send_linux(self, msg: NotifyMessage):
        """Linux 系统通知。"""
        cmd = ["notify-send", msg.title, msg.body]
        subprocess.run(cmd, capture_output=True, timeout=10)


class WebhookSender:
    """Webhook 通知。"""

    def __init__(self, url: str = "", headers: dict = None):
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}

    def send(self, msg: NotifyMessage):
        """发送 webhook。"""
        if not self.url:
            return

        import urllib.request
        import urllib.error

        payload = json.dumps({
            "title": msg.title,
            "body": msg.body,
            "level": msg.level.value,
            "timestamp": msg.timestamp,
            "metadata": msg.metadata,
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            self.url, data=payload, method="POST", headers=self.headers
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logger.warning(f"Webhook 发送失败: {e}")


class FileSender:
    """文件日志通知。"""

    def __init__(self, path: str = ""):
        self.path = path or os.path.join("_meta", "notifications.log")

    def send(self, msg: NotifyMessage):
        """写入文件。"""
        log_dir = os.path.dirname(self.path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"[{msg.timestamp}] [{msg.level.value}] {msg.title}: {msg.body}\n")


# ── 通知管理器 ──────────────────────────────────────────────────────────────

class NotificationManager:
    """通知管理器。

    管理通知渠道、规则和发送。
    """

    def __init__(self):
        self._senders: Dict[NotifyChannel, object] = {
            NotifyChannel.CONSOLE: ConsoleSender(),
            NotifyChannel.SYSTEM: SystemSender(),
            NotifyChannel.FILE: FileSender(),
        }
        self._rules: List[NotifyRule] = []
        self._history: List[NotifyMessage] = []
        self._history_limit = 100

    def configure(self, channel: NotifyChannel, **kwargs):
        """配置通知渠道。"""
        if channel == NotifyChannel.WEBHOOK:
            self._senders[channel] = WebhookSender(
                url=kwargs.get("url", ""),
                headers=kwargs.get("headers"),
            )
        elif channel == NotifyChannel.FILE:
            self._senders[channel] = FileSender(
                path=kwargs.get("path", ""),
            )

    def add_rule(self, rule: NotifyRule):
        """添加通知规则。"""
        self._rules.append(rule)

    def remove_rule(self, name: str):
        """移除通知规则。"""
        self._rules = [r for r in self._rules if r.name != name]

    def notify(self, title: str, body: str,
               level: NotifyLevel = NotifyLevel.INFO,
               channel: NotifyChannel = NotifyChannel.CONSOLE,
               metadata: dict = None):
        """发送通知。"""
        msg = NotifyMessage(
            title=title, body=body, level=level,
            channel=channel, metadata=metadata or {},
        )

        sender = self._senders.get(channel)
        if sender:
            try:
                sender.send(msg)
            except Exception as e:
                logger.error(f"通知发送失败: {e}")

        # 记录历史
        self._history.append(msg)
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit:]

    def check_rules(self, context: dict):
        """检查规则并触发通知。"""
        for rule in self._rules:
            if not rule.enabled:
                continue

            # 冷却检查
            if rule.cooldown > 0:
                now = datetime.now().timestamp()
                if now - rule._last_fired < rule.cooldown:
                    continue

            # 条件评估
            if self._evaluate_condition(rule.condition, context):
                msg = rule.template.format(**context)
                level = NotifyLevel.INFO
                if context.get("status") == "failed":
                    level = NotifyLevel.ERROR
                elif context.get("status") == "ok":
                    level = NotifyLevel.SUCCESS

                self.notify(
                    title=f"规则: {rule.name}",
                    body=msg,
                    level=level,
                    channel=rule.channel,
                    metadata=context,
                )
                rule._last_fired = datetime.now().timestamp()

    def _evaluate_condition(self, condition: str, context: dict) -> bool:
        """评估条件表达式。

        支持简单的 key == 'value' 和 key != 'value' 形式。
        """
        if not condition:
            return True

        # 简单条件解析
        for op in ["==", "!="]:
            if op in condition:
                parts = condition.split(op, 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().strip("'\"")
                    ctx_val = str(context.get(key, ""))
                    if op == "==":
                        return ctx_val == value
                    else:
                        return ctx_val != value

        return False

    def get_history(self, limit: int = 20) -> List[dict]:
        """获取通知历史。"""
        return [
            {
                "title": m.title,
                "body": m.body,
                "level": m.level.value,
                "channel": m.channel.value,
                "timestamp": m.timestamp,
            }
            for m in self._history[-limit:]
        ]

    def stats(self) -> dict:
        """统计信息。"""
        return {
            "total_sent": len(self._history),
            "rules_count": len(self._rules),
            "channels": [c.value for c in self._senders.keys()],
        }


# ── 单例 ──────────────────────────────────────────────────────────────────

_manager = NotificationManager()


def get_notification_manager() -> NotificationManager:
    """获取全局通知管理器。"""
    return _manager


__all__ = [
    'ConsoleSender',
    'FileSender',
    'NotificationManager',
    'NotifyChannel',
    'NotifyLevel',
    'NotifyMessage',
    'NotifyRule',
    'SystemSender',
    'WebhookSender',
    'get_notification_manager',
    'logger'
]
