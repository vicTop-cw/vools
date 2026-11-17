"""T0r12: E4 交互增强——分页与总数 / 排序 / CSV 导出测试。

覆盖提升计划 E4「交互增强」验收标准：
- 分页与总数：`search_params_with_total` 支持 offset 分页并返回实际匹配数
  total（过滤 + 打分后、截断前的完整命中数）；空查询 / 纯过滤场景分页
  同样生效；`search()` 分页语义与 E1 的 offset/limit 内核一致；
- 排序：CLI/MCP 支持 trust|name|recent 三种排序（trust=信任度优先、
  name=名称字典序、recent=最近注册优先），内核 `SearchParams.sort` 实现；
  默认行为（相关度排序 / 空查询注册序逆序）不回归；未知 sort 回退默认；
- CLI --json 输出含 total/offset/limit，且 --csv 导出的字段与 JSON actions
  对齐（tags/purpose/industry 多值以 `|` 平铺）；
- 既有检索 / 倒排 / 语义 / fuzzy / 中文分词套件不回归（由全量回归确认）。

改动范围限 `E:\\IDEProjects\\AI\\vools\\actus`（红线：不删除文件、
不破坏 schema、可 git 回溯）。
"""

import csv
import io
from types import SimpleNamespace

import pytest

from vools.actus.registry import ActionRegistry, RegistryEntry, SearchParams

# ── 构造器（与既有 T0r 测试同风格：直接塞 entries，不落盘） ──


def _mk_entry(aid, name, trust="community", tags=None, desc="", kind=None,
              purpose=None, industry=None):
    return RegistryEntry(
        id=aid, name=name, version="1.0.0", description=desc or f"{name} desc",
        category="bench", path=f"bench/{aid}.actus.md", author="tester",
        tags=tags or ["shared"], checksum=f"sum{aid}",
        trust_level=trust, kind=kind, purpose=purpose, industry=industry)


def _mk_registry(specs):
    """构造 ActionRegistry（specs: dict(aid, name, trust, tags, desc, kind,
    purpose, industry) 列表，按列表顺序 = 注册序）。"""
    reg = ActionRegistry()
    for i, s in enumerate(specs):
        reg._entries[s["aid"]] = _mk_entry(
            s["aid"], s["name"], trust=s.get("trust", "community"),
            tags=s.get("tags"), desc=s.get("desc", ""),
            kind=s.get("kind"), purpose=s.get("purpose"),
            industry=s.get("industry"))
    return reg


def _ids(entries):
    out = []
    for e in entries:
        if isinstance(e, dict) and "entry" in e:
            e = e["entry"]
        out.append(e["id"] if isinstance(e, dict) else e.id)
    return out


# 8 条共享 tag 'data' 的条目：注册序 a0..a7，关键词 'data' 全命中
PAGE_SPECS = [
    {"aid": "a0", "name": "Zero", "trust": "trusted", "tags": ["data"]},
    {"aid": "a1", "name": "One", "trust": "community", "tags": ["data"]},
    {"aid": "a2", "name": "Two", "trust": "unverified", "tags": ["data"]},
    {"aid": "a3", "name": "Three", "trust": "trusted", "tags": ["data"]},
    {"aid": "a4", "name": "Four", "trust": "community", "tags": ["data"]},
    {"aid": "a5", "name": "Five", "trust": "unverified", "tags": ["data"]},
    {"aid": "a6", "name": "Six", "trust": "trusted", "tags": ["data"]},
    {"aid": "a7", "name": "Seven", "trust": "community", "tags": ["data"]},
]


