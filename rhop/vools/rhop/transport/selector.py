"""vools.rhop.transport.selector - 通道选择：在线优先，离线回退 shared path

MVP 判据 3: 有网介质（Git/SFTP）可用时优先走在线通道，不可用时自动回退 shared path。
"""

from typing import Iterable, List, Optional

from .base import OnlineChannel, SharedPath, TransportSelection


def select_transport(
    online_channels: Iterable[OnlineChannel],
    shared_path: SharedPath,
) -> TransportSelection:
    """按序探测在线通道；任一可用则选在线，否则回退 shared path。

    Args:
        online_channels: 在线通道列表（按优先级排序，如 [GitChannel, SftpChannel]）
        shared_path:     离线回退的 shared path 介质

    Returns:
        TransportSelection: (transport, is_online, reason)
    """
    channels = list(online_channels)
    for ch in channels:
        try:
            ok = ch.available()
        except Exception:
            ok = False
        if ok:
            return TransportSelection(ch, True, "在线通道可用: {0}".format(ch.name))
    if not shared_path.available():
        return TransportSelection(
            shared_path,
            False,
            "在线通道均不可用且 shared path 不可达: {0}".format(shared_path.name),
        )
    return TransportSelection(
        shared_path,
        False,
        "在线通道均不可用，回退 shared path: {0}".format(shared_path.name),
    )
