"""vools.rhop.transport.base - 传输抽象基类

SharedPath:    双方共同可达的介质抽象（本地目录 / 挂载盘 / 中间方共享区等）
OnlineChannel: 在线通道抽象（Git 仓库中继 / SFTP 等），可用时优先
"""

import abc
from typing import NamedTuple, Optional


class SharedPath(abc.ABC):
    """shared path 介质抽象：发送方写、接收方读的共同可达位置。

    实现要求（子类）:
        name:         介质名（如 "local:/tmp/shared"）
        available():  该介质当前是否可达
        write_text(): 写入文本内容（建议原子写：先写临时文件再 rename）
        read_text():  读取文本内容
        exists():     判断文件名是否存在
        remove():     删除文件（接收方处理后清理）
    """

    name = "shared-path"

    @abc.abstractmethod
    def available(self) -> bool:
        """介质是否可达。"""

    @abc.abstractmethod
    def write_text(self, filename: str, content: str) -> str:
        """写入文本内容，返回落盘完整路径。"""

    @abc.abstractmethod
    def read_text(self, filename: str) -> str:
        """读取文本内容；不存在时抛 FileNotFoundError。"""

    @abc.abstractmethod
    def exists(self, filename: str) -> bool:
        """判断文件名是否存在。"""

    @abc.abstractmethod
    def remove(self, filename: str) -> bool:
        """删除文件；不存在返回 False。"""


class OnlineChannel(abc.ABC):
    """在线通道抽象：有网时的首选传输方式。"""

    name = "online-channel"

    @abc.abstractmethod
    def available(self) -> bool:
        """探测在线通道是否可用（如远端可达）。"""

    @abc.abstractmethod
    def send(self, filename: str, content: str) -> None:
        """把一包内容发到远端。"""

    @abc.abstractmethod
    def receive(self, filename: str) -> str:
        """从远端取一包内容；不存在时抛 FileNotFoundError。"""


class TransportSelection(NamedTuple):
    """通道选择结果。

    transport:  实际使用的传输对象（OnlineChannel 或 SharedPath）
    is_online:  True=在线通道 / False=回退 shared path
    reason:     选择说明
    """

    transport: object
    is_online: bool
    reason: str
