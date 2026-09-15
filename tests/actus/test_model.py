"""tests/actus/test_model.py — actus 数据模型测试"""
import pytest
import tempfile
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus.model import Action, parse_cfg, parse_cfg_from_file
from vools.actus.errors import ActionError


class TestAction:
    """Action 数据类测试"""

    def _make_action(self, meta=None, **kwargs):
        meta = meta or {
            'id': 'test.hello',
            'name': 'Hello',
            'trust': 'trusted',
            'entry': 'main',
        }
        return Action(
            meta=meta,
            path='actions/test.hello.actus.md',
            sha256='abc123',
            raw='# Hello\n```python\nprint("hi")\n```',
            body='# Hello\n```python\nprint("hi")\n```',
            **kwargs,
        )

    def test_basic_properties(self):
        a = self._make_action()
        assert a.id == 'test.hello'
        assert a.trust == 'trusted'
        assert a.entry == 'main'
        assert a.meta['name'] == 'Hello'

    def test_optional_defaults(self):
        a = self._make_action()
        assert a.blocks == []
        assert a.file_directives == {}
        assert a.args_schema is None
        assert a.max_instances == 0
        assert a.tags == []
        assert a.deps == []

    def test_brief(self):
        a = self._make_action()
        brief = a.brief()
        assert brief['id'] == 'test.hello'
        assert brief['trust'] == 'trusted'
        assert 'path' in brief
        assert 'sha256' in brief

    def test_custom_meta(self):
        meta = {
            'id': 'test.custom',
            'name': 'Custom',
            'trust': 'sandbox',
            'entry': 'run',
            'args': {'type': 'object'},
            'max_instances': 3,
            'tags': ['demo', 'test'],
            'deps': ['python:requests'],
        }
        a = self._make_action(meta=meta)
        assert a.trust == 'sandbox'
        assert a.max_instances == 3
        assert a.tags == ['demo', 'test']
        assert a.deps == ['python:requests']
        assert a.args_schema == {'type': 'object'}


class TestParseCfg:
    """parse_cfg 元数据解析测试"""

    def test_valid_cfg_block(self):
        body = '''# Test Action

```json #!cfg
{
    "id": "test.parse",
    "name": "Parse Test",
    "trust": "trusted",
    "entry": "main"
}
```

Some description here.
'''
        meta = parse_cfg(body)
        assert meta['id'] == 'test.parse'
        assert meta['trust'] == 'trusted'

    def test_missing_cfg_block(self):
        body = '# Just a heading\n\nNo cfg block here.'
        with pytest.raises(ActionError):
            parse_cfg(body)

    def test_invalid_json(self):
        body = '''```json #!cfg
{invalid json}
```'''
        with pytest.raises(ActionError):
            parse_cfg(body)

    def test_wrong_language(self):
        body = '''```python #!cfg
{"id": "test"}
```'''
        with pytest.raises(ActionError):
            parse_cfg(body)

    def test_not_dict(self):
        body = '''```json #!cfg
["not", "a", "dict"]
```'''
        with pytest.raises(ActionError):
            parse_cfg(body)


class TestParseCfgFromFile:
    """parse_cfg_from_file 文件解析测试"""

    def test_from_temp_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''# Test

```json #!cfg
{
    "id": "test.file",
    "name": "File Test",
    "trust": "trusted",
    "entry": "main"
}
```
''')
            f.flush()
            action = parse_cfg_from_file(f.name)
            assert action.id == 'test.file'
            assert action.meta['name'] == 'File Test'
        os.unlink(f.name)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_cfg_from_file('/nonexistent/path/action.actus.md')
