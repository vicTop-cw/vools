"""
VB JSON 序列化后端

基于 VB6 JSON.cls 的 Python 移植实现，提供兼容的 JSON 解析和序列化功能。
"""

from typing import Any, Dict, List, Optional, Union
import re

from .base import BaseBackend

__all__ = ['VBJsonBackend']


class VBJsonBackend(BaseBackend):
    """
    基于 VB6 JSON.cls 的 JSON 序列化后端

    提供与 VB6 JSON.cls 兼容的 JSON 解析和序列化功能，
    支持注释忽略、单引号字符串等 VB6 特性。
    """

    name = "vb_json"

    def __init__(self):
        self._errors = []

    def dumps(self, obj: Any) -> bytes:
        """
        序列化为 JSON 字节串

        Args:
            obj: 要序列化的对象

        Returns:
            JSON 格式的字节串
        """
        return self.dumps_str(obj).encode('utf-8')

    def loads(self, data: bytes) -> Any:
        """
        从 JSON 字节串反序列化

        Args:
            data: JSON 格式的字节串

        Returns:
            反序列化后的对象
        """
        return self.parse(data.decode('utf-8'))

    def dumps_str(self, obj: Any) -> str:
        """
        序列化为 JSON 字符串

        Args:
            obj: 要序列化的对象

        Returns:
            JSON 格式的字符串
        """
        return self._stringify(obj)

    def parse(self, json_str: str) -> Any:
        """
        解析 JSON 字符串

        Args:
            json_str: JSON 字符串

        Returns:
            解析后的 Python 对象
        """
        self._errors = []
        index = [0]
        self._skip_char(json_str, index)
        
        if index[0] >= len(json_str):
            self._errors.append("Invalid JSON: empty string")
            return None
        
        char = json_str[index[0]]
        if char == '{':
            return self._parse_object(json_str, index)
        elif char == '[':
            return self._parse_array(json_str, index)
        else:
            self._errors.append("Invalid JSON: must start with '{' or '['")
            return None

    def get_errors(self) -> List[str]:
        """
        获取解析错误信息

        Returns:
            错误信息列表
        """
        return self._errors.copy()

    def _skip_char(self, json_str: str, index: List[int]) -> None:
        """
        跳过空白字符和注释

        Args:
            json_str: JSON 字符串
            index: 当前位置列表（用于传递引用）
        """
        b_comment = False
        b_start_comment = False
        b_long_comment = False
        
        while index[0] >= 0 and index[0] < len(json_str):
            char = json_str[index[0]]
            
            if char in '\r\n':
                if not b_long_comment:
                    b_start_comment = False
                    b_comment = False
            elif char in '\t (':
                pass
            elif char == '/':
                if not b_long_comment:
                    if b_start_comment:
                        b_start_comment = False
                        b_comment = True
                    else:
                        b_start_comment = True
                        b_comment = False
                        b_long_comment = False
                else:
                    if b_start_comment:
                        b_long_comment = False
                        b_start_comment = False
                        b_comment = False
            elif char == '*':
                if b_start_comment:
                    b_start_comment = False
                    b_comment = True
                    b_long_comment = True
                else:
                    b_start_comment = True
            else:
                if not b_comment:
                    break
            
            index[0] += 1

    def _parse_object(self, json_str: str, index: List[int]) -> Dict[str, Any]:
        """
        解析 JSON 对象

        Args:
            json_str: JSON 字符串
            index: 当前位置列表

        Returns:
            解析后的字典
        """
        result = {}
        self._skip_char(json_str, index)
        
        if index[0] >= len(json_str) or json_str[index[0]] != '{':
            self._errors.append("Invalid Object at position {}".format(index[0]))
            return result
        
        index[0] += 1
        
        while True:
            self._skip_char(json_str, index)
            
            if index[0] >= len(json_str):
                self._errors.append("Missing '}'")
                break
            
            char = json_str[index[0]]
            
            if char == '}':
                index[0] += 1
                break
            elif char == ',':
                index[0] += 1
                continue
            
            key = self._parse_key(json_str, index)
            if not key:
                break
            
            value = self._parse_value(json_str, index)
            result[key] = value
        
        return result

    def _parse_array(self, json_str: str, index: List[int]) -> List[Any]:
        """
        解析 JSON 数组

        Args:
            json_str: JSON 字符串
            index: 当前位置列表

        Returns:
            解析后的列表
        """
        result = []
        self._skip_char(json_str, index)
        
        if index[0] >= len(json_str) or json_str[index[0]] != '[':
            self._errors.append("Invalid Array at position {}".format(index[0]))
            return result
        
        index[0] += 1
        
        while True:
            self._skip_char(json_str, index)
            
            if index[0] >= len(json_str):
                self._errors.append("Missing ']'")
                break
            
            char = json_str[index[0]]
            
            if char == ']':
                index[0] += 1
                break
            elif char == ',':
                index[0] += 1
                continue
            
            value = self._parse_value(json_str, index)
            result.append(value)
        
        return result

    def _parse_value(self, json_str: str, index: List[int]) -> Any:
        """
        解析 JSON 值

        Args:
            json_str: JSON 字符串
            index: 当前位置列表

        Returns:
            解析后的值
        """
        self._skip_char(json_str, index)
        
        if index[0] >= len(json_str):
            return None
        
        char = json_str[index[0]]
        
        if char == '{':
            return self._parse_object(json_str, index)
        elif char == '[':
            return self._parse_array(json_str, index)
        elif char in ('"', "'"):
            return self._parse_string(json_str, index)
        elif char == 't':
            return self._parse_boolean(json_str, index)
        elif char == 'f':
            return self._parse_boolean(json_str, index)
        elif char == 'n':
            return self._parse_null(json_str, index)
        else:
            return self._parse_number(json_str, index)

    def _parse_string(self, json_str: str, index: List[int]) -> str:
        """
        解析 JSON 字符串

        Args:
            json_str: JSON 字符串
            index: 当前位置列表

        Returns:
            解析后的字符串
        """
        self._skip_char(json_str, index)
        
        if index[0] >= len(json_str):
            return ""
        
        quote = json_str[index[0]]
        index[0] += 1
        
        result = []
        
        while index[0] >= 0 and index[0] < len(json_str):
            char = json_str[index[0]]
            
            if char == '\\':
                index[0] += 1
                if index[0] >= len(json_str):
                    break
                char = json_str[index[0]]
                if char in ('"', "'", '\\', '/'):
                    result.append(char)
                elif char == 'b':
                    result.append('\b')
                elif char == 'f':
                    result.append('\f')
                elif char == 'n':
                    result.append('\n')
                elif char == 'r':
                    result.append('\r')
                elif char == 't':
                    result.append('\t')
                elif char == 'u':
                    index[0] += 1
                    if index[0] + 3 < len(json_str):
                        code = json_str[index[0]:index[0]+4]
                        result.append(chr(int(code, 16)))
                        index[0] += 4
                        continue
                index[0] += 1
            elif char == quote:
                index[0] += 1
                break
            else:
                result.append(char)
                index[0] += 1
        
        return ''.join(result)

    def _parse_number(self, json_str: str, index: List[int]) -> Union[int, float]:
        """
        解析 JSON 数字

        Args:
            json_str: JSON 字符串
            index: 当前位置列表

        Returns:
            解析后的数字（int 或 float）
        """
        self._skip_char(json_str, index)
        
        value = []
        while index[0] >= 0 and index[0] < len(json_str):
            char = json_str[index[0]]
            if char in '+-0123456789.eE':
                value.append(char)
                index[0] += 1
            else:
                break
        
        num_str = ''.join(value)
        if not num_str:
            return 0
        
        try:
            if '.' in num_str or 'e' in num_str.lower():
                return float(num_str)
            return int(num_str)
        except ValueError:
            return 0

    def _parse_boolean(self, json_str: str, index: List[int]) -> bool:
        """
        解析 JSON 布尔值

        Args:
            json_str: JSON 字符串
            index: 当前位置列表

        Returns:
            解析后的布尔值
        """
        self._skip_char(json_str, index)
        
        if index[0] + 3 < len(json_str) and json_str[index[0]:index[0]+4] == 'true':
            index[0] += 4
            return True
        elif index[0] + 4 < len(json_str) and json_str[index[0]:index[0]+5] == 'false':
            index[0] += 5
            return False
        
        self._errors.append("Invalid Boolean at position {}".format(index[0]))
        return False

    def _parse_null(self, json_str: str, index: List[int]) -> None:
        """
        解析 JSON null

        Args:
            json_str: JSON 字符串
            index: 当前位置列表

        Returns:
            None
        """
        self._skip_char(json_str, index)
        
        if index[0] + 3 < len(json_str) and json_str[index[0]:index[0]+4] == 'null':
            index[0] += 4
            return None
        
        self._errors.append("Invalid null value at position {}".format(index[0]))
        return None

    def _parse_key(self, json_str: str, index: List[int]) -> str:
        """
        解析 JSON 对象的键

        Args:
            json_str: JSON 字符串
            index: 当前位置列表

        Returns:
            解析后的键
        """
        self._skip_char(json_str, index)
        
        if index[0] >= len(json_str):
            return ""
        
        char = json_str[index[0]]
        
        if char in ('"', "'"):
            result = self._parse_string(json_str, index)
            self._skip_char(json_str, index)
            if index[0] < len(json_str) and json_str[index[0]] == ':':
                index[0] += 1
            return result
        
        result = []
        while index[0] >= 0 and index[0] < len(json_str):
            char = json_str[index[0]]
            if char == ':':
                index[0] += 1
                break
            elif char in '\r\n\t ':
                index[0] += 1
                continue
            else:
                result.append(char)
                index[0] += 1
        
        return ''.join(result)

    def _stringify(self, obj: Any) -> str:
        """
        将对象序列化为 JSON 字符串

        Args:
            obj: 要序列化的对象

        Returns:
            JSON 字符串
        """
        if obj is None:
            return 'null'
        
        if isinstance(obj, bool):
            return 'true' if obj else 'false'
        
        if isinstance(obj, (int, float)):
            return str(obj).replace(',', '.')
        
        if isinstance(obj, str):
            return '"{}"'.format(self._encode_string(obj))
        
        if isinstance(obj, dict):
            items = []
            for key, value in obj.items():
                key_str = '"{}"'.format(self._encode_string(str(key)))
                value_str = self._stringify(value)
                items.append('{}:{}'.format(key_str, value_str))
            return '{' + ','.join(items) + '}'
        
        if isinstance(obj, (list, tuple)):
            items = [self._stringify(item) for item in obj]
            return '[' + ','.join(items) + ']'
        
        return 'null'

    def _encode_string(self, s: str) -> str:
        """
        编码字符串，处理转义字符

        Args:
            s: 原始字符串

        Returns:
            编码后的字符串
        """
        result = []
        for char in s:
            code = ord(char)
            if code == 34:
                result.append('\\"')
            elif code == 92:
                result.append('\\\\')
            elif code == 47:
                result.append('\\/')
            elif code == 8:
                result.append('\\b')
            elif code == 12:
                result.append('\\f')
            elif code == 10:
                result.append('\\n')
            elif code == 13:
                result.append('\\r')
            elif code == 9:
                result.append('\\t')
            elif code < 32 or code > 127:
                result.append('\\u{:04x}'.format(code))
            else:
                result.append(char)
        return ''.join(result)
