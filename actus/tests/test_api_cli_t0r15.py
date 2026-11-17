# -*- coding: utf-8 -*-
"""F5（T0r15）API/CLI 接口完善测试。

覆盖验收标准：
- `actus search --source url --repo/--path <本地路径>`：直接实时加载仓库搜索，
  不依赖缓存索引（仓库内无任何索引文件也能搜）；
- `actus search --source url --url <git-url>`：git URL 浅克隆拉取后搜索；
- `actus suggest <desc>`：输出含 reason 与 confidence（等同 recommend，
  与 E3 已实现的 recommend/reason 链一致）；
- 包公开 API：`from vools.actus import ActionRegistry, search_registry,
  recommend_registry` 可导入，search/recommend 调用契约不变。
"""

import json
import os
import subprocess

import pytest

from vools.actus import cli as actus_cli
from vools.actus.indexer import build_index
from vools.actus.registry import ActionRegistry, RegistryEntry
from vools.actus.paths import meta_dir as actus_meta_dir


@pytest.fixture(autouse=True)
def _env_to_tmp(tmp_path, monkeypatch):
    """测试卫生：ACTUS_REPO_ROOT（scan/build 缓存真源）与 USERPROFILE
    （`~` 展开，隔离 _clone_url_repo 的克隆缓存）都指到 tmp。"""
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


ACTIONS = [
    # (aid, name, kind, purpose, industry, author, tags, desc, usage)
    ("test.t0r15.calc", "Calc Tool", "exec", "compute", "general", "alice",
     ["math", "calc"], "计算工具：数学公式计算",
     "计算数学表达式，如 1+2*3"),
    ("test.t0r15.mathlib", "Math Lib", "exec", "compute", "general", "bob",
     ["math", "lib"], "数学库函数集合",
     "提供常用数学函数与数值算法"),
    ("test.t0r15.monitor", "Folder Monitor", "exec", "compute", "general", "carol",
     ["watch", "monitor"], "监控文件夹变化",
     "监控文件系统目录变化并上报事件"),
    ("test.t0r15.web", "Open Web", "exec", "web", "internet", "dave",
     ["web", "http"], "打开网页",
     "打开指定 URL 并等待加载完成"),
    ("test.t0r15.demo", "Demo Action", "demo", "demo", "finance", "erin",
     ["demo"], "演示动作",
     "演示用：输出固定结果"),
]


def _old_action_md(aid, name, kind, purpose, industry, author, tags, desc,
                   usage):
    """老格式动作（.actus.md + #!cfg JSON 块）—— registry 实时构建路径解析。"""
    tag_list = json.dumps(tags, ensure_ascii=False)
    cfg = {
        "id": aid, "name": name, "version": "1.0.0", "trust": "sandbox",
        "entry": "main", "platform": "desktop", "description": desc,
        "usage": usage, "author": author, "tags": tags,
        "kind": kind, "purpose": purpose, "industry": industry,
    }
    return (
        "```json #!cfg\n%s\n```\n\n# %s\n\n```python #!run tag=main\n"
        "def main():\n    return \"ok\"\n```\n"
        % (json.dumps(cfg, ensure_ascii=False, indent=1), name))


def _new_action_md(aid, name, kind, purpose, industry, author, tags, desc,
                   usage):
    """新格式动作（.actus.schema.md + YAML front-matter）—— indexer 索引路径。"""
    tag_str = ", ".join(tags)
    return f"""---
id: {aid}
name: {name}
version: 1.0.0
trust: sandbox
kind: {kind}
purpose: [{purpose}]
industry: [{industry}]
trigger: [manual]
context_applies: []
entry: main
description: {desc}
usage: {usage}
author: {author}
platform: desktop
tags: [{tag_str}]
license: mit
pricing: free
declared_features: []
deprecated: false
---

# {name}

## Implementation

```python #!run tag=main
def main():
    return "ok"
```
"""


def _write_repo(repo_root, actions, suffix=".actus.md", render=_old_action_md):
    actions_dir = repo_root / "actions"
    actions_dir.mkdir(parents=True, exist_ok=True)
    for aid, name, kind, purpose, industry, author, tags, desc, usage in actions:
        (actions_dir / ("%s%s" % (aid, suffix))).write_text(
            render(aid, name, kind, purpose, industry, author, tags,
                   desc, usage),
            encoding="utf-8")
    return repo_root


