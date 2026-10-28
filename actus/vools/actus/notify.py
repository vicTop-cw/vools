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
from typing import Dict, List, Optional, Callable
from vools.core.dataclass_compat import dataclass, field
from datetime import datetime
from enum import Enum

from ._proc import run_cmd_safe

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

    def send(self, msg: NotifyMessage) -> bool:
        """发到控制台；返回是否成功（供 notify() 判定真实投递结果）。"""
        icon = self.LEVEL_ICONS.get(msg.level, "📌")
        print(f"{icon} [{msg.timestamp}] {msg.title}")
        if msg.body:
            print(f"   {msg.body}")
        if msg.metadata:
            for k, v in msg.metadata.items():
                print(f"   {k}: {v}")
        return True


class SystemSender:
    """系统级通知。"""

    def send(self, msg: NotifyMessage) -> bool:
        """发送系统通知；返回是否成功。

        审计修：改前这里的异常被内部吞掉（只 logger.warning），`send()` 返回 None
        ⇒ 上层 `notify()` 无法区分"发出去了"和"发失败了"，只能当成功。现在如实返回。
        """
        try:
            if os.name == 'nt':
                self._send_windows(msg)
            elif os.uname().sysname == 'Darwin':
                self._send_macos(msg)
            else:
                self._send_linux(msg)
            return True
        except Exception as e:
            logger.warning(f"系统通知失败: {e}")
            return False

    def _send_windows(self, msg: NotifyMessage):
        """Windows 系统通知。"""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(msg.title, msg.body, duration=5)
        except ImportError:
            # 回退到 PowerShell
            # 审计修（命令注入）：title/body 会被拼进 `CreateTextNode('...')` 的
            # **单引号字符串**里；之前原样插值 ⇒ 标题里带 `x')); <语句>; #` 就能
            # 在 Windows 上执行任意 PowerShell（实测写文件成功）。PowerShell 单引号
            # 字符串里转义单引号的方式是把 `'` 写成 `''`，这里补上。
            ps_title = str(msg.title).replace("'", "''")
            ps_body = str(msg.body).replace("'", "''")
            cmd = [
                "powershell", "-Command",
                f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
                f"$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
                f"$text = $template.GetElementsByTagName('text');"
                f"$text[0].AppendChild($template.CreateTextNode('{ps_title}'));"
                f"$text[1].AppendChild($template.CreateTextNode('{ps_body}'));"
                f"$toast = [Windows.UI.Notifications.ToastNotification]::new($template);"
                f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Actus').Show($toast)"
            ]
            run_cmd_safe(cmd, timeout=10)

    def _send_macos(self, msg: NotifyMessage):
        """macOS 系统通知。"""
        # 审计修（同类注入）：AppleScript 字符串是**双引号**语义，title/body 里的
        # `"` 与 `\` 会提前闭合字符串 ⇒ 可注入 AppleScript 语句。先转义再拼接。
        def _as_quote(value):
            return str(value).replace('\\', '\\\\').replace('"', '\\"')
        cmd = [
            "osascript", "-e",
            'display notification "%s" with title "%s"'
            % (_as_quote(msg.body), _as_quote(msg.title))
        ]
        run_cmd_safe(cmd, timeout=10)

    def _send_linux(self, msg: NotifyMessage):
        """Linux 系统通知。"""
        cmd = ["notify-send", msg.title, msg.body]
        run_cmd_safe(cmd, timeout=10)


class WebhookSender:
    """Webhook 通知。"""

    def __init__(self, url: str = "", headers: dict = None):
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}

    def send(self, msg: NotifyMessage) -> bool:
        """发送 webhook；返回是否成功（无 url 视为未发送 = False）。"""
        if not self.url:
            return False

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
            # `with` 确保响应体被及时关闭：长驻进程里 urlopen 不关会累积 fd
            # 直到 GC，反复发通知最终耗尽句柄（2026-10-16 巡检发现）。
            with urllib.request.urlopen(req, timeout=10):
                pass
            return True
        except Exception as e:
            logger.warning(f"Webhook 发送失败: {e}")
            return False


class FileSender:
    """文件日志通知。"""

    def __init__(self, path: str = ""):
        self.path = path or os.path.join("_meta", "notifications.log")

    def send(self, msg: NotifyMessage) -> bool:
        """写入文件；返回是否成功（写盘异常不再被上层当成功）。"""
        log_dir = os.path.dirname(self.path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"[{msg.timestamp}] [{msg.level.value}] {msg.title}: {msg.body}\n")
        return True


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
               metadata: dict = None) -> dict:
        """发送通知，返回结构化投递结果。

        返回:
            {'delivered': bool, 'channel': str, 'error': str|None, 'timestamp': str}

        **审计修（假成功）**：改前吞掉发送异常、只 `logger.error`，照样把消息塞进
        `_history` 并 `return None` —— 于是用 `get_history()` / `stats()` 判断
        "通知发出去了没"的人得到**假阳性**（`total_sent` 连失败也计入）。
        现在：失败条目进历史但标 `delivered: False` + 原因；`total_sent` 只统计
        成功，另加 `total_failed` —— "没发出去"和"发出去了"能区分。
        """
        msg = NotifyMessage(
            title=title, body=body, level=level,
            channel=channel, metadata=metadata or {},
        )

        delivered = False
        error = None
        sender = self._senders.get(channel)
        if sender is None:
            error = f'no sender for channel {channel.value}'
            logger.warning(f"通知未发送（无对应 sender）: {channel.value}")
        else:
            try:
                # 只有**显式返回 False** 才算投递失败：内置 sender 全部返回 bool；
                # 第三方自定义 sender 若仍返回 None，保持旧的"不判定"语义（兼容）。
                result = sender.send(msg)
                delivered = (result is not False)
                if not delivered:
                    error = f'{type(sender).__name__} 报告未投递'
            except Exception as e:
                error = f'{type(e).__name__}: {e}'
                logger.error(f"通知发送失败: {e}")

        # 记录历史：**失败也记，但必须标 delivered=False**（不再伪装成功）
        self._history.append({
            "message": msg,
            "delivered": delivered,
            "error": error,
        })
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit:]

        return {'delivered': delivered, 'channel': channel.value,
                'error': error, 'timestamp': msg.timestamp}

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
        """获取通知历史（每条带真实 `delivered` 标记与失败原因）。"""
        out = []
        for entry in self._history[-limit:]:
            msg = entry.get("message")
            item = {
                "title": msg.title,
                "body": msg.body,
                "level": msg.level.value,
                "channel": msg.channel.value,
                "timestamp": msg.timestamp,
                "delivered": bool(entry.get("delivered")),
            }
            if entry.get("error"):
                item["error"] = entry["error"]
            out.append(item)
        return out

    def stats(self) -> dict:
        """统计信息：**成功/失败分开计数**，total_sent 只算真的发出去了的。"""
        delivered = sum(1 for e in self._history if e.get("delivered"))
        return {
            "total_sent": delivered,
            "total_failed": len(self._history) - delivered,
            "total_recorded": len(self._history),
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
