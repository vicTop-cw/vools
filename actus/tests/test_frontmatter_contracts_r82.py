"""frontmatter.py 契约测试（第 82 轮）——AIGC 前置区剥离 + 元数据解析。

覆盖：_looks_like_aigc_block 第 0 列判别（V-13/V-14 缩进嵌套不算）、
_split_frontmatter_blocks 前导空行/无闭合、strip_frontmatter 只剥 AIGC 块、
parse_action_metadata 双块拼回/解析失败/非 dict、PyYAML 缺失时
_simple_yaml_parse 降级全类型。

隔离：tmp 目录；yaml 替身用 monkeypatch 还原，不污染其它测试。
"""
import sys
import types

import pytest

import _ai_local_bootstrap  # noqa: F401

import vools.actus.frontmatter as fm
from vools.actus.frontmatter import (
    _looks_like_aigc_block, parse_action_metadata, strip_frontmatter,
)
from vools.actus.errors import ActionError


# ═══════════════════════════════════════════════════════════════════
# AIGC 块判别（第 0 列语义，V-13/V-14）
# ═══════════════════════════════════════════════════════════════════

class TestAigcBlockDetection:
    @pytest.mark.parametrize('marker', ['AIGC:', 'aigc:', 'generated-by:',
                                        'generated-by-at:'])
    def test_top_level_markers(self, marker):
        assert _looks_like_aigc_block(marker + ' x') is True

    def test_indented_nested_key_not_marker(self):
        # V-13：元数据块内 ai: 下的 generated-by: 是合法嵌套子键
        assert _looks_like_aigc_block(
            'id: a.b\nai:\n  generated-by: claude') is False

    def test_tab_indented_skipped(self):
        assert _looks_like_aigc_block('\tgenerated-by: x') is False

    def test_blank_lines_skipped(self):
        assert _looks_like_aigc_block('\n\ngenerated-by: x') is True

    def test_no_marker(self):
        assert _looks_like_aigc_block('id: a.b\nname: n') is False

    def test_empty(self):
        assert _looks_like_aigc_block('') is False


# ═══════════════════════════════════════════════════════════════════
# strip_frontmatter（只剥区域 0）
# ═══════════════════════════════════════════════════════════════════

class TestStripFrontmatter:
    def test_strips_aigc_keeps_meta(self):
        text = ('---\nAIGC: yes\ngenerated-by: claude\n---\n'
                '---\nid: a.b\nname: n\n---\nbody')
        out = strip_frontmatter(text)
        assert out.startswith('---\nid: a.b')      # 元数据块保留在前
        assert 'AIGC' not in out
        assert out.endswith('body')

    def test_single_meta_block_untouched(self):
        # 存量 bug 回归钉：无差别剥首块会丢唯一元数据
        text = '---\nid: a.b\nname: n\n---\nbody'
        assert strip_frontmatter(text) == text

    def test_no_frontmatter_leading_newlines_lstripped(self):
        assert strip_frontmatter('\n\nbody') == 'body'

    def test_no_frontmatter_plain(self):
        assert strip_frontmatter('body') == 'body'

    def test_unclosed_aigc_block_returned_as_is(self):
        text = '---\nAIGC: yes\n'          # 无闭合
        assert strip_frontmatter(text) == text

    def test_unclosed_after_first_block(self):
        # 首块闭合、第二块无闭合 → 只处理首块
        text = '---\nAIGC: x\n---\n---\nid: a.b\n'
        out = strip_frontmatter(text)
        assert 'id: a.b' in out and 'AIGC' not in out

    def test_meta_only_with_leading_blank(self):
        text = '\n\n---\nid: a.b\n---\nrest'
        out = strip_frontmatter(text)
        assert out.startswith('---\nid: a.b')


# ═══════════════════════════════════════════════════════════════════
# parse_action_metadata
# ═══════════════════════════════════════════════════════════════════

