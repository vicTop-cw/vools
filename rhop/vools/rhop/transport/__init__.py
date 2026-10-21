"""vools.rhop.transport - 传输抽象：在线通道 + shared path 回退

shared path 本质: 发送方写到"它能写的地方"，且该地方是接收方"它能读的地方"；
双方共同可达的介质，不限定具体技术（同机目录 / SFTP / Git 仓库 / 中间方 C 等）。

通道选择: 有网时优先在线通道（Git / SFTP），否则自动回退 shared path。
SftpChannel 为 paramiko 优先（真实 SFTP 读写），paramiko 缺失或连接失败时回退注入式
reader/writer；详见 docs/sftp-channel.md。
"""

from .base import OnlineChannel, SharedPath, TransportSelection
from .endpoint import (
    EndpointView,
    FileUrlEndpoint,
    HttpEndpoint,
    LocalEndpoint,
    parse_endpoint,
)
from .local import LocalSharedPath
from .online import GitChannel, SftpChannel
from .relay import RelayChannel, RelayServer
from .selector import select_transport
from .shared import SharedPathView, make_shared_path

__all__ = [
    "OnlineChannel",
    "SharedPath",
    "TransportSelection",
    "EndpointView",
    "LocalEndpoint",
    "FileUrlEndpoint",
    "HttpEndpoint",
    "parse_endpoint",
    "LocalSharedPath",
    "GitChannel",
    "SftpChannel",
    "RelayChannel",
    "RelayServer",
    "SharedPathView",
    "make_shared_path",
    "select_transport",
]
