# -*- coding: utf-8 -*-
"""project_io.py 契约测试 (Round 54)。

只测公开契约，零产品代码改动。隔离：全部使用 tmp_path。

审计发现（佐证测试，未修）：
- BUG-IO1 (security): import_project (project_io.py:143) `target = root / member.name`
  无任何路径净化/白名单检查 —— 恶意 .actus 包中 member.name 为 `../evil.txt`
  时直接逃出 repo_root 写任意文件。tarfile.extractall 自 3.12 起有 filter 防护，
  但本模块手工 extractfile+open 写入，绕过了全部防护。
- IO2 (inconsistency): merge_project (project_io.py:223) 文档声明三种策略
  (skip_existing/overwrite/rename)，实际只实现 overwrite 布尔映射；
  strategy="rename" 静默退化为 skip_existing。
"""

import hashlib
import json
import tarfile
import io as _io

import pytest

from vools.actus import project_io as pio


# ---------------------------------------------------------------- manifest

class TestCreateProjectManifest:
    def test_empty_root(self, tmp_path):
        m = pio.create_project_manifest(str(tmp_path))
        assert m["version"] == pio.PROJECT_MANIFEST_VERSION == "1.0"
        assert m["actions_count"] == 0
        assert m["actions"] == []
        assert m["configs"] == []
        assert m["name"] == tmp_path.name
        assert "created" in m

    def test_collects_action_files_nested(self, tmp_path):
        (tmp_path / "actions" / "sub").mkdir(parents=True)
        f = tmp_path / "actions" / "sub" / "a.actus.md"
        f.write_text("hello", encoding="utf-8")
        (tmp_path / "actions" / "b.md").write_text("not actus", encoding="utf-8")
        m = pio.create_project_manifest(str(tmp_path))
        assert m["actions_count"] == 1
        a = m["actions"][0]
        assert a["path"].replace("\\", "/") == "actions/sub/a.actus.md"
        assert a["size"] == 5
        assert a["hash"] == hashlib.md5(b"hello").hexdigest()

    def test_collects_each_config(self, tmp_path):
        (tmp_path / ".actus.md").write_text("x", encoding="utf-8")
        (tmp_path / "actus.config.json").write_text("{}", encoding="utf-8")
        (tmp_path / "actus.yaml").write_text("k: v", encoding="utf-8")
        m = pio.create_project_manifest(str(tmp_path))
        got = sorted(c["path"] for c in m["configs"])
        assert got == [".actus.md", "actus.config.json", "actus.yaml"]

    def test_no_actions_dir(self, tmp_path):
        # 没有 actions 目录也应有 configs
        (tmp_path / "actus.yaml").write_text("k: v", encoding="utf-8")
        m = pio.create_project_manifest(str(tmp_path))
        assert m["actions_count"] == 0 and len(m["configs"]) == 1


# ---------------------------------------------------------------- export

