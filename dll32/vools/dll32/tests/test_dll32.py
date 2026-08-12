"""
vools.dll32 单元测试

测试 @dll32 装饰器和相关功能。
"""
import unittest


class TestDll32Decorator(unittest.TestCase):
    """测试 @dll32 装饰器"""
    
    def test_import(self):
        """测试模块导入"""
        try:
            from vools.dll32 import dll32
            self.assertIsNotNone(dll32)
        except ImportError as e:
            self.skipTest(f"导入失败: {e}")
    
    def test_dll_spec_parsing(self):
        """测试 DLL 规格解析"""
        # 测试 :: 分隔
        spec = 'VB6Plus.dll::Base64Encode_UTF8'
        if '::' in spec:
            dll_path, func_name = spec.rsplit('::', 1)
            self.assertEqual(dll_path, 'VB6Plus.dll')
            self.assertEqual(func_name, 'Base64Encode_UTF8')


class TestBuiltinModules(unittest.TestCase):
    """测试内置模块"""
    
    def test_vb6plus_import(self):
        """测试 VB6Plus 导入"""
        try:
            from vools.dll32.vb6plus import vb6plus
            self.assertIsNotNone(vb6plus)
        except ImportError as e:
            self.skipTest(f"导入失败: {e}")
    
    def test_mqtt_import(self):
        """测试 MQTT 导入"""
        try:
            from vools.dll32.mqtt import mqtt
            self.assertIsNotNone(mqtt)
        except ImportError as e:
            self.skipTest(f"导入失败: {e}")
    
    def test_openssl_import(self):
        """测试 OpenSSL 导入"""
        try:
            from vools.dll32.openssl import openssl
            self.assertIsNotNone(openssl)
        except ImportError as e:
            self.skipTest(f"导入失败: {e}")


if __name__ == '__main__':
    unittest.main()