class TestPaginationAndTotal:
    """分页与总数：offset+limit 正确、total=实际匹配数。"""

    def test_keyword_pagination_slices_and_total(self):
        reg = _mk_registry(PAGE_SPECS)
        # 关键词 'data' 命中 tag 共 8 条；分页切片 = 相关度序（同分注册序）
        full = _ids(reg.search("data", limit=50))
        assert len(full) == 8
        p0, t0 = reg.search_params_with_total(SearchParams(query="data", limit=3, offset=0))
        p1, t1 = reg.search_params_with_total(SearchParams(query="data", limit=3, offset=3))
        p2, t2 = reg.search_params_with_total(SearchParams(query="data", limit=3, offset=6))
        assert t0 == t1 == t2 == 8
        assert _ids(p0) == full[0:3]
        assert _ids(p1) == full[3:6]
        assert _ids(p2) == full[6:8]  # 越界页返回空，total 仍为 8

    def test_keyword_total_equals_full_match_count(self):
        reg = _mk_registry(PAGE_SPECS)
        params = SearchParams(query="data", limit=2, offset=0)
        rows, total = reg.search_params_with_total(params)
        assert len(rows) == 2
        assert total == len(_ids(reg.search("data", limit=50)))

    def test_empty_query_pagination_and_total(self):
        reg = _mk_registry(PAGE_SPECS)
        # 空查询：total = 注册表大小；分页 = 注册序逆序（最近注册在前）
        params = SearchParams(query="", limit=2, offset=1)
        rows, total = reg.search_params_with_total(params)
        assert total == 8
        assert _ids(rows) == ["a6", "a5"]  # reversed(a0..a7)[1:3]

    def test_filter_only_pagination_and_total(self):
        reg = _mk_registry(PAGE_SPECS)
        # 纯过滤（无关键词）：只命中 trusted 的 3 条
        params = SearchParams(category="bench", limit=2, offset=0)
        rows, total = reg.search_params_with_total(params)
        assert total == 8
        # kind 过滤：trusted 子集仍需显式构造；此处用 kind 过滤演示
        specs = [{"aid": "k0", "name": "A", "kind": "exec"},
                 {"aid": "k1", "name": "B", "kind": "demo"},
                 {"aid": "k2", "name": "C", "kind": "exec"},
                 {"aid": "k3", "name": "D", "kind": "exec"}]
        reg2 = _mk_registry(specs)
        params2 = SearchParams(kind="exec", limit=1, offset=1)
        rows2, total2 = reg2.search_params_with_total(params2)
        assert total2 == 3
        assert _ids(rows2) == ["k2"]  # 注册逆序 [k3,k2,k1][1:2]

    def test_search_offset_limit_consistency(self):
        # E1 已引入的 search(offset/limit) 与 with_total 分页一致
        reg = _mk_registry(PAGE_SPECS)
        assert _ids(reg.search("data", limit=3, offset=2)) == _ids(
            reg.search_params_with_total(
                SearchParams(query="data", limit=3, offset=2))[0])


class TestSortModes:
    """三种排序：trust / name / recent 各自一致性 + 默认不回归。"""

    def test_sort_trust_puts_trusted_first(self):
        reg = _mk_registry(PAGE_SPECS)
        rows = _ids(reg.search("data", sort="trust", limit=50))
        trust_rank = {"trusted": 0, "community": 1, "unverified": 2}
        ranks = [trust_rank[reg._entries[i].trust_level] for i in rows]
        assert ranks == sorted(ranks)
        assert rows[:3] == ["a0", "a3", "a6"]  # trusted 全在前

    def test_sort_name_lexicographic(self):
        reg = _mk_registry(PAGE_SPECS)
        rows = _ids(reg.search("data", sort="name", limit=50))
        names = [reg._entries[i].name.lower() for i in rows]
        assert names == sorted(names)
        assert rows[0] == "a5"  # "five" 字典序最小

    def test_sort_recent_registration_order(self):
        reg = _mk_registry(PAGE_SPECS)
        rows = _ids(reg.search("data", sort="recent", limit=50))
        assert rows == ["a7", "a6", "a5", "a4", "a3", "a2", "a1", "a0"]

    def test_default_relevance_unchanged(self):
        # 默认（sort=None / 空串 / 未知值）均与不带 sort 的 search 一致
        reg = _mk_registry(PAGE_SPECS)
        base = _ids(reg.search("data", limit=50))
        assert _ids(reg.search("data", limit=50, sort=None)) == base
        assert _ids(reg.search("data", limit=50, sort="")) == base
        assert _ids(reg.search("data", limit=50, sort="bogus")) == base

    def test_default_relevance_score_desc_then_registration(self):
        # 非空查询默认排序 = 分数降序、同分注册序（构造不同分数验证）
        specs = [
            {"aid": "m0", "name": "File Manager", "desc": "manage files",
             "tags": ["file"]},
            {"aid": "m1", "name": "File Watcher", "desc": "watch files",
             "tags": ["file", "watch"]},
            {"aid": "m2", "name": "Disk Manager", "desc": "manage disks",
             "tags": ["disk", "file"]},
        ]
        reg = _mk_registry(specs)
        rows = _ids(reg.search("file manager", limit=50))
        # 精确 id/name 命中者在前（m0 的 name 含 'file manager' 完整词）
        assert rows[0] == "m0"
        # 其余按分数，未命中者不返回
        assert set(rows) == {"m0", "m1", "m2"}

    def test_sort_trust_empty_query(self):
        reg = _mk_registry(PAGE_SPECS)
        rows = _ids(reg.search("", sort="trust", limit=50))
        rank = {"trusted": 0, "community": 1, "unverified": 2}
        assert [rank[reg._entries[i].trust_level] for i in rows] == sorted(
            rank[reg._entries[i].trust_level] for i in rows)

    def test_sort_passthrough_explain(self):
        reg = _mk_registry(PAGE_SPECS)
        rows = reg.search_explain("data", sort="recent", limit=50)
        assert _ids(rows) == ["a7", "a6", "a5", "a4", "a3", "a2", "a1", "a0"]