class TestExportProject:
    def test_missing_root_returns_none(self, tmp_path):
        assert pio.export_project(str(tmp_path / "nope"),
                                  str(tmp_path / "out.actus")) is None

    def test_roundtrip_manifest(self, tmp_path):
        (tmp_path / "actions").mkdir()
        (tmp_path / "actions" / "a.actus.md").write_text("body", encoding="utf-8")
        out = tmp_path / "pkg.actus"
        r = pio.export_project(str(tmp_path), str(out))
        assert r == str(out) and out.exists()
        with tarfile.open(out, "r:gz") as tar:
            names = tar.getnames()
            assert "manifest.json" in names
            assert "actions/a.actus.md".replace("/", "\\") in names or \
                   "actions/a.actus.md" in names
            man = json.loads(tar.extractfile("manifest.json").read())
        assert man["actions_count"] == 1

    def test_include_meta_false_omits_meta(self, tmp_path):
        (tmp_path / "_meta").mkdir()
        (tmp_path / "_meta" / "ledger.json").write_text("{}", encoding="utf-8")
        out = tmp_path / "p.actus"
        pio.export_project(str(tmp_path), str(out), include_meta=False)
        with tarfile.open(out, "r:gz") as tar:
            assert not any("_meta" in n for n in tar.getnames())

    def test_include_meta_true(self, tmp_path):
        (tmp_path / "_meta").mkdir()
        (tmp_path / "_meta" / "ledger.json").write_text("{}", encoding="utf-8")
        out = tmp_path / "p.actus"
        pio.export_project(str(tmp_path), str(out), include_meta=True)
        with tarfile.open(out, "r:gz") as tar:
            assert any("ledger.json" in n for n in tar.getnames())

    def test_config_files_included(self, tmp_path):
        (tmp_path / "actus.yaml").write_text("k: v", encoding="utf-8")
        out = tmp_path / "p.actus"
        pio.export_project(str(tmp_path), str(out))
        with tarfile.open(out, "r:gz") as tar:
            assert any("actus.yaml" in n for n in tar.getnames())

    def test_bad_output_path_returns_none(self, tmp_path):
        # 输出路径在不存在目录中 → tarfile.open 抛异常 → 捕获返回 None
        r = pio.export_project(str(tmp_path), str(tmp_path / "nodir" / "x.actus"))
        assert r is None

    def test_empty_root_export(self, tmp_path):
        out = tmp_path / "e.actus"
        assert pio.export_project(str(tmp_path), str(out)) == str(out)
        with tarfile.open(out, "r:gz") as tar:
            assert tar.getnames() == ["manifest.json"]


def _make_pkg(tmp_path, name="pkg.actus", manifest_extra=None,
              body=b"body", corrupt_hash=False, drop_action=False):
    """构造一个最小 .actus 包。"""
    actions_dir = tmp_path / "src_actions"
    actions_dir.mkdir(exist_ok=True)
    af = actions_dir / "a.actus.md"
    af.write_bytes(body)
    manifest = {
        "version": "1.0",
        "name": "src",
        "actions_count": 1,
        "actions": [{
            "path": "actions/a.actus.md",
            "size": len(body),
            "hash": hashlib.md5(body).hexdigest(),
        }],
        "configs": [],
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    if corrupt_hash:
        manifest["actions"][0]["hash"] = "0" * 32
    if drop_action:
        # 声明了 action 但包里没有该文件
        out = tmp_path / name
        mb = json.dumps(manifest).encode()
        with tarfile.open(out, "w:gz") as tar:
            info = tarfile.TarInfo("manifest.json")
            info.size = len(mb)
            tar.addfile(info, _io.BytesIO(mb))
        return out
    out = tmp_path / name
    with tarfile.open(out, "w:gz") as tar:
        mb = json.dumps(manifest).encode()
        info = tarfile.TarInfo("manifest.json")
        info.size = len(mb)
        tar.addfile(info, _io.BytesIO(mb))
        ainfo = tarfile.TarInfo("actions/a.actus.md")
        ainfo.size = len(body)
        tar.addfile(ainfo, _io.BytesIO(body))
    return out


# ---------------------------------------------------------------- import

class TestImportProject:
    def test_basic_import(self, tmp_path):
        pkg = _make_pkg(tmp_path)
        dest = tmp_path / "dest"
        stats = pio.import_project(str(dest), str(pkg))
        assert stats == {"imported": 1, "skipped": 0, "errors": 0}
        assert (dest / "actions" / "a.actus.md").read_bytes() == b"body"

    def test_existing_without_overwrite_skips(self, tmp_path):
        pkg = _make_pkg(tmp_path)
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "actions").mkdir()
        (dest / "actions" / "a.actus.md").write_bytes(b"OLD")
        stats = pio.import_project(str(dest), str(pkg), overwrite=False)
        assert stats["skipped"] == 1 and stats["imported"] == 0
        assert (dest / "actions" / "a.actus.md").read_bytes() == b"OLD"

    def test_overwrite_replaces(self, tmp_path):
        pkg = _make_pkg(tmp_path)
        dest = tmp_path / "dest"
        (dest / "actions").mkdir(parents=True)
        (dest / "actions" / "a.actus.md").write_bytes(b"OLD")
        stats = pio.import_project(str(dest), str(pkg), overwrite=True)
        assert stats["imported"] == 1
        assert (dest / "actions" / "a.actus.md").read_bytes() == b"body"

    def test_missing_manifest_still_imports_files(self, tmp_path):
        # 包里没有 manifest.json → manifest={} → 文件照常解压
        pkg = tmp_path / "nomanifest.actus"
        with tarfile.open(pkg, "w:gz") as tar:
            data = b"raw"
            info = tarfile.TarInfo("loose.txt")
            info.size = len(data)
            tar.addfile(info, _io.BytesIO(data))
        dest = tmp_path / "dest"
        stats = pio.import_project(str(dest), str(pkg))
        assert stats["imported"] == 1
        assert (dest / "loose.txt").read_bytes() == b"raw"

    def test_corrupt_tar_returns_none(self, tmp_path):
        bad = tmp_path / "bad.actus"
        bad.write_bytes(b"not a tar at all")
        assert pio.import_project(str(tmp_path / "dest"), str(bad)) is None

    def test_missing_input_returns_none(self, tmp_path):
        assert pio.import_project(str(tmp_path / "dest"),
                                  str(tmp_path / "ghost.actus")) is None

    def test_dir_member_counts_as_error(self, tmp_path):
        # 目录 member：extractfile 返回 None → with None 抛错 → errors+1
        pkg = tmp_path / "dirs.actus"
        with tarfile.open(pkg, "w:gz") as tar:
            d = tarfile.TarInfo("empty_dir/")
            d.type = tarfile.DIRTYPE
            tar.addfile(d)
        stats = pio.import_project(str(tmp_path / "dest"), str(pkg))
        assert stats["errors"] == 1 and stats["imported"] == 0

    def test_bad_json_manifest_ignored(self, tmp_path):
        pkg = tmp_path / "badjson.actus"
        with tarfile.open(pkg, "w:gz") as tar:
            mb = b"{not json"
            info = tarfile.TarInfo("manifest.json")
            info.size = len(mb)
            tar.addfile(info, _io.BytesIO(mb))
        dest = tmp_path / "dest"
        stats = pio.import_project(str(dest), str(pkg))
        assert stats == {"imported": 0, "skipped": 0, "errors": 0}


