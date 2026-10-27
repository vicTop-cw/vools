"""
VB JSON 序列化后端

基于 VB6 JSON.cls 的 Python 移植实现，提供兼容的 JSON 解析和序列化功能。
"""

from typing import Any, Dict, List, Optional, Union
import enum
import re

from .base import BaseBackend

__all__ = ['VBJsonBackend']


def _apply_object_hook(obj: Any) -> Any:
    """BUG-309: 递归应用 codec.vools_object_hook（bottom-up）。

    与 json 后端 object_hook 的调用顺序一致：先处理内层 dict，再处理外层，
    使 {"__vools_type__": ...} / {"__vools_singleton__": ...} 等标记可还原。
    非 dict/list 原样返回，解析失败时保持原始结构（不新增崩溃面）。
    """
    from ..codec import vools_object_hook
    if isinstance(obj, dict):
        return vools_object_hook({k: _apply_object_hook(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_apply_object_hook(v) for v in obj]
    return obj


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
        # BUG-408: 同 JsonBackend——非字符串键会被静默转成字符串，这里告警。
        try:
            from ._keycheck import find_non_str_keys
            _bad, _truncated = find_non_str_keys(obj)
            if _bad:
                import warnings as _w
                _w.warn(
                    f"VBJsonBackend: 载荷含非字符串映射键 {_bad!r}"
                    f"{' 等' if _truncated else ''}——JSON 只能表示字符串键，"
                    f"这些键在反序列化后会变成字符串（键类型改变）。",
                    RuntimeWarning, stacklevel=2)
        except Exception:
            pass
        return self.dumps_str(obj).encode('utf-8')

    def loads(self, data: bytes) -> Any:
        """
        从 JSON 字节串反序列化

        Args:
            data: JSON 格式的字节串

        Returns:
            反序列化后的对象
        """
        data = self._require_bytes(data, "VBJsonBackend.loads")
        # BUG-309: 与 json 后端对齐——解析结果递归应用 vools_object_hook，
        # 使 register_type 注册类型与内置类型（datetime/set/NONE 哨兵等）可还原。
        return _apply_object_hook(self.parse(data.decode('utf-8')))

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
            # BUG-203：顶层标量（数字/字符串/bool/null）必须分派到 _parse_value，
            # 否则 dumps(1.5) -> loads 会得到 None，标量数据丢失。
            return self._parse_value(json_str, index)

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
            
            # BUG-185 兜底：子解析器未推进 index[0] 会让 while True 挂死。
            before = index[0]
            value = self._parse_value(json_str, index)
            if index[0] == before:
                if index[0] < len(json_str):
                    index[0] += 1
                self._errors.append("Invalid value at position {}".format(index[0]))
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
            
            # BUG-185 兜底：任何子解析器未推进 index[0] 都会让 while True 挂死。
            before = index[0]
            value = self._parse_value(json_str, index)
            if index[0] == before:
                if index[0] < len(json_str):
                    index[0] += 1
                self._errors.append("Invalid value at position {}".format(index[0]))
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
            # 合法的数字起始字符，或 Infinity / NaN 字面量起始（I/N），才交给
            # _parse_number；非法起始字符（如 'invalid' 的小写 'i'）返回 None 并
            # 推进 index[0]，避免内层 while 挂死（BUG-185 同类）。
            if char in '+-.0123456789' or char in 'IN':
                return self._parse_number(json_str, index)
            self._errors.append("Invalid value at position {}".format(index[0]))
            if index[0] < len(json_str):
                index[0] += 1
            return None

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

        # BUG-203：识别标准 JSON 非有限浮点字面量（Infinity / -Infinity / NaN），
        # 否则 _stringify 的 Infinity 会被 int() 吞成 0 / None，数据失真。
        for _lit, _val in (('Infinity', float('inf')),
                           ('-Infinity', float('-inf')),
                           ('NaN', float('nan'))):
            if json_str[index[0]:index[0]+len(_lit)] == _lit:
                index[0] += len(_lit)
                return _val

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
            # BUG-185: 空收集时不推进 index[0] 会让 _parse_array 的
            # while True 原地重进同一字符 → 无限循环挂死。
            if index[0] < len(json_str):
                index[0] += 1
            self._errors.append("Invalid Number at position {}".format(index[0]))
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
        # BUG-185: 失败必须推进 index[0]，否则 _parse_array 无限循环。
        if index[0] < len(json_str):
            index[0] += 1
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
        # BUG-185: 失败必须推进 index[0]，否则 _parse_array 无限循环。
        if index[0] < len(json_str):
            index[0] += 1
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

    def _stringify(self, obj: Any, _path_ids=None) -> str:  # noqa: C901 - BUG-344 增加环检测入参
        """
        将对象序列化为 JSON 字符串

        Args:
            obj: 要序列化的对象

        Returns:
            JSON 字符串
        """
        # BUG-344: 循环引用检测——自引用容器此前一路递归到
        # RecursionError: maximum recursion depth exceeded（错误信息指不到"数据里有环"）。
        if _path_ids is None:
            _path_ids = set()
        if obj is None:
            return 'null'
        
        if isinstance(obj, bool):
            return 'true' if obj else 'false'
        
        # BUG-310B: enum.Enum 检查必须在 int/float 分支之前——
        # IntEnum/IntFlag 是 int 子类，若走 int 分支会被静默降级为普通 int
        # （值对、类型丢，后续 is/成员方法/isinstance 判断全部失效）。
        # 先走 vools_preprocess 标记化，确保枚举类型不丢失。
        if isinstance(obj, enum.Enum):
            try:
                from ..codec import vools_preprocess
                _pre = vools_preprocess(obj)
                if _pre is not obj:
                    return self._stringify(_pre)
            except Exception:
                pass
            # vools_preprocess 未处理（未注册），走 __vools_obj__ 标记
            try:
                from ..codec import vools_default
                _dflt = vools_default(obj)
                if isinstance(_dflt, dict) and '__vools_obj__' in _dflt:
                    return self._stringify(_dflt)
            except Exception:
                pass
        
        if isinstance(obj, (int, float)):
            # BUG-203：非有限浮点必须输出标准 JSON 字面量（与 json.dumps 的
            # Infinity / NaN 对齐），否则 loads 端会得到 0 / None，数据失真。
            if isinstance(obj, float):
                if obj != obj:
                    return 'NaN'
                if obj == float('inf'):
                    return 'Infinity'
                if obj == float('-inf'):
                    return '-Infinity'
            return str(obj).replace(',', '.')
        
        if isinstance(obj, str):
            return '"{}"'.format(self._encode_string(obj))
        
        if isinstance(obj, dict):
            _oid = id(obj)
            if _oid in _path_ids:
                raise ValueError(
                    "vools.serialize: 输入包含循环引用（字典自引用），"
                    "vb_json 后端无法表示循环结构。"
                    "请先断开环，或改用 pickle 后端。")
            _path_ids.add(_oid)
            try:
                items = []
                for key, value in obj.items():
                    key_str = '"{}"'.format(self._encode_string(str(key)))
                    value_str = self._stringify(value, _path_ids)
                    items.append('{}:{}'.format(key_str, value_str))
                return '{' + ','.join(items) + '}'
            finally:
                _path_ids.discard(_oid)

        if isinstance(obj, (list, tuple)):
            _oid = id(obj)
            if _oid in _path_ids:
                raise ValueError(
                    "vools.serialize: 输入包含循环引用（列表/元组自引用），"
                    "vb_json 后端无法表示循环结构。"
                    "请先断开环，或改用 pickle 后端。")
            _path_ids.add(_oid)
            try:
                items = [self._stringify(item, _path_ids) for item in obj]
                return '[' + ','.join(items) + ']'
            finally:
                _path_ids.discard(_oid)
        
        # BUG-309: 未知类型先尝试类型注册表（register_type 自定义类型、
        # 内置 datetime/set/Decimal 等）——与 json 后端 _json_default 同源。
        # vools_preprocess 对未注册对象原样返回（is 判断），此时才报错。
        try:
            from ..codec import vools_preprocess
            _pre = vools_preprocess(obj)
        except Exception:
            _pre = obj
        if _pre is not obj:
            return self._stringify(_pre)
        # 单例哨兵（NONE 等）由 vools_default 产出 __vools_singleton__ 标记。
        # 只接受**可还原**的标记（__vools_singleton__ / __vools_type__）；
        # 通用 __vools_obj__ 依赖 _import_class 白名单，可能还原不回来，
        # 宁可抛 TypeError（保持 BUG-303 的显式报错，不静默丢数据）。
        try:
            from ..codec import vools_default
            _dflt = vools_default(obj)
        except Exception:
            _dflt = obj
        if isinstance(_dflt, dict) and (
                _dflt.get('__vools_singleton__') or _dflt.get('__vools_type__')):
            return self._stringify(_dflt)

        # BUG-303: 未知类型原实现静默 `return 'null'` —— dumps 成功但 loads
        # 得到 None（数据无声丢失，嵌套字段变 null）。改为显式 TypeError，
        # 与同库 json 后端口径一致（不吞数据）。
        raise TypeError(
            f"Object of type {type(obj).__name__} is not serializable by "
            f"VBJsonBackend（vb_json 支持 str/int/float/bool/None/dict/list/tuple；"
            f"请改用 pickle 后端或先转换为受支持类型）"
        )
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
