"""
Network 模块 - 网络功能

封装 API.Network COM 对象，提供网络检测、下载、URL 编解码、获取网页源码等功能。
"""

from ._base import APIBridgeError, _BaseModule


class NetworkModule(_BaseModule):
    """网络功能模块

    提供网络可用性检测、文件下载、URL 编解码、获取网页源码、IP 地址查询等功能。
    """

    _prog_id = "API.Network"

    def NetworkIsAvailable(self) -> bool:
        """检测网络是否可用

        Returns:
            bool: 网络是否可用
        """
        return self._call_bool("NetworkIsAvailable")

    def DownloadFile(self, url: str, save_path: str) -> bool:
        """下载文件到本地

        Args:
            url: 文件 URL
            save_path: 本地保存路径

        Returns:
            bool: 是否下载成功
        """
        return self._call_bool("DownloadFile", url, save_path)

    def UrlEncode(self, text: str) -> str:
        """URL 编码

        Args:
            text: 要编码的文本

        Returns:
            str: 编码后的字符串
        """
        return self._call_str("UrlEncode", text)

    def UrlDecode(self, text: str) -> str:
        """URL 解码

        Args:
            text: 要解码的 URL 编码字符串

        Returns:
            str: 解码后的文本
        """
        return self._call_str("UrlDecode", text)

    def GetWebSourceCode(self, url: str) -> str:
        """获取网页源代码

        Args:
            url: 网页 URL

        Returns:
            str: 网页 HTML 源码
        """
        return self._call_str("GetWebSourceCode", url)

    def GetIPAddresses(self) -> list:
        """获取本机 IP 地址列表

        Returns:
            list: IP 地址字符串列表
        """
        return self._call_list("GetIPAddresses")


Network = NetworkModule()