class TestPathTraversalAudit:
    def test_bug_io1_traversal_writes_outside_root(self, tmp_path):
        """BUG-IO1 佐证：member.name 带 .. 时逃出 repo_root。"""
        pkg = tmp_path / "evil.actus"
        outside = tmp_path / "outside.txt"
        assert not outside.exists()
        with tarfile.open(pkg, "w:gz") as tar:
            data = b"pwned"
            info = tarfile.TarInfo("../outside.txt")
            info.size = len(data)
            tar.addfile(info, _io.BytesIO(data))
        dest = tmp_path / "dest"
        stats = pio.import_project(str(dest), str(pkg), overwrite=True)
        # 记录现状：无净化 → 写到了 dest 之外
        assert outside.exists()
        assert outside.read_bytes() == b"pwned"
        assert stats["imported"] == 1


# ---------------------------------------------------------------- validate

class TestValidateProject:
    def test_missing_file(self, tmp_path):
        r = pio.validate_project(str(tmp_path / "ghost.actus"))
        assert r["valid"] is False
        assert r["errors"] == ["文件不存在"]
        assert r["warnings"] == []

    def test_not_a_tar(self, tmp_path):
        bad = tmp_path / "bad.actus"
        bad.write_bytes(b"garbage")
        r = pio.validate_project(str(bad))
        assert r["valid"] is False
        assert any("无法打开文件" in e for e in r["errors"])

    def test_missing_manifest(self, tmp_path):
        pkg = tmp_path / "nm.actus"
        with tarfile.open(pkg, "w:gz") as tar:
            pass
        r = pio.validate_project(str(pkg))
        assert r["valid"] is False
        assert r["errors"] == ["缺少 manifest.json"]

    def test_bad_json_manifest(self, tmp_path):
        pkg = tmp_path / "bj.actus"
        with tarfile.open(pkg, "w:gz") as tar:
            mb = b"{oops"
            info = tarfile.TarInfo("manifest.json")
            info.size = len(mb)
            tar.addfile(info, _io.BytesIO(mb))
        r = pio.validate_project(str(pkg))
        assert r["errors"] == ["manifest.json 格式错误"]

    def test_valid_roundtrip(self, tmp_path):
        src = tmp_path / "src"
        (src / "actions").mkdir(parents=True)
        (src / "actions" / "a.actus.md").write_text("body", encoding="utf-8")
        out = tmp_path / "ok.actus"
        pio.export_project(str(src), str(out))
        r = pio.validate_project(str(out))
        assert r["valid"] is True
        assert r["errors"] == []
        assert r["manifest"]["actions_count"] == 1

    def test_hash_mismatch_detected(self, tmp_path):
        pkg = _make_pkg(tmp_path, corrupt_hash=True)
        r = pio.validate_project(str(pkg))
        assert r["valid"] is False
        assert any("哈希不匹配" in e for e in r["errors"])

    def test_declared_action_missing_is_warning(self, tmp_path):
        pkg = _make_pkg(tmp_path, drop_action=True)
        r = pio.validate_project(str(pkg))
        # 缺文件是 warning 不是 error → valid 仍为 True（记录现状）
        assert r["valid"] is True
        assert any("声明的文件不存在" in w for w in r["warnings"])

    def test_empty_hash_not_compared(self, tmp_path):
        # expected_hash 为空时不比较（不报哈希不匹配）
        pkg = _make_pkg(tmp_path, manifest_extra=None)
        # 手工改 manifest：去掉 hash 字段
        with tarfile.open(pkg, "r:gz") as tar:
            man = json.loads(tar.extractfile("manifest.json").read())
        man["actions"][0].pop("hash")
        pkg2 = tmp_path / "nohash.actus"
        with tarfile.open(pkg2, "w:gz") as tar:
            mb = json.dumps(man).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(mb)
            tar.addfile(info, _io.BytesIO(mb))
            body = b"body"
            ainfo = tarfile.TarInfo("actions/a.actus.md")
            ainfo.size = len(body)
            tar.addfile(ainfo, _io.BytesIO(body))
        r = pio.validate_project(str(pkg2))
        assert r["valid"] is True and r["errors"] == []


