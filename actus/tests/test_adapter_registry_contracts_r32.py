"""adapter AdapterRegistry 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- discover 解析错误 → 适配器丢失或配置错被静默丢弃
- get 找不到 → 报"适配器不存在"而不是"配置错"
- create_adapter 不校验 → 缺 command/url 的 spec 被实例化
"""
import json

import pytest


@pytest.fixture
def tmp_adapters_dir(tmp_path, monkeypatch):
    """隔离：adapters_dir 指向 tmp。"""
    d = tmp_path / "adapters"
    d.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    return str(d)


def _write_adapter(d, adapter_id, cfg):
    """写一个 .actus.md 适配器文件。"""
    content = "```json #!cfg\n" + json.dumps(cfg, ensure_ascii=False) + "\n```\n"
    (d / f"{adapter_id}.actus.md").write_text(content, encoding="utf-8")


class TestDiscover:
    def test_empty_dir(self, tmp_adapters_dir):
        """退步了会怎样：空目录应返回空列表。"""
        from vools.actus.adapter import AdapterRegistry
        ar = AdapterRegistry(adapters_dir=tmp_adapters_dir)
        assert ar.discover() == []

    def test_nonexistent_dir(self, tmp_adapters_dir):
        """退步了会怎样：目录不存在应返回空列表。"""
        from vools.actus.adapter import AdapterRegistry
        ar = AdapterRegistry(adapters_dir="/tmp/nonexistent_adapters")
        assert ar.discover() == []

    def test_valid_adapter(self, tmp_adapters_dir):
        """退步了会怎样：合法适配器应被解析。"""
        from pathlib import Path
        from vools.actus.adapter import AdapterRegistry
        d = Path(tmp_adapters_dir)
        _write_adapter(d, "act.a", {
            "id": "act.a", "name": "Test", "adapter": {"type": "cli", "command": "python"},
        })
        ar = AdapterRegistry(adapters_dir=tmp_adapters_dir)
        specs = ar.discover()
        assert len(specs) == 1
        assert specs[0].id == "act.a"
        assert specs[0].command == "python"

    def test_bad_json_skipped(self, tmp_adapters_dir):
        """退步了会怎样：坏 JSON 应跳过（记 warning），不影响其他。"""
        from pathlib import Path
        from vools.actus.adapter import AdapterRegistry
        d = Path(tmp_adapters_dir)
        (d / "bad.actus.md").write_text("not valid content", encoding="utf-8")
        _write_adapter(d, "act.a", {
            "id": "act.a", "adapter": {"type": "cli", "command": "python"},
        })
        ar = AdapterRegistry(adapters_dir=tmp_adapters_dir)
        specs = ar.discover()
        assert len(specs) == 1
        assert specs[0].id == "act.a"


class TestGet:
    def test_get_existing(self, tmp_adapters_dir):
        """退步了会怎样：get 已发现的适配器应返回 spec。"""
        from pathlib import Path
        from vools.actus.adapter import AdapterRegistry
        d = Path(tmp_adapters_dir)
        _write_adapter(d, "act.a", {
            "id": "act.a", "adapter": {"type": "cli", "command": "python"},
        })
        ar = AdapterRegistry(adapters_dir=tmp_adapters_dir)
        spec = ar.get("act.a")
        assert spec is not None
        assert spec.id == "act.a"

    def test_get_nonexistent(self, tmp_adapters_dir):
        """退步了会怎样：get 不存在的适配器应返回 None。"""
        from vools.actus.adapter import AdapterRegistry
        ar = AdapterRegistry(adapters_dir=tmp_adapters_dir)
        assert ar.get("not.exists") is None


class TestCreateAdapter:
    def test_create_cli(self, tmp_adapters_dir):
        """退步了会怎样：CLI 类型应创建 CLIAdapter。"""
        from vools.actus.adapter import AdapterRegistry, AdapterSpec, CLIAdapter
        ar = AdapterRegistry(adapters_dir=tmp_adapters_dir)
        spec = AdapterSpec.from_dict({"id": "adapter.cli.test", "adapter": {"type": "cli", "command": "python"}})
        adapter = ar.create_adapter(spec)
        assert isinstance(adapter, CLIAdapter)

    def test_create_invalid_raises(self, tmp_adapters_dir):
        """退步了会怎样：缺 command 的 spec 应抛 AdapterSpecError。"""
        from vools.actus.adapter import AdapterRegistry, AdapterSpec, AdapterSpecError
        ar = AdapterRegistry(adapters_dir=tmp_adapters_dir)
        spec = AdapterSpec.from_dict({"id": "adapter.cli.test", "adapter": {"type": "cli"}})
        with pytest.raises(AdapterSpecError):
            ar.create_adapter(spec)
