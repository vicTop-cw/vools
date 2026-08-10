"""
FileSystem 模块 - 文件系统操作

封装 API.FileSystem COM 对象，提供文件和目录的创建、删除、读写等功能。
"""

from typing import Optional

from ._base import APIBridgeError, _BaseModule


class FileSystemModule(_BaseModule):
    """文件系统操作模块

    提供目录和文件的创建、删除、判断、读写、路径操作等功能。
    """

    _prog_id = "API.FileSystem"

    def CreateDirectory(self, path: str) -> bool:
        """创建目录

        Args:
            path: 目录路径

        Returns:
            bool: 是否成功
        """
        return self._call_bool("CreateDirectory", path)

    def DeleteDirectory(self, path: str) -> bool:
        """删除目录

        Args:
            path: 目录路径

        Returns:
            bool: 是否成功
        """
        return self._call_bool("DeleteDirectory", path)

    def DeleteFile(self, path: str) -> bool:
        """删除文件

        Args:
            path: 文件路径

        Returns:
            bool: 是否成功
        """
        return self._call_bool("DeleteFile", path)

    def ReadAllText(self, path: str, encoding: Optional[str] = None) -> str:
        """读取文本文件全部内容

        Args:
            path: 文件路径
            encoding: 编码名称，如 "UTF-8"、"GBK" 等，为 None 时使用默认编码

        Returns:
            str: 文件内容
        """
        if encoding is None:
            return self._call_str("ReadAllText", path)
        return self._call_str("ReadAllText", path, encoding)

    def WriteAllText(self, path: str, text: str, encoding: Optional[str] = None) -> bool:
        """写入文本到文件（覆盖）

        Args:
            path: 文件路径
            text: 要写入的文本
            encoding: 编码名称，如 "UTF-8"、"GBK" 等，为 None 时使用默认编码

        Returns:
            bool: 是否成功
        """
        if encoding is None:
            return self._call_bool("WriteAllText", path, text)
        return self._call_bool("WriteAllText", path, text, encoding)

    def CombinePath(self, path1: str, path2: str) -> str:
        """合并两个路径

        Args:
            path1: 第一个路径
            path2: 第二个路径

        Returns:
            str: 合并后的路径
        """
        return self._call_str("CombinePath", path1, path2)

    def DirectoryExists(self, path: str) -> bool:
        """判断目录是否存在

        Args:
            path: 目录路径

        Returns:
            bool: 目录是否存在
        """
        return self._call_bool("DirectoryExists", path)

    def FileExists(self, path: str) -> bool:
        """判断文件是否存在

        Args:
            path: 文件路径

        Returns:
            bool: 文件是否存在
        """
        return self._call_bool("FileExists", path)

    def GetParentPath(self, path: str) -> str:
        """获取父目录路径

        Args:
            path: 路径

        Returns:
            str: 父目录路径
        """
        return self._call_str("GetParentPath", path)

    def CopyFile(self, src: str, dst: str) -> bool:
        """复制文件

        Args:
            src: 源文件路径
            dst: 目标文件路径

        Returns:
            bool: 是否成功
        """
        return self._call_bool("CopyFile", src, dst)

    def MoveFile(self, src: str, dst: str) -> bool:
        """移动文件

        Args:
            src: 源文件路径
            dst: 目标文件路径

        Returns:
            bool: 是否成功
        """
        return self._call_bool("MoveFile", src, dst)

    def RenameFile(self, path: str, new_name: str) -> bool:
        """重命名文件

        Args:
            path: 原文件路径
            new_name: 新文件名（不含路径）

        Returns:
            bool: 是否成功
        """
        return self._call_bool("RenameFile", path, new_name)


FileSystem = FileSystemModule()