# ---------------------------------------------------------------- merge

class TestMergeProject:
    def test_skip_existing_strategy(self, tmp_path):
        pkg = _make_pkg(tmp_path)
        dest = tmp_path / "dest"
        (dest / "actions").mkdir(parents=True)
        (dest / "actions" / "a.actus.md").write_bytes(b"OLD")
        stats = pio.merge_project(str(dest), str(pkg), strategy="skip_existing")
        assert stats["skipped"] == 1
        assert (dest / "actions" / "a.actus.md").read_bytes() == b"OLD"

    def test_overwrite_strategy(self, tmp_path):
        pkg = _make_pkg(tmp_path)
        dest = tmp_path / "dest"
        (dest / "actions").mkdir(parents=True)
        (dest / "actions" / "a.actus.md").write_bytes(b"OLD")
        stats = pio.merge_project(str(dest), str(pkg), strategy="overwrite")
        assert stats["imported"] == 1

    def test_rename_strategy_degrades_to_skip(self, tmp_path):
        """IO2 佐证：文档声明 rename 策略，实际退化为 skip_existing。"""
        pkg = _make_pkg(tmp_path)
        dest = tmp_path / "dest"
        (dest / "actions").mkdir(parents=True)
        (dest / "actions" / "a.actus.md").write_bytes(b"OLD")
        stats = pio.merge_project(str(dest), str(pkg), strategy="rename")
        assert stats["skipped"] == 1
        assert not (dest / "actions" / "a.actus.md.1").exists()


# ---------------------------------------------------------------- exports

def test_all_exports():
    assert set(pio.__all__) == {
        "PROJECT_MANIFEST_VERSION", "create_project_manifest",
        "export_project", "import_project", "logger",
        "merge_project", "validate_project",
    }