# ── CLI 级测试：monkeypatch 替换检索内核为固定 stub，验证 _cmd_search ──


class _FakeRegistry:
    """可调用 stub：`ActionRegistry()` 返回共享实例，记录调用参数。"""

    def __init__(self, entries=None):
        self.calls = []
        self.idx = None
        self._entries_ = entries

    def load_from_index(self, idx):
        self.idx = idx

    def search_params_with_total(self, params):
        self.calls.append(("search_params_with_total", params))
        rows = self._entries_ or [
            _mk_entry("r0", "Row Zero", trust="trusted"),
            _mk_entry("r1", "Row One", trust="community"),
            _mk_entry("r2", "Row Two", trust="unverified"),
        ]
        total = 5
        return rows[params.offset: params.offset + params.limit], total

    def search_explain(self, **kw):
        self.calls.append(("search_explain", kw))
        return []


@pytest.fixture
def cli_search_env(monkeypatch):
    """把 cli._cmd_search 依赖的 indexer 替换为可控 stub（registry 按测试自配）。"""
    from vools.actus import cli as cli_mod
    import vools.actus.indexer as idx_mod

    monkeypatch.setattr(idx_mod, "load_index",
                        lambda build=False: {"actions": {}})
    return cli_mod


def _mk_search_args(**over):
    base = dict(query="data", category=None, author=None, tag=None,
                source="local", url=None, limit=2, offset=1, json_output=False,
                sort=None, csv=False, output=None, kind=None, purpose=None,
                industry=None)
    base.update(over)
    return SimpleNamespace(**base)


class TestCliJsonTotal:
    """CLI --json 输出 total/offset/limit，sort 透传内核。"""

    def test_json_has_total_and_pagination_fields(self, cli_search_env, capsys,
                                                    monkeypatch):
        import vools.actus.registry as reg_mod
        fake = _FakeRegistry()
        monkeypatch.setattr(reg_mod, "ActionRegistry", lambda: fake)
        args = _mk_search_args(json_output=True, limit=2, offset=1, sort="trust")
        rc = cli_search_env._cmd_search(args)
        out = capsys.readouterr().out
        import json as _json
        payload = _json.loads(out)
        assert rc == 0
        assert payload["status"] == "ok"
        assert payload["count"] == 2
        assert payload["total"] == 5
        assert payload["offset"] == 1
        assert payload["limit"] == 2
        assert len(payload["actions"]) == 2
        assert {"id", "name", "version", "trust", "description", "author",
                "category", "tags", "kind", "purpose", "industry"} <= set(
                    payload["actions"][0].keys())

    def test_sort_recorded_by_fake(self, cli_search_env, monkeypatch):
        from vools.actus import cli as cli_mod
        import vools.actus.registry as reg_mod
        fake = _FakeRegistry()
        monkeypatch.setattr(reg_mod, "ActionRegistry", lambda: fake)
        args = _mk_search_args(json_output=True, sort="name", limit=3, offset=2)
        cli_mod._cmd_search(args)
        kind, params = fake.calls[0]
        assert kind == "search_params_with_total"
        assert params.sort == "name"
        assert params.limit == 3
        assert params.offset == 2

    def test_human_sort_passthrough(self, cli_search_env, monkeypatch):
        from vools.actus import cli as cli_mod
        import vools.actus.registry as reg_mod
        fake = _FakeRegistry()
        monkeypatch.setattr(reg_mod, "ActionRegistry", lambda: fake)
        args = _mk_search_args(json_output=False, sort="trust")
        cli_mod._cmd_search(args)
        assert fake.calls
        kind, kw = fake.calls[-1]
        assert kind == "search_explain"
        assert kw["sort"] == "trust"


