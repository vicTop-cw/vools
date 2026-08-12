"""
VB6OpenSSL.dll 包装模块

提供便捷的 HTTPS 请求功能。
"""
from .dll import dll32


class OpenSSL:
    """OpenSSL HTTP 客户端"""

    @dll32('VB6OpenSSL.dll::OpenSSL_Get')
    def get(self, url: str, request_headers: str = '',
            response_headers: str = '', http_version: float = 1.0,
            is_utf8: int = 1, timeout: int = 10) -> str:
        """OpenSSL GET 请求

        Args:
            url: URL 地址 (支持 http/https)
            request_headers: 请求头
            response_headers: 响应头 (输出)
            http_version: HTTP 版本 (默认 1.0)
            is_utf8: 是否 UTF-8 编码 (1-是, 0-否)
            timeout: 超时时间 (秒, 默认 10)

        Returns:
            响应内容
        """
        pass

    @dll32('VB6OpenSSL.dll::OpenSSL_Post')
    def post(self, url: str, post_data: str,
             request_headers: str = 'content-type:application/x-www-form-urlencoded',
             response_headers: str = '', http_version: float = 1.0,
             is_utf8: int = 1, timeout: int = 10) -> str:
        """OpenSSL POST 请求

        Args:
            url: URL 地址 (支持 http/https)
            post_data: POST 数据
            request_headers: 请求头
            response_headers: 响应头 (输出)
            http_version: HTTP 版本 (默认 1.0)
            is_utf8: 是否 UTF-8 编码 (1-是, 0-否)
            timeout: 超时时间 (秒, 默认 10)

        Returns:
            响应内容
        """
        pass


# 全局实例
openssl = OpenSSL()
