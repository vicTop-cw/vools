"""vools.rhop.transport.shared - 多端视图 SharedPath

shared path 由 写端视图(write_view) + 读端视图(read_view) 共同描述同一介质，
各方用自己形态的地址访问（本地目录 / UNC / file:// / http(s)://）。

工厂 make_shared_path:
    make_shared_path("<share_dir>")                        # 单 spec：写读同视图（兼容旧用法）
    make_shared_path("<share_dir>", "file:///<share_dir>") # A 写本地，B 读 file://（同一介质）
    make_shared_path("<mount_point>:\\share", "\\\\NAS\\share")  # A 写盘符，B 读 UNC
"""

from typing import Optional

from .base import SharedPath
from .endpoint import EndpointView, parse_endpoint


class SharedPathView(SharedPath):
    """写端视图 + 读端视图描述的 shared path 实现。"""

    def __init__(self, write_view: EndpointView, read_view: Optional[EndpointView] = None):
        self.write_view = write_view
        self.read_view = read_view if read_view is not None else write_view
        self.name = "shared:{0}->{1}".format(self.write_view.display, self.read_view.display)

    @property
    def root(self):
        """兼容旧 API：读端视图的本地路径（若为本地形态），供 vools-rx 监控用。"""
        return getattr(self.read_view, "path", self.read_view.display)

    def available(self) -> bool:
        return self.write_view.available() and self.read_view.available()

    def write_text(self, filename: str, content: str) -> str:
        return self.write_view.write_text(filename, content)

    def read_text(self, filename: str) -> str:
        return self.read_view.read_text(filename)

    def exists(self, filename: str) -> bool:
        return self.read_view.exists(filename)

    def remove(self, filename: str) -> bool:
        return self.read_view.remove(filename)

    def __repr__(self):
        return "<SharedPathView {0}>".format(self.name)


def make_shared_path(write_spec: str, read_spec: Optional[str] = None, **kwargs) -> SharedPathView:
    """构造 shared path：write_spec 为写端地址，read_spec 为读端地址（缺省同写端）。

    地址形态: 本地路径 / UNC / 网络盘符 / file:// URL / http(s):// URL。
    """
    write_view = parse_endpoint(write_spec, **kwargs)
    if read_spec is None or read_spec == write_spec:
        return SharedPathView(write_view)
    read_view = parse_endpoint(read_spec, **kwargs)
    return SharedPathView(write_view, read_view)
