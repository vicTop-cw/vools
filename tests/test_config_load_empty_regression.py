# -*- coding: utf-8 -*-
"""回归测试：配置加载对「空配置」不再抛内部 TypeError（BUG-316）。

`ConfigManager.load_from_file` 用 YAML 读配置。**空文件 / 仅注释 / "null"
字面量** 解析结果为 `None`，原实现直接 `'database' in config_data`，抛：

    TypeError: argument of type 'NoneType' is not iterable

错误信息完全指不到真因（配置文件为空），属内部错误掩盖真实原因。

修复：None 视为空配置（no-op）；非映射顶层（list/标量）给出清晰 ValueError。
"""

import pytest

from vools.core.config import ConfigManager


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding='utf-8')
    return str(p)


class TestEmptyConfigNoOp:
    @pytest.mark.parametrize('content', ['', '   \n\n', '# only comment\n',
                                         '# a\n# b\n', 'null\n', '~\n', '{}\n'])
    def test_no_crash_and_defaults_kept(self, tmp_path, content):
        cm = ConfigManager()
        before = (cm.app.environment, cm.database.port, cm.cache.duration)
        cm.load_from_file(_write(tmp_path, 'c.yaml', content))
        after = (cm.app.environment, cm.database.port, cm.cache.duration)
        assert after == before


class TestNonMappingTopLevel:
    @pytest.mark.parametrize('content', ['- a\n- b\n', '42\n', 'hello\n'])
    def test_clear_value_error(self, tmp_path, content):
        cm = ConfigManager()
        with pytest.raises(ValueError, match='映射'):
            cm.load_from_file(_write(tmp_path, 'c.yaml', content))


class TestValidConfigStillWorks:
    def test_partial_override(self, tmp_path):
        cm = ConfigManager()
        cm.load_from_file(_write(
            tmp_path, 'c.yaml',
            '{"app": {"debug": true}, "database": {"host": "h1"}}'))
        assert cm.app.debug is True
        assert cm.database.host == 'h1'
        # 未提供的键保持默认
        assert cm.app.environment == 'development'
        assert cm.database.port == 5432

    def test_full_config(self, tmp_path):
        cm = ConfigManager()
        cm.load_from_file(_write(tmp_path, 'c.yaml', (
            'app: {environment: prod, debug: false, log_level: WARN}\n'
            'cache: {duration: 60, max_size: 10, enabled: false}\n'
            'database: {host: db, port: 5433, user: u, password: p, database: d}\n'
        )))
        assert cm.app.environment == 'prod'
        assert cm.cache.duration == 60
        assert cm.database.port == 5433

    def test_unknown_keys_ignored(self, tmp_path):
        cm = ConfigManager()
        cm.load_from_file(_write(
            tmp_path, 'c.yaml', '{"bogus": {"x": 1}, "app": {"debug": true}}'))
        assert cm.app.debug is True

    def test_missing_file_still_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ConfigManager().load_from_file(str(tmp_path / 'nope.yaml'))