@pytest.fixture
def sample_repo(tmp_path):
    """仅含老格式 actions/ 的仓库：没有任何索引文件（验证实时构建路径）。"""
    return _write_repo(tmp_path / "repo", ACTIONS)


@pytest.fixture
def indexed_repo(tmp_path):
    """新格式仓库 + 索引（suggest 走 indexer.load_index）。

    meta 目录必须显式传给 build_index（自定义 actions_dir 时未显式
    meta_dir 不会落盘），且与 suggest 的 load_index 默认 meta 一致：
    跟随 conftest 钉住的 ACTUS_META_DIR（默认 tmp_path/_meta_runtime），
    故用 paths.meta_dir() 解析，不硬编码目录名。
    """
    repo = _write_repo(tmp_path / "indexed", ACTIONS,
                       suffix=".actus.schema.md", render=_new_action_md)
    build_index(actions_dir=str(repo / "actions"),
                meta_dir=actus_meta_dir(), write=True)
    return repo


@pytest.fixture
def git_repo(tmp_path):
    """真实 git 仓库（含一次提交），供 --source url --url 浅克隆。"""
    repo = _write_repo(tmp_path / "git_repo", ACTIONS)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True,
                   capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-m", "init"], check=True, capture_output=True)
    return repo


class TestSearchUrlRepoPath:
    """① --source url 直接指定本地 repo 路径（--repo/--path 等价）。"""

    def test_repo_path_direct_search(self, sample_repo, capsys):
        rc = actus_cli.main(["search", "计算", "--source", "url",
                             "--repo", str(sample_repo)])
        out = capsys.readouterr().out
        assert rc == 0, out
        assert "test.t0r15.calc" in out
        # 实时构建路径：仓库里不应留下任何索引文件
        assert not os.path.exists(str(sample_repo / ".actus.registry.json"))

    def test_path_alias_equivalent(self, sample_repo, capsys):
        rc = actus_cli.main(["search", "监控", "--source", "url",
                             "--path", str(sample_repo)])
        out = capsys.readouterr().out
        assert rc == 0, out
        assert "test.t0r15.monitor" in out

    def test_repo_path_json_output(self, sample_repo, capsys):
        rc = actus_cli.main(["search", "计算", "--source", "url",
                             "--repo", str(sample_repo), "--json"])
        out = capsys.readouterr().out
        assert rc == 0, out
        data = json.loads(out)
        assert data["status"] == "ok"
        ids = [r.get("id") or r.get("name") for r in data["actions"]]
        assert "test.t0r15.calc" in ids

    def test_missing_repo_returns_error(self, tmp_path, capsys):
        rc = actus_cli.main(["search", "计算", "--source", "url",
                             "--repo", str(tmp_path / "no-such-repo")])
        out = capsys.readouterr().out
        assert rc == 1, out
        assert "不存在" in out

    def test_missing_url_and_repo_returns_error(self, capsys):
        rc = actus_cli.main(["search", "计算", "--source", "url"])
        out = capsys.readouterr().out
        assert rc == 1, out
        assert "--url" in out and "--repo" in out


class TestSearchUrlGitClone:
    """② --source url --url 浅克隆拉取后搜索。"""

    def test_git_url_clone_and_search(self, git_repo, capsys):
        rc = actus_cli.main(["search", "计算", "--source", "url",
                             "--url", str(git_repo)])
        out = capsys.readouterr().out
        assert rc == 0, out
        assert "test.t0r15.calc" in out
        # 克隆缓存落在 <USERPROFILE>/.actus/cache/url_repos 下（测试已隔离）
        cache_root = os.path.join(
            os.path.expanduser("~"), ".actus", "cache", "url_repos")
        assert os.path.isdir(cache_root)
        assert any(os.path.isdir(os.path.join(cache_root, d))
                   and os.path.isdir(os.path.join(cache_root, d, "actions"))
                   for d in os.listdir(cache_root))

    def test_clone_failure_returns_error(self, tmp_path, capsys):
        rc = actus_cli.main(["search", "计算", "--source", "url",
                             "--url", str(tmp_path / "no-such-git-repo")])
        out = capsys.readouterr().out
        assert rc == 1, out
        assert "无法拉取" in out


