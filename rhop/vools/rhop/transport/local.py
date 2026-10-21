"""vools.rhop.transport.local - 同机 shared path（本地目录介质，兼容旧 API）

MVP 判据 2: 同一机器两进程（A/B 模拟）通过 shared path 收发。
LocalSharedPath 基于多端视图实现（写读同视图），仍支持旧用法 root 目录。
写入由 LocalEndpoint 提供原子写（临时文件 + rename）。
"""

from .endpoint import LocalEndpoint
from .shared import SharedPathView


class LocalSharedPath(SharedPathView):
    """本地目录 shared path（写读同视图，兼容旧 API：root 参数）。"""

    def __init__(self, root: str):
        view = LocalEndpoint(root)
        SharedPathView.__init__(self, view)
