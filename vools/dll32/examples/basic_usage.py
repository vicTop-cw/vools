"""
vools.dll32 基本用法示例

演示如何使用 @dll32 装饰器调用 32 位 DLL。
"""
from vools.dll32 import dll32
from vools.dll32.vb6plus import vb6plus
from vools.dll32.mqtt import mqtt
from vools.dll32.openssl import openssl


def main():
    print("=" * 60)
    print("vools.dll32 基本用法示例")
    print("=" * 60)
    print()
    
    # 示例 1: 直接使用 @dll32 装饰器
    print("1. 直接使用 @dll32 装饰器")
    print("-" * 40)
    
    # 注意：由于是 32 位 DLL，需要通过管道通信调用
    # 以下是伪代码示例：
    
    # @dll32('VB6Plus.dll::Base64Encode_UTF8')
    # def base64_encode(input_data: str) -> str:
    #     pass
    #
    # result = base64_encode("Hello, World!")
    # print(f"Base64: {result}")
    
    print("  @dll32('VB6Plus.dll::Base64Encode_UTF8')")
    print("  def base64_encode(input_data: str) -> str:")
    print("      pass")
    print()
    
    # 示例 2: 使用内置包装
    print("2. 使用内置包装模块")
    print("-" * 40)
    
    print("  from vools.dll32.vb6plus import vb6plus")
    print("  from vools.dll32.mqtt import mqtt")
    print("  from vools.dll32.openssl import openssl")
    print()
    
    # 示例 3: MQTT 示例
    print("3. MQTT 连接示例")
    print("-" * 40)
    
    print("  # 连接 MQTT 服务器")
    print("  mqtt.open('broker.example.com', 1883, 'client_id', 'user', 'pass')")
    print()
    print("  # 发布消息")
    print("  mqtt.pub_message('topic', 'Hello MQTT!', qos=1)")
    print()
    print("  # 关闭连接")
    print("  mqtt.close()")
    print()
    
    # 示例 4: HTTPS 请求
    print("4. HTTPS GET 请求示例")
    print("-" * 40)
    
    print("  response = openssl.get('https://api.example.com/data')")
    print("  print(response)")
    print()
    
    print("=" * 60)
    print("示例结束")
    print("=" * 60)


if __name__ == '__main__':
    main()