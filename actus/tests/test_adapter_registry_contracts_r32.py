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


class TestProbeAvailable:
    def test_unknown_type(self):
        """退步了会怎样：未知适配器类型应返回 False。"""
        from vools.actus.adapter import _probe_available, clear_availability_cache
        clear_availability_cache()
        ok, msg = _probe_available("adapter.cli.x", "unknown", "", "", "", "", "", "", False)
        assert ok is False
        assert "未知" in msg

    def test_cli_available(self):
        """退步了会怎样：CLI 命令存在应返回 True。"""
        from vools.actus.adapter import _probe_available, clear_availability_cache
        clear_availability_cache()
        ok, msg = _probe_available("adapter.cli.x", "cli", "python", "", "", "", "", "", False)
        assert ok is True

    def test_cli_unavailable(self):
        """退步了会怎样：CLI 命令不存在应返回 False。"""
        from vools.actus.adapter import _probe_available, clear_availability_cache
        clear_availability_cache()
        ok, msg = _probe_available("adapter.cli.x", "cli", "nonexistent_xyz_123", "", "", "", "", "", False)
        assert ok is False

    def test_http_no_preflight_skips_probe(self):
        """退步了会怎样：HTTP 无 preflight 应直接返回 True（不探测网络）。"""
        from vools.actus.adapter import _probe_available, clear_availability_cache
        clear_availability_cache()
        ok, msg = _probe_available("adapter.http.x", "http", "", "https://example.com", "", "", "", "", False)
        assert ok is True

    def test_cached(self):
        """退步了会怎样：相同 key 应命中缓存。"""
        from vools.actus.adapter import _probe_available, clear_availability_cache
        clear_availability_cache()
        r1 = _probe_available("adapter.cli.cached", "cli", "python", "", "", "", "", "", False)
        r2 = _probe_available("adapter.cli.cached", "cli", "python", "", "", "", "", "", False)
        assert r1 == r2


class TestEnsureAvailable:
    def test_ensure_available_ok(self, tmp_adapters_dir):
        """退步了会怎样：可用适配器不应抛异常。"""
        from vools.actus.adapter import AdapterRegistry, AdapterSpec, clear_availability_cache
        clear_availability_cache()
        ar = AdapterRegistry(adapters_dir=tmp_adapters_dir)
        spec = AdapterSpec.from_dict({"id": "adapter.cli.test", "adapter": {"type": "cli", "command": "python"}})
        ar.ensure_available("adapter.cli.test", spec)  # 不应抛

    def test_ensure_available_unavailable(self, tmp_adapters_dir):
        """退步了会怎样：不可用适配器应抛 AdapterUnavailableError。"""
        from vools.actus.adapter import (AdapterRegistry, AdapterSpec, AdapterUnavailableError,
                                         clear_availability_cache)
        clear_availability_cache()
        ar = AdapterRegistry(adapters_dir=tmp_adapters_dir)
        spec = AdapterSpec.from_dict({
            "id": "adapter.cli.test",
            "adapter": {"type": "cli", "command": "nonexistent_xyz_123"},
        })
        with pytest.raises(AdapterUnavailableError):
            ar.ensure_available("adapter.cli.test", spec)


class TestValidateAdapterSpec:
    def test_valid_cli(self):
        """退步了会怎样：合法 CLI 应通过。"""
        from vools.actus.adapter import AdapterSpec, validate_adapter_spec
        spec = AdapterSpec.from_dict({
            "id": "adapter.cli.test",
            "adapter": {"type": "cli", "command": "python"},
        })
        ok, issues = validate_adapter_spec(spec)
        assert ok is True
        assert issues == []

    def test_cli_missing_command(self):
        """退步了会怎样：CLI 缺 command 应报 issues。"""
        from vools.actus.adapter import AdapterSpec, validate_adapter_spec
        spec = AdapterSpec.from_dict({
            "id": "adapter.cli.test",
            "adapter": {"type": "cli"},
        })
        ok, issues = validate_adapter_spec(spec)
        assert ok is False
        assert any("command" in i for i in issues)

    def test_quicker_missing_action(self):
        """退步了会怎样：Quicker 缺 action 应报 issues。"""
        from vools.actus.adapter import AdapterSpec, validate_adapter_spec
        spec = AdapterSpec.from_dict({
            "id": "adapter.quicker.test",
            "adapter": {"type": "quicker"},
        })
        ok, issues = validate_adapter_spec(spec)
        assert ok is False
        assert any("action" in i for i in issues)

    def test_http_missing_url(self):
        """退步了会怎样：HTTP 缺 url 应报 issues。"""
        from vools.actus.adapter import AdapterSpec, validate_adapter_spec
        spec = AdapterSpec.from_dict({
            "id": "adapter.http.test",
            "adapter": {"type": "http"},
        })
        ok, issues = validate_adapter_spec(spec)
        assert ok is False
        assert any("url" in i for i in issues)

    def test_mcp_missing_server_and_tool(self):
        """退步了会怎样：MCP 缺 server+tool 应报 issues。"""
        from vools.actus.adapter import AdapterSpec, validate_adapter_spec
        spec = AdapterSpec.from_dict({
            "id": "adapter.mcp.test",
            "adapter": {"type": "mcp"},
        })
        ok, issues = validate_adapter_spec(spec)
        assert ok is False
        assert any("mcp_server" in i for i in issues)
        assert any("mcp_tool" in i for i in issues)

    def test_valid_quicker(self):
        """退步了会怎样：合法 Quicker 应通过。"""
        from vools.actus.adapter import AdapterSpec, validate_adapter_spec
        spec = AdapterSpec.from_dict({
            "id": "adapter.quicker.test",
            "adapter": {"type": "quicker", "action": "my_action"},
        })
        ok, issues = validate_adapter_spec(spec)
        assert ok is True

    def test_valid_http(self):
        """退步了会怎样：合法 HTTP 应通过。"""
        from vools.actus.adapter import AdapterSpec, validate_adapter_spec
        spec = AdapterSpec.from_dict({
            "id": "adapter.http.test",
            "adapter": {"type": "http", "url": "https://example.com"},
        })
        ok, issues = validate_adapter_spec(spec)
        assert ok is True

    def test_valid_mcp(self):
        """退步了会怎样：合法 MCP 应通过。"""
        from vools.actus.adapter import AdapterSpec, validate_adapter_spec
        spec = AdapterSpec.from_dict({
            "id": "adapter.mcp.test",
            "adapter": {"type": "mcp", "mcp_server": "srv", "mcp_tool": "tool"},
        })
        ok, issues = validate_adapter_spec(spec)
        assert ok is True