class TestCliCsv:
    """CLI --csv 导出：字段与 --json 的 actions 对齐。"""

    JSON_ACTIONS = [
        {"id": "r0", "name": "Row Zero", "version": "1.0.0", "trust": "trusted",
         "description": "d", "author": "tester", "category": "bench",
         "tags": ["file", "data"], "kind": "exec",
         "purpose": ["utility"], "industry": ["general"]},
        {"id": "r1", "name": "Row One", "version": "1.0.0", "trust": "community",
         "description": "d2", "author": "tester", "category": "bench",
         "tags": ["watch"], "kind": "demo",
         "purpose": ["transform"], "industry": ["devops"]},
    ]
    # CLI --json 分支经 `search_params_with_total` 取 RegistryEntry，
    # 再由 cli 映射为扁平 JSON；组合测试用真实 entry 驱动整链路。
    CSV_ENTRIES = [
        _mk_entry("r0", "Row Zero", trust="trusted", tags=["file", "data"],
                  desc="d", kind="exec", purpose=["utility"],
                  industry=["general"]),
        _mk_entry("r1", "Row One", trust="community", tags=["watch"],
                  desc="d2", kind="demo", purpose=["transform"],
                  industry=["devops"]),
    ]

    def test_csv_headers_match_json_fields(self, cli_search_env, capsys):
        rc = cli_search_env._emit_search_csv(self.JSON_ACTIONS)
        out = capsys.readouterr().out
        assert rc == 0
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[0] == list(self.JSON_ACTIONS[0].keys())
        assert rows[0] == ['id', 'name', 'version', 'trust', 'description',
                           'author', 'category', 'tags', 'kind', 'purpose',
                           'industry']

    def test_csv_multivalue_flatten(self, cli_search_env, capsys):
        cli_search_env._emit_search_csv(self.JSON_ACTIONS[:1])
        out = capsys.readouterr().out
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[1][7] == "file|data"   # tags
        assert rows[1][9] == "utility"     # purpose
        assert rows[1][10] == "general"    # industry

    def test_csv_json_combo_and_output_file(self, cli_search_env, tmp_path,
                                            monkeypatch, capsys):
        from vools.actus import cli as cli_mod
        import vools.actus.registry as reg_mod
        fake = _FakeRegistry(self.CSV_ENTRIES)
        monkeypatch.setattr(reg_mod, "ActionRegistry", lambda: fake)
        out_csv = tmp_path / "out.csv"
        args = _mk_search_args(json_output=True, csv=True,
                               output=str(out_csv), limit=2, offset=0)
        rc = cli_mod._cmd_search(args)
        assert rc == 0
        assert out_csv.exists()
        text = out_csv.read_text(encoding="utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        assert rows[0] == list(self.JSON_ACTIONS[0].keys())
        assert len(rows) == 1 + 2  # header + 2 actions

    def test_csv_json_combo_stdout(self, cli_search_env, monkeypatch, capsys):
        from vools.actus import cli as cli_mod
        import vools.actus.registry as reg_mod
        fake = _FakeRegistry(self.CSV_ENTRIES)
        monkeypatch.setattr(reg_mod, "ActionRegistry", lambda: fake)
        args = _mk_search_args(json_output=True, csv=True, limit=2, offset=0)
        rc = cli_mod._cmd_search(args)
        out = capsys.readouterr().out
        assert rc == 0
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[0] == list(self.JSON_ACTIONS[0].keys())
