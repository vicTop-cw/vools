"""测试 dll32 核心功能"""
from vools.dll32 import vb6plus
import tempfile
import os

# 测试 HTML 编解码
print('=== HTML 编解码 ===')
try:
    encoded = vb6plus.html_encode('<div>test & "quote"</div>')
    print('HTML 编码:', encoded)
    decoded = vb6plus.html_decode(encoded)
    print('HTML 解码:', decoded)
    print('HTML 测试通过')
except Exception as e:
    print('HTML 测试失败:', e)

# 测试 URL 编解码
print()
print('=== URL 编解码 ===')
try:
    encoded = vb6plus.url_encode_utf8('hello world!@#')
    print('URL 编码:', encoded)
    decoded = vb6plus.url_decode_utf8(encoded)
    print('URL 解码:', decoded)
    print('URL 测试通过')
except Exception as e:
    print('URL 测试失败:', e)

# 测试字符串相似度
print()
print('=== 字符串相似度 ===')
try:
    sim = vb6plus.str_compare('hello', 'hallo')
    print('相似度 (hello vs hallo):', sim)
    print('字符串相似度测试通过')
except Exception as e:
    print('字符串相似度测试失败:', e)

# 测试 INI 文件操作
print()
print('=== INI 文件操作 ===')
try:
    tmp_dir = tempfile.gettempdir()
    ini_file = os.path.join(tmp_dir, 'test_vools.ini')
    vb6plus.write_ini_value('TestSection', 'TestKey', 'TestValue', ini_file)
    value = vb6plus.read_ini_value('TestSection', 'TestKey', 'Default', ini_file)
    print('写入值: TestValue')
    print('读取值:', value)
    print('INI 文件操作测试通过')
    os.remove(ini_file)
except Exception as e:
    print('INI 文件操作测试失败:', e)

# 测试正则替换
print()
print('=== 正则替换 ===')
try:
    result = vb6plus.regex_replace('hello world', 'world', 'vools')
    print('正则替换结果:', result)
    print('正则替换测试通过')
except Exception as e:
    print('正则替换测试失败:', e)

# 测试 Hex 编解码
print()
print('=== Hex 编解码 ===')
try:
    hex_str = vb6plus.str_to_hex_utf8('Hello')
    print('字符串转 Hex:', hex_str)
    decoded = vb6plus.hex_to_str_utf8(hex_str)
    print('Hex 转字符串:', decoded)
    print('Hex 编解码测试通过')
except Exception as e:
    print('Hex 编解码测试失败:', e)

print()
print('=== 所有测试完成 ===')