class TestSuggestCLI:
    """③ suggest 子命令：输出含 reason 与 confidence（等同 recommend）。"""

    def test_suggest_json_contains_reason_confidence(self, indexed_repo, capsys):
        rc = actus_cli.main(["suggest", "计算", "--json"])
        out = capsys.readouterr().out
        assert rc == 0, out
        data = json.loads(out)
        assert data["status"] == "ok"
        assert data["query"] == "计算"
        assert data["count"] >= 3, out
        for rec in data["recommendations"]:
            assert "id" in rec
            assert "reason" in rec and rec["reason"], rec
            assert isinstance(rec["confidence"], float)
            assert 0 <= rec["confidence"] <= 1.0
            assert isinstance(rec["score"], float)
            assert "match_fields" in rec
        # 顶项 = 最相关：calc
        assert data["recommendations"][0]["id"] == "test.t0r15.calc"
        assert data["recommendations"][0]["confidence"] == \
            data["recommendations"][0]["score"]

    def test_suggest_json_equals_recommend(self, indexed_repo, capsys):
        actus_cli.main(["suggest", "计算", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        reg = ActionRegistry()
        reg.load_from_index(
            build_index(actions_dir=str(indexed_repo / "actions"),
                        meta_dir=actus_meta_dir(),
                        write=True))
        recs = reg.recommend("计算", limit=data["count"])
        assert [r["entry"]["id"] for r in recs] == \
            [r["id"] for r in data["recommendations"]]

    def test_suggest_human_output_contains_reason_confidence(self, indexed_repo,
                                                             capsys):
        rc = actus_cli.main(["suggest", "计算"])
        out = capsys.readouterr().out
        assert rc == 0, out
        assert "置信度=" in out
        assert "理由:" in out
        assert "test.t0r15.calc" in out

    def test_suggest_respects_limit(self, indexed_repo, capsys):
        rc = actus_cli.main(["suggest", "计算", "--limit", "1", "--json"])
        out = capsys.readouterr().out
        assert rc == 0, out
        data = json.loads(out)
        assert len(data["recommendations"]) == 1

    def test_suggest_semantic_flag_accepted(self, indexed_repo, capsys):
        rc = actus_cli.main(["suggest", "计算", "--semantic", "--json"])
        out = capsys.readouterr().out
        assert rc == 0, out
        data = json.loads(out)
        assert data["count"] >= 1


class TestPublicAPI:
    """④ 公开 API：__init__.py 导出 + 调用契约不变。"""

    def test_import_from_package(self):
        from vools.actus import (ActionRegistry, RegistryEntry,
                                 search_registry, recommend_registry)
        from vools.actus import __all__
        for name in ("ActionRegistry", "search_registry", "recommend_registry"):
            assert name in __all__, name

    def test_search_registry_returns_entries(self, sample_repo):
        from vools.actus import search_registry
        hits = search_registry(str(sample_repo), "计算", limit=5)
        assert isinstance(hits, list)
        assert hits, "应至少命中 calc"
        assert isinstance(hits[0], RegistryEntry)
        assert hits[0].id == "test.t0r15.calc"

    def test_recommend_registry_returns_dicts_with_reason_confidence(
            self, sample_repo):
        from vools.actus import recommend_registry
        recs = recommend_registry(str(sample_repo), "计算", limit=3)
        assert recs
        for rec in recs:
            assert rec["reason"], rec
            assert isinstance(rec["confidence"], float)
            assert 0 <= rec["confidence"] <= 1.0
            assert rec["entry"]["id"]

    def test_action_registry_methods_contract_unchanged(self, sample_repo):
        reg = ActionRegistry()
        reg.load_from_repo(str(sample_repo))
        # search 契约：返回 RegistryEntry 列表
        hits = reg.search("监控", limit=5)
        assert isinstance(hits, list) and hits
        assert isinstance(hits[0], RegistryEntry)
        assert hits[0].id == "test.t0r15.monitor"
        # recommend 契约：返回 dict 列表，含 entry/score/confidence/reason/match_fields
        recs = reg.recommend("计算", limit=3)
        assert recs
        for rec in recs:
            for key in ("entry", "score", "confidence", "reason",
                        "match_fields"):
                assert key in rec, key
