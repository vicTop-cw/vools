"""
VB6MQTT.dll 包装模块

提供便捷的 MQTT 客户端功能。

注意：
- MQTT 是有状态的连接，由于当前实现每次调用都启动新进程，
  连接状态无法保持，建议用于单次发布等无状态场景。
- 未来可通过常驻进程模式支持完整的 MQTT 功能。
"""
from .dll import dll32


class MQTT:
    """MQTT 客户端"""

    @dll32('VB6MQTT.dll::MQTT_Open')
    def open(self, mqtt_client: int = 0, address: str = '', topic: str = '',
             client_id: str = '', username: str = '', password: str = '',
             qos: int = 1, str_err: str = '') -> int:
        """打开 MQTT 连接

        Args:
            mqtt_client: 客户端句柄 (输出参数，返回时被填充)
            address: 服务器地址 (host:port 格式)
            topic: 订阅主题
            client_id: 客户端 ID
            username: 用户名
            password: 密码
            qos: 服务质量等级 (0/1/2, 默认1)
            str_err: 错误信息 (输出参数)

        Returns:
            非0-成功, 0-失败
        """
        pass

    @dll32('VB6MQTT.dll::MQTT_Close')
    def close(self, mqtt_client: int, str_err: str = '') -> int:
        """关闭 MQTT 连接

        Args:
            mqtt_client: 客户端句柄
            str_err: 错误信息 (输出参数)

        Returns:
            非0-成功, 0-失败
        """
        pass

    @dll32('VB6MQTT.dll::MQTT_GetNewMsg')
    def get_new_msg(self, mqtt_client: int) -> str:
        """获取新消息

        Args:
            mqtt_client: 客户端句柄

        Returns:
            新消息内容
        """
        pass

    @dll32('VB6MQTT.dll::MQTT_PubMessage')
    def pub_message(self, mqtt_client: int, message: str,
                    qos: int = 1, timeout: int = 5000,
                    str_err: str = '') -> int:
        """发布消息

        Args:
            mqtt_client: 客户端句柄
            message: 消息内容 (格式: topic|payload)
            qos: 服务质量等级 (0/1/2, 默认1)
            timeout: 超时时间 (毫秒, 默认5000)
            str_err: 错误信息 (输出参数)

        Returns:
            非0-成功, 0-失败
        """
        pass


# 全局实例
mqtt = MQTT()