class TestParseActionMetadata:
    def test_happy_path(self):
        text = '---\nAIGC: yes\n---\n---\nid: a.b\nversion: 1.0.0\n---\n# run'
        meta, body = parse_action_metadata(text)
        assert meta['id'] == 'a.b' and meta['version'] == '1.0.0'
        assert body == '# run'

    def test_no_meta_block_passthrough(self):
        text = '---\nAIGC: yes\n---\nbody'
        meta, body = parse_action_metadata(text)
        assert meta == {} and body == text

    def test_plain_text_passthrough(self):
        meta, body = parse_action_metadata('no markers here')
        assert meta == {} and body == 'no markers here'

    def test_multiple_meta_blocks_rejoined(self):
        # 两个连续的前导元数据块：首个被解析，其余按原样拼回正文前部
        text = '---\nid: a.b\n---\n---\nextra: 1\n---\nTAIL'
        meta, body = parse_action_metadata(text)
        assert meta == {'id': 'a.b'}
        assert body.startswith('---\nextra: 1')
        assert body.endswith('TAIL')

    def test_mid_body_block_is_body_not_metadata(self):
        # 只有前导 front-matter 块参与判别；正文里的 '---' 是普通内容
        text = '---\nid: a.b\n---\nMIDDLE\n---\nextra: 1\n---\nTAIL'
        meta, body = parse_action_metadata(text)
        assert meta == {'id': 'a.b'}
        assert body == 'MIDDLE\n---\nextra: 1\n---\nTAIL'

    def test_yaml_error_raises_actionerror(self, monkeypatch):
        fake = types.ModuleType('yaml')
        def bad(_t):
            raise ValueError('bad yaml syntax')
        fake.safe_load = bad
        monkeypatch.setitem(sys.modules, 'yaml', fake)
        with pytest.raises(ActionError) as e:
            parse_action_metadata('---\nbad: [\n---\n')
        assert e.value.code == 'action_invalid'
        assert 'YAML 解析失败' in e.value.message

    def test_non_mapping_raises(self, monkeypatch):
        fake = types.ModuleType('yaml')
        fake.safe_load = lambda _t: ['not', 'a', 'dict']
        monkeypatch.setitem(sys.modules, 'yaml', fake)
        with pytest.raises(ActionError) as e:
            parse_action_metadata('---\nx: 1\n---\n')
        assert 'YAML mapping' in e.value.message

    def test_yaml_import_error_falls_back(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'yaml', None)   # None → ImportError
        meta, body = parse_action_metadata(
            '---\nid: a.b\ncount: 3\nratio: 1.5\n---\nBODY')
        assert meta == {'id': 'a.b', 'count': 3, 'ratio': 1.5}
        assert body == 'BODY'


# ═══════════════════════════════════════════════════════════════════
# _simple_yaml_parse（降级解析全类型）
# ═══════════════════════════════════════════════════════════════════

class TestSimpleYamlParse:
    def _parse(self, text, monkeypatch):
        monkeypatch.setitem(sys.modules, 'yaml', None)
        meta, _ = parse_action_metadata('---\n' + text + '\n---\n')
        return meta

    def test_full_type_matrix(self, monkeypatch):
        meta = self._parse(
            's: hello\n'
            'i: 42\n'
            'f: 3.14\n'
            't1: true\n'
            't2: yes\n'
            'f1: false\n'
            'f2: no\n'
            'n1: null\n'
            'n2: ~\n'
            'empty:\n'
            "qs: 'quoted'\n"
            'qd: "double"\n'
            'lst: [a, b, c]\n'
            'lst_quoted: [x ,  y]\n'
            'empty_lst: []', monkeypatch)
        assert meta['s'] == 'hello'
        assert meta['i'] == 42 and isinstance(meta['i'], int)
        assert meta['f'] == 3.14
        assert meta['t1'] is True and meta['t2'] is True
        assert meta['f1'] is False and meta['f2'] is False
        assert meta['n1'] is None and meta['n2'] is None
        assert meta['empty'] is None
        assert meta['qs'] == 'quoted' and meta['qd'] == 'double'
        assert meta['lst'] == ['a', 'b', 'c']
        assert meta['lst_quoted'] == ['x', 'y']
        assert meta['empty_lst'] == []

    def test_comments_and_blank_skipped(self, monkeypatch):
        meta = self._parse('# comment\n\nkey: 1\n# another', monkeypatch)
        assert meta == {'key': 1}

    def test_colonless_line_skipped(self, monkeypatch):
        meta = self._parse('just text\nkey: 1', monkeypatch)
        assert meta == {'key': 1}

    def test_unparseable_number_stays_string(self, monkeypatch):
        meta = self._parse('v: abc123', monkeypatch)
        assert meta['v'] == 'abc123'
