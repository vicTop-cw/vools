# -*- coding: utf-8 -*-
"""回归测试：SQL 装饰器的 Optional / 泛型注解处理（BUG-352）。

`@sql_function` 依据返回值注解把 `ResultSet` 转成 Python 值。原实现只认
`list`/`dict`/`Row`/标量等**具体类型**：

    @sql_function(...)
    def get_name() -> Optional[str]: ...   # 实际返回 ResultSet（未转换）

因为 `Optional[X]` 的 `__origin__` 是 `typing.Union`，所有具体分支都匹配不上，
而 `Optional` 恰好是**可空列**最常用的写法。参数侧同理：
`Optional[int]` 被推断成 `VARCHAR`；`List[int]`/`Dict[...]` 也落到 `VARCHAR`
（`PY_TO_SQL` 明明声明 list/dict → JSON）。

修复：
- `_unwrap_optional`：`Optional[X]`/`Union[X, None]` → `X`，用于返回值转换与类型推断；
- `_resolve_sql_types`：泛型按 `__origin__` 映射（list/dict → JSON）；
- `SqlTypeMapper.infer_ret_type`：同样解包 Optional、按 origin 映射泛型。
"""

import typing

import pytest

from vools.sql.core.decorators import _convert_result, _resolve_sql_types
from vools.sql.core.result import ResultSet, Row
from vools.sql.core.types import SqlTypeMapper

RS = ResultSet(['id', 'name'], [(1, 'a'), (2, 'b')])
EMPTY = ResultSet(['id'], [])


class TestOptionalReturnConversion:
    @pytest.mark.parametrize('annotation,expected_type', [
        (typing.Optional[int], int),
        (typing.Optional[str], int),        # 标量分支（convert_result 为占位空实现）
        (typing.Union[int, None], int),
        (typing.Optional[list], list),
        (typing.Optional[dict], dict),
        (typing.Optional[Row], Row),
    ])
    def test_optional_converted(self, annotation, expected_type):
        # 修复前：全部原样返回 ResultSet
        assert type(_convert_result(RS, annotation)) is expected_type

    def test_optional_int_empty_uses_rowcount(self):
        assert _convert_result(EMPTY, typing.Optional[int]) == 0

    def test_optional_list_content(self):
        assert _convert_result(RS, typing.Optional[list]) == [
            {'id': 1, 'name': 'a'}, {'id': 2, 'name': 'b'}]

    def test_optional_dict_content(self):
        assert _convert_result(RS, typing.Optional[dict]) == {'id': 1, 'name': 'a'}


class TestPlainAnnotationsUnchanged:
    @pytest.mark.parametrize('annotation,expected_type', [
        (list, list),
        (typing.List[int], list),
        (dict, dict),
        (typing.Dict[str, int], dict),
        (Row, Row),
        (int, int),
    ])
    def test_plain(self, annotation, expected_type):
        assert type(_convert_result(RS, annotation)) is expected_type

    def test_none_annotation_returns_raw(self):
        assert isinstance(_convert_result(RS, None), ResultSet)


class TestSqlTypeInference:
    def test_optional_param_type(self):
        # 修复前：('VARCHAR', ...)
        assert _resolve_sql_types([typing.Optional[int]], None)[0] == ['INTEGER']

    @pytest.mark.parametrize('annotation', [typing.List[int], typing.Dict[str, int]])
    def test_generic_param_type(self, annotation):
        # 修复前：VARCHAR
        assert _resolve_sql_types([annotation], None)[0] == ['JSON']

    def test_plain_param_type(self):
        assert _resolve_sql_types([int, str, None], None)[0] == ['INTEGER', 'VARCHAR', None]

    @pytest.mark.parametrize('annotation,expected', [
        (typing.List[int], 'JSON'),
        (typing.Dict[str, int], 'JSON'),
        (typing.Optional[int], 'INTEGER'),
        (int, 'INTEGER'),
        (str, 'VARCHAR'),
        (None, None),
    ])
    def test_infer_ret_type(self, annotation, expected):
        assert SqlTypeMapper.infer_ret_type(annotation) == expected