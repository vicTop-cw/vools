"""
测试 vools.serialize.backends.vb_json_backend 模块

验证 VB6 JSON.cls 移植的 JSON 解析器功能正确性。
"""

import json as std_json
import pytest
from vools.serialize import VBJsonBackend
from vools.serialize.backends import get_backend


class TestVBJsonBackend:
    """VB JSON 后端测试"""

    def setup_method(self):
        self.backend = VBJsonBackend()

    def test_parse_simple_object(self):
        """测试解析简单对象"""
        json_str = '{"name": "test", "value": 123}'
        result = self.backend.parse(json_str)
        assert result == {'name': 'test', 'value': 123}

    def test_parse_simple_array(self):
        """测试解析简单数组"""
        json_str = '[1, 2, 3, 4, 5]'
        result = self.backend.parse(json_str)
        assert result == [1, 2, 3, 4, 5]

    def test_parse_nested_object(self):
        """测试解析嵌套对象"""
        json_str = '{"outer": {"inner": {"value": 42}}}'
        result = self.backend.parse(json_str)
        assert result == {'outer': {'inner': {'value': 42}}}

    def test_parse_nested_array(self):
        """测试解析嵌套数组"""
        json_str = '[[1, 2], [3, 4], [5, 6]]'
        result = self.backend.parse(json_str)
        assert result == [[1, 2], [3, 4], [5, 6]]

    def test_parse_mixed_nested(self):
        """测试解析混合嵌套结构"""
        json_str = '{"data": [{"id": 1}, {"id": 2}], "count": 2}'
        result = self.backend.parse(json_str)
        assert result == {'data': [{'id': 1}, {'id': 2}], 'count': 2}

    def test_parse_boolean(self):
        """测试解析布尔值"""
        assert self.backend.parse('{"bool": true}') == {'bool': True}
        assert self.backend.parse('{"bool": false}') == {'bool': False}

    def test_parse_null(self):
        """测试解析 null"""
        result = self.backend.parse('{"value": null}')
        assert result['value'] is None

    def test_parse_numbers(self):
        """测试解析数字"""
        json_str = '{"int": 42, "float": 3.14, "negative": -10, "scientific": 1e10}'
        result = self.backend.parse(json_str)
        assert result['int'] == 42
        assert result['float'] == pytest.approx(3.14)
        assert result['negative'] == -10
        assert result['scientific'] == 1e10

    def test_parse_strings(self):
        """测试解析字符串"""
        json_str = '{"text": "hello world", "empty": ""}'
        result = self.backend.parse(json_str)
        assert result['text'] == 'hello world'
        assert result['empty'] == ''

    def test_parse_escaped_strings(self):
        """测试解析转义字符串"""
        json_str = '{"text": "hello\\nworld\\t!"}'
        result = self.backend.parse(json_str)
        assert result['text'] == 'hello\nworld\t!'

    def test_parse_unicode(self):
        """测试解析 Unicode"""
        json_str = '{"chinese": "中文", "unicode": "\\u4e2d\\u6587"}'
        result = self.backend.parse(json_str)
        assert result['chinese'] == '中文'
        assert result['unicode'] == '中文'

    def test_dumps_simple_object(self):
        """测试序列化简单对象"""
        obj = {'name': 'test', 'value': 123}
        result = self.backend.dumps_str(obj)
        parsed = std_json.loads(result)
        assert parsed == obj

    def test_dumps_simple_array(self):
        """测试序列化简单数组"""
        obj = [1, 2, 3, 4, 5]
        result = self.backend.dumps_str(obj)
        parsed = std_json.loads(result)
        assert parsed == obj

    def test_dumps_nested_object(self):
        """测试序列化嵌套对象"""
        obj = {'outer': {'inner': {'value': 42}}}
        result = self.backend.dumps_str(obj)
        parsed = std_json.loads(result)
        assert parsed == obj

    def test_dumps_nested_array(self):
        """测试序列化嵌套数组"""
        obj = [[1, 2], [3, 4], [5, 6]]
        result = self.backend.dumps_str(obj)
        parsed = std_json.loads(result)
        assert parsed == obj

    def test_dumps_mixed_nested(self):
        """测试序列化混合嵌套结构"""
        obj = {'data': [{'id': 1}, {'id': 2}], 'count': 2}
        result = self.backend.dumps_str(obj)
        parsed = std_json.loads(result)
        assert parsed == obj

    def test_dumps_boolean(self):
        """测试序列化布尔值"""
        obj = {'bool_true': True, 'bool_false': False}
        result = self.backend.dumps_str(obj)
        parsed = std_json.loads(result)
        assert parsed == obj

    def test_dumps_null(self):
        """测试序列化 None"""
        obj = {'value': None}
        result = self.backend.dumps_str(obj)
        parsed = std_json.loads(result)
        assert parsed == obj

    def test_dumps_numbers(self):
        """测试序列化数字"""
        obj = {'int': 42, 'float': 3.14, 'negative': -10}
        result = self.backend.dumps_str(obj)
        parsed = std_json.loads(result)
        assert parsed['int'] == 42
        assert parsed['float'] == pytest.approx(3.14)
        assert parsed['negative'] == -10

    def test_dumps_strings(self):
        """测试序列化字符串"""
        obj = {'text': 'hello world', 'empty': ''}
        result = self.backend.dumps_str(obj)
        parsed = std_json.loads(result)
        assert parsed == obj

    def test_dumps_unicode(self):
        """测试序列化 Unicode"""
        obj = {'chinese': '中文'}
        result = self.backend.dumps_str(obj)
        parsed = std_json.loads(result)
        assert parsed == obj

    def test_dumps_bytes(self):
        """测试 dumps 返回字节串"""
        obj = {'name': 'test'}
        result = self.backend.dumps(obj)
        assert isinstance(result, bytes)
        assert result.decode('utf-8') == self.backend.dumps_str(obj)

    def test_loads_bytes(self):
        """测试从字节串加载"""
        data = b'{"name": "test"}'
        result = self.backend.loads(data)
        assert result == {'name': 'test'}

    def test_roundtrip(self):
        """测试序列化和反序列化往返"""
        obj = {
            'string': 'hello',
            'int': 42,
            'float': 3.14,
            'bool': True,
            'null': None,
            'array': [1, 2, 3],
            'nested': {'key': 'value'}
        }
        dumped = self.backend.dumps(obj)
        loaded = self.backend.loads(dumped)
        assert loaded == obj

    def test_compatibility_with_std_json(self):
        """测试与标准库 JSON 的兼容性"""
        obj = {'name': 'test', 'value': [1, 2, 3], 'nested': {'key': 'value'}}
        vb_json_str = self.backend.dumps_str(obj)
        std_parsed = std_json.loads(vb_json_str)
        assert std_parsed == obj

        std_json_str = std_json.dumps(obj)
        vb_parsed = self.backend.parse(std_json_str)
        assert vb_parsed == obj

    def test_get_backend_vb_json(self):
        """测试通过 get_backend 获取 VB JSON 后端"""
        backend_class = get_backend('vb_json')
        assert backend_class == VBJsonBackend

    def test_backend_name(self):
        """测试后端名称"""
        assert self.backend.name == 'vb_json'


class TestVBJsonSpecialFeatures:
    """VB JSON 特殊特性测试（兼容 VB6 JSON.cls）"""

    def setup_method(self):
        self.backend = VBJsonBackend()

    def test_parse_single_quote_string(self):
        """测试解析单引号字符串（VB6 特性）"""
        json_str = "{'name': 'test'}"
        result = self.backend.parse(json_str)
        assert result == {'name': 'test'}

    def test_parse_comments(self):
        """测试解析注释（VB6 特性）"""
        json_str = '{/* comment */ "name": "test"}'
        result = self.backend.parse(json_str)
        assert result == {'name': 'test'}

    def test_parse_line_comment(self):
        """测试解析行注释（VB6 特性）"""
        json_str = '{// comment\n"name": "test"}'
        result = self.backend.parse(json_str)
        assert result == {'name': 'test'}

    def test_empty_input(self):
        """测试空输入"""
        result = self.backend.parse('')
        assert result is None
        assert len(self.backend.get_errors()) > 0

    def test_invalid_json(self):
        """测试无效 JSON"""
        result = self.backend.parse('invalid')
        assert result is None
        assert len(self.backend.get_errors()) > 0
