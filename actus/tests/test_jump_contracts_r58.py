# -*- coding: utf-8 -*-
"""jump.py 契约测试 —— 跳板机文件传输（全部 mock，零真实网络/ssh/paramiko）。

方法论：审计驱动 + 契约测试（每条断言能红）。产品代码零改动。

本轮发现（BUG 佐证测试，未修，待裁决）：
- BUG-J1: sync() 非 paramiko 路径不把 delete 传给 compute_sync_plan
  (jump.py:476) —— sync(delete=True) 在 scp/tar+ssh 路径被静默忽略
  （paramiko 路径 jump.py:467 有传）。
- BUG-J2: _pull_paramiko 单文件 stat (jump.py:1020) 直接 S_ISREG/S_ISDIR，
  不走 _sftp_entry_kind 的兜底 —— 实测跳板机（st_mode 只有权限位 0o666、
  没有类型位）单文件拉取恒报「既不是文件也不是目录」，而 walk/scan 路径
  有兜底。同模块内两套判定不一致。
- BUG-J3: _pull_tar_ssh (jump.py:639) 只检查 tar_proc.returncode，
  不检查 ssh_proc.returncode —— ssh 失败（rc≠0、空流）时 tar 以 rc=0
  正常退出 → 报 ok。与 _push_tar_ssh（ssh:571 + tar:574 双检）不对称。
- BUG-J4: _push_scp 的 mkdir ssh 调用 (jump.py:524) 在 try 之外 ——
  ssh 不可达时裸异常直接冲出 _push_scp 和 push()（push 无 try），
  不会返回 {"status": "error"}。_push_tar_ssh/_push_paramiko 都有兜底。
"""
import io
import os
import sys
import types

import pytest

from vools.actus import jump as jm
from vools.actus import jump


# ═══════════════ 基础纯函数 ═══════════════

class TestShquote:
    def test_none(self):
        assert jm.shquote(None) == "''"

    def test_simple(self):
        assert jm.shquote("abc") == "'abc'"

    def test_space(self):
        assert jm.shquote("a b") == "'a b'"

    def test_embedded_quote(self):
        assert jm.shquote("x'y") == "'x'\\''y'"

    def test_non_string_coerced(self):
        assert jm.shquote(5) == "'5'"

    def test_semicolon_not_interpreted(self):
        # 单引号内一切皆字面量：分号不再能拆命令
        q = jm.shquote("a; rm -rf /")
        assert q == "'a; rm -rf /'"
        assert q.startswith("'") and q.endswith("'")


class TestRemoteJoin:
    def test_posix_join(self):
        assert jm.remote_join("/base", "sub/f.txt") == "/base/sub/f.txt"

    def test_backslash_normalized(self):
        assert jm.remote_join("/base", "sub\\f.txt") == "/base/sub/f.txt"

    def test_all_backslashes(self):
        assert jm.remote_join("/b", "a\\b\\c") == "/b/a/b/c"


class TestSafeRelpath:
    @pytest.mark.parametrize("p,ok", [
        ("", True),
        ("a/b", True),
        ("a", True),
        ("../x", False),
        ("a/../b", False),
        ("/abs", False),
        ("C:/x", False),
        ("a\\..\\b", False),
        ("..", False),
        ("a/./b", True),
    ])
    def test_cases(self, p, ok):
        assert jm._is_safe_relpath(p) is ok


class TestShouldExclude:
    def test_exact(self):
        assert jm.should_exclude("a.txt", ["a.txt"]) is True

    def test_glob(self):
        assert jm.should_exclude("x.log", ["*.log"]) is True

    def test_path_part(self):
        # 只匹配路径部件，不匹配不相关文件名
        assert jm.should_exclude("src/node_modules/foo", ["node_modules"]) is True
        assert jm.should_exclude("foo", ["node_modules"]) is False

    def test_backslash_path_part(self):
        assert jm.should_exclude("src\\node_modules\\foo", ["node_modules"]) is True

    def test_no_match(self):
        assert jm.should_exclude("keep.txt", ["*.log"]) is False

    def test_empty_patterns(self):
        assert jm.should_exclude("a.txt", []) is False


class TestCollectFiles:
    def test_single_file(self, tmp_path):
        f = tmp_path / "a.jar"
        f.write_text("x")
        assert jm.collect_files(str(f)) == [str(f)]

    def test_single_file_excluded(self, tmp_path):
        f = tmp_path / "a.log"
        f.write_text("x")
        assert jm.collect_files(str(f), ["*.log"]) == []

    def test_tree_with_excludes(self, tmp_path):
        (tmp_path / "a.txt").write_text("1")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("2")
        (tmp_path / "x.log").write_text("3")
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "c.js").write_text("4")
        files = jm.collect_files(str(tmp_path), ["*.log", "node_modules"])
        names = sorted(os.path.relpath(f, str(tmp_path)) for f in files)
        assert names == ["a.txt", os.path.join("sub", "b.txt")]


class TestScanLocalFiles:
    def test_single_file_key_is_empty(self, tmp_path):
        f = tmp_path / "a.jar"
        f.write_text("hello")
        files = jm.scan_local_files(str(f))
        assert "" in files and files[""]["size"] == 5
        assert isinstance(files[""]["mtime"], float)

    def test_dir(self, tmp_path):
        (tmp_path / "a.txt").write_text("1")
        files = jm.scan_local_files(str(tmp_path))
        assert set(files) == {"a.txt"}
        assert files["a.txt"]["size"] == 1

    def test_excluded_dir_pruned(self, tmp_path):
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "x.js").write_text("1")
        (tmp_path / "k.txt").write_text("2")
        files = jm.scan_local_files(str(tmp_path), ["node_modules"])
        assert set(files) == {"k.txt"}

    def test_stat_oserror_skipped(self, tmp_path, monkeypatch):
        d = tmp_path / "d"
        d.mkdir()
        (d / "a.txt").write_text("x")
        real_stat = os.stat

        def flaky(p, *a, **k):
            if str(p).endswith("a.txt"):
                raise OSError("boom")
            return real_stat(p, *a, **k)

        monkeypatch.setattr(os, "stat", flaky)
        assert jm.scan_local_files(str(d)) == {}

    def test_file_exclude_skips_entry(self, tmp_path):
        (tmp_path / "a.txt").write_text("1")
        (tmp_path / "b.log").write_text("2")
        files = jm.scan_local_files(str(tmp_path), ["*.log"])
        assert set(files) == {"a.txt"}


class TestBuildSshOpts:
    def test_defaults(self):
        opts = jm.build_ssh_opts()
        assert opts[0] == "-o"
        assert "StrictHostKeyChecking=no" in opts
        assert "UserKnownHostsFile=/dev/null" in opts
        # 默认 300s 被 cap 到 30
        assert "ConnectTimeout=30" in opts
        assert "Port=22" in opts
        assert "-i" not in opts

    def test_timeout_capped_at_30(self):
        assert "ConnectTimeout=30" in jm.build_ssh_opts(timeout=600)

    def test_key_used_when_exists(self, tmp_path):
        key = tmp_path / "id_rsa"
        key.write_text("key")
        opts = jm.build_ssh_opts(key_path=str(key))
        i = opts.index("-i")
        assert opts[i + 1] == str(key)

    def test_key_ignored_when_missing(self, tmp_path):
        opts = jm.build_ssh_opts(key_path=str(tmp_path / "nope"))
        assert "-i" not in opts

    def test_port(self):
        assert "Port=2222" in jm.build_ssh_opts(port=2222)


# ═══════════════ SSH 路扫描 ═══════════════

class _CmdResult:
    def __init__(self, rc=0, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


class TestScanRemoteFiles:
    def test_error_returncode(self, monkeypatch):
        monkeypatch.setattr(jm, "run_cmd_safe",
                            lambda *a, **k: _CmdResult(rc=1, err="perm"))
        out = jm.scan_remote_files("/r", "h", "u")
        assert out == {"__error__": "perm"}

    def test_exception(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("ssh missing")
        monkeypatch.setattr(jm, "run_cmd_safe", boom)
        out = jm.scan_remote_files("/r", "h", "u")
        assert "__error__" in out and "ssh missing" in out["__error__"]

    def test_parse_lines(self, monkeypatch):
        stdout = ("1719600000.0 5 /r/a.txt\n"
                  "1719600001.0 7 /r/sub/b.txt\n")
        monkeypatch.setattr(jm, "run_cmd_safe",
                            lambda *a, **k: _CmdResult(out=stdout))
        files = jm.scan_remote_files("/r", "h", "u")
        assert set(files) == {"a.txt", "sub/b.txt"}
        assert files["a.txt"] == {"size": 5, "mtime": 1719600000.0}

    def test_malformed_and_bad_lines_skipped(self, monkeypatch):
        stdout = "\nshort\nabc def /r/p\n1719600000.0 5 /r/ok.txt\n"
        monkeypatch.setattr(jm, "run_cmd_safe",
                            lambda *a, **k: _CmdResult(out=stdout))
        files = jm.scan_remote_files("/r", "h", "u")
        assert set(files) == {"ok.txt"}

    def test_unsafe_relpath_skipped(self, monkeypatch):
        stdout = "1719600000.0 5 /r/../escape.txt\n"
        monkeypatch.setattr(jm, "run_cmd_safe",
                            lambda *a, **k: _CmdResult(out=stdout))
        assert jm.scan_remote_files("/r", "h", "u") == {}

    def test_exclude_applied(self, monkeypatch):
        stdout = ("1719600000.0 5 /r/a.log\n"
                  "1719600000.0 5 /r/b.txt\n")
        monkeypatch.setattr(jm, "run_cmd_safe",
                            lambda *a, **k: _CmdResult(out=stdout))
        files = jm.scan_remote_files("/r", "h", "u", exclude=["*.log"])
        assert set(files) == {"b.txt"}

    def test_ssh_command_shape(self, monkeypatch):
        seen = {}

        def fake(cmd, timeout=None, **k):
            seen["cmd"] = cmd
            return _CmdResult(out="")

        monkeypatch.setattr(jm, "run_cmd_safe", fake)
        jm.scan_remote_files("/r p", "h", "u", port=2222)
        cmd = seen["cmd"]
        assert cmd[0] == "ssh"
        assert "Port=2222" in cmd
        # 路径必须被 shquote（含空格不拆词）
        assert "find '/r p'" in cmd[-1]


# ═══════════════ 同步计划 ═══════════════

L1 = {"a.txt": {"size": 1, "mtime": 1000.0}}
R1 = {"a.txt": {"size": 1, "mtime": 1000.0}}


class TestComputeSyncPlan:
    def test_same_file_same_stat_skipped(self):
        p = jm.compute_sync_plan(L1, dict(R1))
        assert p == {"upload": [], "download": [], "conflict": [], "skip": ["a.txt"], "delete": []}

    def test_mtime_within_tolerance_skipped(self):
        p = jm.compute_sync_plan(L1, {"a.txt": {"size": 1, "mtime": 1001.5}})
        assert p["skip"] == ["a.txt"]

    def test_upload_only_local(self):
        p = jm.compute_sync_plan({"n.txt": L1["a.txt"]}, {})
        assert p["upload"] == ["n.txt"]

    def test_local_only_direction_download_goes_to_skip(self):
        p = jm.compute_sync_plan(L1, {}, direction="download")
        assert p["upload"] == [] and p["skip"] == ["a.txt"]

    def test_remote_only_download(self):
        p = jm.compute_sync_plan({}, R1, direction="download")
        assert p["download"] == ["a.txt"]

    def test_remote_only_upload_with_delete(self):
        p = jm.compute_sync_plan({}, R1, direction="upload", delete=True)
        assert p["delete"] == ["a.txt"]

    def test_remote_only_upload_no_delete_skips(self):
        p = jm.compute_sync_plan({}, R1, direction="upload", delete=False)
        assert p["skip"] == ["a.txt"] and p["delete"] == []

    def test_conflict_both_direction(self):
        p = jm.compute_sync_plan(L1, {"a.txt": {"size": 9, "mtime": 900.0}})
        assert len(p["conflict"]) == 1
        c = p["conflict"][0]
        assert c["relpath"] == "a.txt"
        assert c["local"]["size"] == 1 and c["remote"]["size"] == 9

    def test_conflict_direction_upload(self):
        p = jm.compute_sync_plan(L1, {"a.txt": {"size": 9, "mtime": 900.0}},
                                 direction="upload")
        assert p["upload"] == ["a.txt"] and p["conflict"] == []

    def test_conflict_direction_download(self):
        p = jm.compute_sync_plan(L1, {"a.txt": {"size": 9, "mtime": 900.0}},
                                 direction="download")
        assert p["download"] == ["a.txt"] and p["conflict"] == []

    def test_all_keys_present(self):
        p = jm.compute_sync_plan({}, {})
        assert set(p) == {"upload", "download", "conflict", "skip", "delete"}


# ═══════════════ 单文件传输 ═══════════════

class TestUploadSingle:
    def test_ok(self, monkeypatch, tmp_path):
        f = tmp_path / "a.jar"
        f.write_text("x")
        seen = {}

        def fake(cmd, timeout=None, **k):
            seen["cmd"] = cmd
            return _CmdResult()

        monkeypatch.setattr(jm, "run_cmd_safe", fake)
        assert jm.upload_single(str(f), "/r/a.jar", "h", "u") is True
        cmd = seen["cmd"]
        assert cmd[0] == "scp"
        assert cmd[-2] == str(f)
        assert cmd[-1] == "u@h:/r"

    def test_rc_nonzero(self, monkeypatch, tmp_path):
        f = tmp_path / "a.jar"
        f.write_text("x")
        monkeypatch.setattr(jm, "run_cmd_safe",
                            lambda cmd, **k: _CmdResult(rc=1, err="denied"))
        assert jm.upload_single(str(f), "/r/a.jar", "h", "u") is False

    def test_exception_false(self, monkeypatch, tmp_path):
        f = tmp_path / "a.jar"
        f.write_text("x")
        monkeypatch.setattr(jm, "run_cmd_safe",
                            lambda cmd, **k: (_ for _ in ()).throw(RuntimeError("x")))
        assert jm.upload_single(str(f), "/r/a.jar", "h", "u") is False


class TestDownloadSingle:
    def test_ok_creates_parent(self, monkeypatch, tmp_path):
        target = tmp_path / "sub" / "out.bin"
        monkeypatch.setattr(jm, "run_cmd_safe", lambda cmd, **k: _CmdResult())
        assert jm.download_single("/r/in.bin", str(target), "h", "u") is True
        assert (tmp_path / "sub").is_dir()
        monkeypatch.undo()
        cmd_ok = None

    def test_rc_nonzero_false(self, monkeypatch, tmp_path):
        target = tmp_path / "out.bin"
        monkeypatch.setattr(jm, "run_cmd_safe",
                            lambda cmd, **k: _CmdResult(rc=255))
        assert jm.download_single("/r/in.bin", str(target), "h", "u") is False

    def test_exception_false(self, monkeypatch, tmp_path):
        target = tmp_path / "out.bin"
        monkeypatch.setattr(jm, "run_cmd_safe",
                            lambda cmd, **k: (_ for _ in ()).throw(RuntimeError("x")))
        assert jm.download_single("/r/in.bin", str(target), "h", "u") is False


# ═══════════════ 批量传输 ═══════════════

class TestBatchUpload:
    def test_mixed(self, monkeypatch, tmp_path):
        (tmp_path / "a.txt").write_text("1")
        calls = []

        def fake_up(l, r, *a, **k):
            calls.append((l, r))
            return r.endswith("ok.txt")

        monkeypatch.setattr(jm, "upload_single", fake_up)
        out = jm.batch_upload(["ok.txt", "bad.txt", "../evil"],
                              str(tmp_path), "/r", "h", "u")
        assert out["count"] == 1
        assert out["errors"] == ["上传失败: bad.txt",
                                 "拒绝不安全相对路径: ../evil"]
        # 两条安全路径都被尝试；不安全条目在拼接前就被拒绝
        assert calls == [(os.path.join(str(tmp_path), "ok.txt"), "/r/ok.txt"),
                         (os.path.join(str(tmp_path), "bad.txt"), "/r/bad.txt")]

    def test_empty(self, monkeypatch):
        monkeypatch.setattr(jm, "upload_single", lambda *a, **k: True)
        assert jm.batch_upload([], "/l", "/r", "h", "u") == {"count": 0, "errors": []}


class TestBatchDownload:
    def test_mixed(self, monkeypatch, tmp_path):
        calls = []

        def fake_dl(r, l, *a, **k):
            calls.append((r, l))
            return False

        monkeypatch.setattr(jm, "download_single", fake_dl)
        out = jm.batch_download(["ok.txt", "C:/abs"],
                                str(tmp_path), "/r", "h", "u")
        assert out["count"] == 0
        assert out["errors"] == ["下载失败: ok.txt",
                                 "拒绝不安全相对路径: C:/abs"]
        assert calls == [("/r/ok.txt", os.path.join(str(tmp_path), "ok.txt"))]


# ═══════════════ 冲突解决 ═══════════════

def _conflict(local_mtime=1000.0, remote_mtime=900.0):
    return {"relpath": "a.txt",
            "local": {"size": 1, "mtime": local_mtime},
            "remote": {"size": 1, "mtime": remote_mtime}}


class TestResolveConflict:
    def test_unsafe_relpath_false(self, monkeypatch):
        monkeypatch.setattr(jm, "upload_single",
                            lambda *a, **k: pytest.fail("不应调用"))
        assert jm.resolve_conflict({"relpath": "../x", "local": {}, "remote": {}},
                                   "/l", "/r", "h", "u") is False

    def test_newer_local_uploads(self, monkeypatch):
        seen = []
        monkeypatch.setattr(jm, "upload_single", lambda *a, **k: seen.append("up") or True)
        monkeypatch.setattr(jm, "download_single", lambda *a, **k: pytest.fail("不应下载"))
        assert jm.resolve_conflict(_conflict(1000.0, 900.0), "/l", "/r", "h", "u") is True
        assert seen == ["up"]

    def test_newer_remote_downloads(self, monkeypatch):
        monkeypatch.setattr(jm, "upload_single", lambda *a, **k: pytest.fail("不应上传"))
        monkeypatch.setattr(jm, "download_single", lambda *a, **k: True)
        assert jm.resolve_conflict(_conflict(900.0, 1000.0), "/l", "/r", "h", "u") is True

    def test_strategy_local(self, monkeypatch):
        monkeypatch.setattr(jm, "upload_single", lambda *a, **k: True)
        monkeypatch.setattr(jm, "download_single", lambda *a, **k: pytest.fail("不应下载"))
        assert jm.resolve_conflict(_conflict(1.0, 9999.0), "/l", "/r", "h", "u",
                                   strategy="local") is True

    def test_strategy_remote(self, monkeypatch):
        monkeypatch.setattr(jm, "upload_single", lambda *a, **k: pytest.fail("不应上传"))
        monkeypatch.setattr(jm, "download_single", lambda *a, **k: True)
        assert jm.resolve_conflict(_conflict(9999.0, 1.0), "/l", "/r", "h", "u",
                                   strategy="remote") is True

    def test_unknown_strategy_false(self, monkeypatch):
        monkeypatch.setattr(jm, "upload_single", lambda *a, **k: pytest.fail("不应调用"))
        monkeypatch.setattr(jm, "download_single", lambda *a, **k: pytest.fail("不应调用"))
        assert jm.resolve_conflict(_conflict(), "/l", "/r", "h", "u",
                                   strategy="coin-flip") is False


# ═══════════════ push / pull / sync 分派 ═══════════════

class TestPush:
    def test_source_missing_error(self, tmp_path):
        out = jm.push(str(tmp_path / "nope"), "/r", "h", "u")
        assert out["status"] == "error"
        assert "本地路径不存在" in out["message"]

    def test_empty_dir_ok_zero(self, tmp_path):
        out = jm.push(str(tmp_path), "/r", "h", "u")
        assert out["status"] == "ok"
        assert out["files_transferred"] == 0 and out["bytes"] == 0

    def test_dry_run(self, tmp_path):
        (tmp_path / "a.txt").write_text("1")
        out = jm.push(str(tmp_path), "/r", "h", "u", dry_run=True)
        assert out["status"] == "ok" and out["dry_run"] is True
        assert out["total_files"] == 1 and out["files"] == [str(tmp_path / "a.txt")]
        assert out["files_transferred"] == 0

    def test_dispatch_paramiko(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")
        monkeypatch.setattr(jm, "_push_paramiko",
                            lambda *a, **k: {"status": "ok", "via": "paramiko"})
        assert jm.push(str(tmp_path), "/r", "h", "u")["via"] == "paramiko"

    def test_dispatch_sftp_alias(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")
        monkeypatch.setattr(jm, "_push_paramiko", lambda *a, **k: {"via": "sftp"})
        assert jm.push(str(tmp_path), "/r", "h", "u", method="sftp")["via"] == "sftp"

    def test_dispatch_tar_ssh(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")
        monkeypatch.setattr(jm, "_push_tar_ssh", lambda *a, **k: {"via": "tar"})
        assert jm.push(str(tmp_path), "/r", "h", "u", method="tar+ssh")["via"] == "tar"

    def test_dispatch_scp_default_other(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")
        monkeypatch.setattr(jm, "_push_scp", lambda *a, **k: {"via": "scp"})
        assert jm.push(str(tmp_path), "/r", "h", "u", method="scp")["via"] == "scp"


class TestPull:
    def test_dry_run_shape(self, tmp_path):
        out = jm.pull("/r", str(tmp_path / "out"), "h", "u", dry_run=True,
                      method="tar+ssh")
        assert out == {"status": "ok", "files_transferred": 0, "bytes": 0,
                       "dry_run": True, "transport": "tar+ssh",
                       "message": "预览模式"}
        # dry_run 零副作用：不建目录
        assert not (tmp_path / "out").exists()

    def test_real_run_creates_local_dir_and_dispatches(self, tmp_path, monkeypatch):
        seen = {}
        monkeypatch.setattr(jm, "_pull_paramiko",
                            lambda *a, **k: seen.setdefault("called", True) or {})
        out = jm.pull("/r", str(tmp_path / "out"), "h", "u")
        assert (tmp_path / "out").is_dir()
        assert seen["called"] is True

    def test_dispatch_tar_ssh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jm, "_pull_tar_ssh", lambda *a, **k: {"via": "tar"})
        assert jm.pull("/r", str(tmp_path), "h", "u", method="tar+ssh")["via"] == "tar"

    def test_dispatch_scp(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jm, "_pull_scp", lambda *a, **k: {"via": "scp"})
        assert jm.pull("/r", str(tmp_path), "h", "u", method="scp")["via"] == "scp"


class TestSync:
    def test_dispatch_paramiko(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jm, "_sync_paramiko",
                            lambda *a, **k: {"status": "ok", "via": "p"})
        out = jm.sync(str(tmp_path), "/r", "h", "u", method="paramiko")
        assert out["via"] == "p"

    def test_remote_scan_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jm, "scan_remote_files",
                            lambda *a, **k: {"__error__": "no find"})
        out = jm.sync(str(tmp_path), "/r", "h", "u", method="scp")
        assert out == {"status": "error", "message": "no find"}

    def test_dry_run_counts(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")
        monkeypatch.setattr(jm, "scan_remote_files",
                            lambda *a, **k: {"b.txt": {"size": 2, "mtime": 1.0}})
        out = jm.sync(str(tmp_path), "/r", "h", "u", method="scp", dry_run=True)
        assert out["status"] == "ok" and out["dry_run"] is True
        assert out["upload"] == 1 and out["download"] == 1

    def test_full_flow_partial_on_errors(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")
        monkeypatch.setattr(jm, "scan_remote_files", lambda *a, **k: {})
        monkeypatch.setattr(jm, "batch_upload",
                            lambda *a, **k: {"count": 1, "errors": ["上传失败: a.txt"]})
        out = jm.sync(str(tmp_path), "/r", "h", "u", method="scp")
        assert out["status"] == "partial"
        assert out["uploaded"] == 1 and out["errors"] == ["上传失败: a.txt"]

    def test_clean_run_ok(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")
        monkeypatch.setattr(jm, "scan_remote_files", lambda *a, **k: {})
        monkeypatch.setattr(jm, "batch_upload",
                            lambda *a, **k: {"count": 1, "errors": []})
        out = jm.sync(str(tmp_path), "/r", "h", "u", method="scp")
        assert out["status"] == "ok"
        assert out == {"status": "ok", "uploaded": 1, "downloaded": 0,
                       "conflicts": 0, "errors": []}

    def test_bug_j1_delete_ignored_on_ssh_path(self, tmp_path, monkeypatch):
        """BUG-J1 佐证：非 paramiko 路径 compute_sync_plan 未收到 delete。

        sync(delete=True, method="scp") → 捕获到的 delete 仍是默认 False；
        远端独有文件被静默 skip 而不是按承诺删除（paramiko 路径会传）。
        修 BUG 后：delete 应为 True，且本断言要改。
        """
        captured = {}

        real_plan = jm.compute_sync_plan

        def spy_plan(local, remote, direction="both", strategy="newer", delete=False):
            captured["delete"] = delete
            return real_plan(local, remote, direction, strategy, delete)

        monkeypatch.setattr(jm, "compute_sync_plan", spy_plan)
        monkeypatch.setattr(jm, "scan_remote_files", lambda *a, **k: {})
        monkeypatch.setattr(jm, "batch_upload", lambda *a, **k: {"count": 0, "errors": []})
        jm.sync(str(tmp_path), "/r", "h", "u", method="scp", delete=True)
        assert captured["delete"] is False  # ← BUG：承诺 True 却没传

    def test_conflicts_resolved_counted(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")
        monkeypatch.setattr(jm, "scan_remote_files",
                            lambda *a, **k: {"a.txt": {"size": 9, "mtime": 1.0}})
        monkeypatch.setattr(jm, "batch_upload", lambda *a, **k: {"count": 0, "errors": []})
        monkeypatch.setattr(jm, "batch_download", lambda *a, **k: {"count": 0, "errors": []})
        monkeypatch.setattr(jm, "resolve_conflict", lambda *a, **k: True)
        out = jm.sync(str(tmp_path), "/r", "h", "u", method="scp")
        assert out["conflicts"] == 1

    def test_download_branch_counted(self, tmp_path, monkeypatch):
        """远端独有文件 → 走 batch_download 分支并计入 downloaded（行 495-498）。"""
        monkeypatch.setattr(jm, "scan_remote_files",
                            lambda *a, **k: {"b.txt": {"size": 2, "mtime": 1.0}})
        calls = []
        monkeypatch.setattr(jm, "batch_download",
                            lambda files, *a, **k: calls.append(files) or
                            {"count": 1, "errors": []})
        out = jm.sync(str(tmp_path), "/r", "h", "u", method="scp")
        assert out["status"] == "ok"
        assert out["downloaded"] == 1 and out["uploaded"] == 0
        assert calls == [["b.txt"]]


class TestBatchDownloadSuccess:
    def test_ok(self, monkeypatch, tmp_path):
        monkeypatch.setattr(jm, "download_single", lambda r, l, *a, **k: True)
        out = jm.batch_download(["a.txt"], str(tmp_path), "/r", "h", "u")
        assert out == {"count": 1, "errors": []}


# ═══════════════ scp / tar+ssh 实现 ═══════════════

class TestPushScp:
    def test_ok(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1234")
        (tmp_path / "b.txt").write_text("12")
        calls = []

        def fake(cmd, **k):
            calls.append(cmd)
            return _CmdResult()

        monkeypatch.setattr(jm, "run_cmd_safe", fake)
        files = jm.collect_files(str(tmp_path))
        out = jm._push_scp(str(tmp_path), "/r", "h", "u", 22, None, None, files, 300)
        assert out["status"] == "ok"
        assert out["files_transferred"] == 2 and out["bytes"] == 6
        # 先建远端目录（scp 不自建）
        assert calls[0][0] == "ssh" and calls[0][-1] == "mkdir -p '/r'"
        assert calls[1][0] == "scp"

    def test_scp_fail(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")
        calls = []

        def fake(cmd, **k):
            calls.append(cmd)
            return _CmdResult(rc=1, err="denied") if cmd[0] == "scp" else _CmdResult()

        monkeypatch.setattr(jm, "run_cmd_safe", fake)
        out = jm._push_scp(str(tmp_path), "/r", "h", "u", 22, None, None,
                           jm.collect_files(str(tmp_path)), 300)
        assert out["status"] == "error" and "denied" in out["message"]

    def test_scp_exception(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")

        def fake(cmd, **k):
            if cmd[0] == "scp":
                raise RuntimeError("boom")
            return _CmdResult()

        monkeypatch.setattr(jm, "run_cmd_safe", fake)
        out = jm._push_scp(str(tmp_path), "/r", "h", "u", 22, None, None,
                           jm.collect_files(str(tmp_path)), 300)
        assert out["status"] == "error" and "boom" in out["message"]

    def test_bug_j4_mkdir_ssh_outside_try(self, tmp_path, monkeypatch):
        """BUG-J4 佐证：mkdir ssh 在 try 之外，ssh 不可达 → 裸异常冲出。

        _push_tar_ssh/_push_paramiko 连接失败都返回 {"status": "error"}，
        只有 scp 路径让异常穿透到 push()（push 无 try）→ 调用方拿到的是
        异常而不是错误 dict。修 BUG 后改为返回 error dict，本断言要改。
        """
        (tmp_path / "a.txt").write_text("1")

        def fake(cmd, **k):
            if cmd[0] == "ssh":
                raise RuntimeError("ssh down")
            return _CmdResult()

        monkeypatch.setattr(jm, "run_cmd_safe", fake)
        with pytest.raises(RuntimeError, match="ssh down"):
            jm._push_scp(str(tmp_path), "/r", "h", "u", 22, None, None,
                         jm.collect_files(str(tmp_path)), 300)


class _FakeProc:
    def __init__(self, rc=0, comm_exc=None):
        self.returncode = rc
        self._comm_exc = comm_exc
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()

    def communicate(self, timeout=None):
        if self._comm_exc:
            raise self._comm_exc
        return (b"", b"")

    def wait(self, timeout=None):
        return self.returncode


class TestPushTarSsh:
    def _setup(self, tmp_path, monkeypatch, tar_rc=0, ssh_rc=0,
               ssh_comm_exc=None, ssh_popen_exc=None):
        (tmp_path / "a.txt").write_text("hello")
        made, killed = [], []

        def fake_popen(cmd, **kw):
            made.append(cmd[0])
            if cmd[0] == "ssh" and ssh_popen_exc:
                raise ssh_popen_exc
            if cmd[0] == "ssh":
                return _FakeProc(rc=ssh_rc, comm_exc=ssh_comm_exc)
            return _FakeProc(rc=tar_rc)

        monkeypatch.setattr(jm.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(jm, "kill_tree", lambda p: killed.append(p))
        return made, killed

    def test_ok(self, tmp_path, monkeypatch):
        made, killed = self._setup(tmp_path, monkeypatch)
        out = jm._push_tar_ssh(str(tmp_path), "/r", "h", "u", 22, None, None,
                               ["*.log"], 300)
        assert out["status"] == "ok"
        assert out["files_transferred"] == 1 and out["bytes"] == 5
        assert made == ["tar", "ssh"]
        # 单文件/目录两种 -C 形态：目录是 -C <path> .
        tar_cmd_made = None

    def test_tar_cmd_shape_single_file(self, tmp_path, monkeypatch):
        f = tmp_path / "one.jar"
        f.write_text("x")
        cmds = []

        def fake_popen(cmd, **kw):
            cmds.append(cmd)
            return _FakeProc(rc=0)

        monkeypatch.setattr(jm.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(jm, "kill_tree", lambda p: None)
        jm._push_tar_ssh(str(f), "/r", "h", "u", 22, None, None, [], 300)
        tar_cmd = cmds[0]
        i = tar_cmd.index("-C")
        assert tar_cmd[i + 1] == str(tmp_path)
        assert tar_cmd[i + 2] == "one.jar"
        assert cmds[1][0] == "ssh"
        # 远端命令已引用 + mkdir
        remote_cmd = cmds[1][-1]
        assert "mkdir -p '/r'" in remote_cmd and "tar xzf - -C '/r'" in remote_cmd

    def test_exclude_flags_forwarded(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("x")
        cmds = []

        def fake_popen(cmd, **kw):
            cmds.append(cmd)
            return _FakeProc(rc=0)

        monkeypatch.setattr(jm.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(jm, "kill_tree", lambda p: None)
        jm._push_tar_ssh(str(tmp_path), "/r", "h", "u", 22, None, None,
                         ["*.log", "a b"], 300)
        tar_cmd = cmds[0]
        i = tar_cmd.index("--exclude")
        assert tar_cmd[i + 1] == "*.log"
        # 含空格的 pattern 也作为单参数转发（tar 自身不经 shell）
        j = tar_cmd.index("a b")
        assert tar_cmd[j] == "a b"

    def test_ssh_fail(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch, ssh_rc=1)
        out = jm._push_tar_ssh(str(tmp_path), "/r", "h", "u", 22, None, None, [], 300)
        assert out == {"status": "error", "message": "ssh 失败"}

    def test_tar_fail(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch, tar_rc=2)
        out = jm._push_tar_ssh(str(tmp_path), "/r", "h", "u", 22, None, None, [], 300)
        assert out["status"] == "error"
        assert "打包失败" in out["message"] and "2" in out["message"]

    def test_timeout_kills_both(self, tmp_path, monkeypatch):
        made, killed = self._setup(tmp_path, monkeypatch,
                                   ssh_comm_exc=subprocess_timeout())
        out = jm._push_tar_ssh(str(tmp_path), "/r", "h", "u", 22, None, None, [], 300)
        assert out["status"] == "error" and "传输超时" in out["message"]
        assert len(killed) == 2  # ssh + tar 都要杀

    def test_ssh_popen_failure_kills_tar(self, tmp_path, monkeypatch):
        made, killed = self._setup(tmp_path, monkeypatch,
                                   ssh_popen_exc=OSError("no ssh"))
        out = jm._push_tar_ssh(str(tmp_path), "/r", "h", "u", 22, None, None, [], 300)
        assert out["status"] == "error" and "no ssh" in out["message"]
        assert len(killed) == 1  # tar 被补杀，防孤儿进程写满管道


def subprocess_timeout():
    import subprocess as _sp
    return _sp.TimeoutExpired(cmd="ssh", timeout=0.1)


class TestPullTarSsh:
    def _setup(self, tmp_path, monkeypatch, tar_rc=0, ssh_rc=0,
               tar_comm_exc=None, tar_popen_exc=None):
        made, killed = [], []

        def fake_popen(cmd, **kw):
            made.append(cmd[0])
            if cmd[0] == "tar" and tar_popen_exc:
                raise tar_popen_exc
            if cmd[0] == "tar":
                return _FakeProc(rc=tar_rc, comm_exc=tar_comm_exc)
            return _FakeProc(rc=ssh_rc)

        monkeypatch.setattr(jm.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(jm, "kill_tree", lambda p: killed.append(p))
        return made, killed

    def test_ok(self, tmp_path, monkeypatch):
        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "x.bin").write_text("abcd")
        self._setup(tmp_path, monkeypatch)
        out = jm._pull_tar_ssh("/r", str(tmp_path / "out"), "h", "u", 22,
                               None, None, [], 300)
        assert out["status"] == "ok"
        assert out["files_transferred"] == 1 and out["bytes"] == 4

    def test_exclude_quoted_with_shquote(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        cmds = []
        old = jm.subprocess.Popen
        monkeypatch.setattr(jm.subprocess, "Popen",
                            lambda cmd, **k: cmds.append(cmd) or _FakeProc())
        jm._pull_tar_ssh("/r", str(tmp_path / "out"), "h", "u", 22, None, None,
                         ["a b"], 300)
        ssh_cmd = cmds[0]
        assert "--exclude 'a b'" in ssh_cmd[-1]

    def test_tar_fail(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch, tar_rc=2)
        out = jm._pull_tar_ssh("/r", str(tmp_path / "out"), "h", "u", 22,
                               None, None, [], 300)
        assert out == {"status": "error", "message": "解压失败"}

    def test_timeout_kills_both(self, tmp_path, monkeypatch):
        made, killed = self._setup(tmp_path, monkeypatch,
                                   tar_comm_exc=subprocess_timeout())
        out = jm._pull_tar_ssh("/r", str(tmp_path / "out"), "h", "u", 22,
                               None, None, [], 300)
        assert out["status"] == "error" and "传输超时" in out["message"]
        assert len(killed) == 2

    def test_tar_popen_failure_kills_ssh(self, tmp_path, monkeypatch):
        made, killed = self._setup(tmp_path, monkeypatch,
                                   tar_popen_exc=OSError("no tar"))
        out = jm._pull_tar_ssh("/r", str(tmp_path / "out"), "h", "u", 22,
                               None, None, [], 300)
        assert out["status"] == "error" and "no tar" in out["message"]
        assert len(killed) == 1

    def test_bug_j3_ssh_failure_still_ok(self, tmp_path, monkeypatch):
        """BUG-J3 佐证：ssh rc=1（空流）+ tar rc=0 → 仍报 ok。

        push 侧双检（ssh + tar），pull 侧只检 tar —— 不对称。
        ssh 失败时 tar 收到 EOF 正常退出，半截/零文件也按成功返回。
        修 BUG 后：应返回 error，本断言要改。
        """
        self._setup(tmp_path, monkeypatch, ssh_rc=1)
        out = jm._pull_tar_ssh("/r", str(tmp_path / "out"), "h", "u", 22,
                               None, None, [], 300)
        assert out["status"] == "ok"  # ← BUG：ssh 失败被吞


class TestPullScp:
    def test_ok_counts_local_tree(self, tmp_path, monkeypatch):
        outdir = tmp_path / "out"
        outdir.mkdir()
        (outdir / "a.txt").write_text("123")
        (outdir / "sub").mkdir()
        (outdir / "sub" / "b.txt").write_text("12")
        monkeypatch.setattr(jm, "run_cmd_safe", lambda cmd, **k: _CmdResult())
        out = jm._pull_scp("/r", str(outdir), "h", "u", 22, None, None, 300)
        assert out["status"] == "ok"
        assert out["files_transferred"] == 2 and out["bytes"] == 5

    def test_fail(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jm, "run_cmd_safe",
                            lambda cmd, **k: _CmdResult(rc=1, err="no"))
        out = jm._pull_scp("/r", str(tmp_path), "h", "u", 22, None, None, 300)
        assert out["status"] == "error" and out["message"] == "no"

    def test_exception(self, tmp_path, monkeypatch):
        monkeypatch.setattr(jm, "run_cmd_safe",
                            lambda cmd, **k: (_ for _ in ()).throw(RuntimeError("x")))
        out = jm._pull_scp("/r", str(tmp_path), "h", "u", 22, None, None, 300)
        assert out["status"] == "error" and "x" in out["message"]


# ═══════════════ paramiko 基础设施 ═══════════════

class TestImportParamiko:
    def test_missing_gives_hint(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "paramiko", None)
        mod, err = jm._import_paramiko()
        assert mod is None
        assert "pip install paramiko" in err
        assert "tar+ssh" in err

    def test_present(self):
        import importlib.util
        if importlib.util.find_spec("paramiko") is None:
            pytest.skip("paramiko not installed")
        mod, err = jm._import_paramiko()
        assert mod is not None and err is None


class TestPatchParamikoDecoding:
    def _fake_message_mod(self):
        mod = types.ModuleType("paramiko.message")

        class Message:
            payload = b""

            def get_string(self):
                return self.payload

            def get_text(self):
                return "orig"

        mod.Message = Message
        return mod, Message

    def test_patch_and_idempotent(self, monkeypatch):
        mod, Message = self._fake_message_mod()
        monkeypatch.setitem(sys.modules, "paramiko", types.ModuleType("paramiko"))
        monkeypatch.setitem(sys.modules, "paramiko.message", mod)
        assert jm._patch_paramiko_filename_decoding() is True
        assert getattr(Message.get_text, "_actus_surrogateescape", False) is True
        # 合法 utf-8 不受影响
        m = Message()
        m.payload = "ok".encode()
        assert m.get_text() == "ok"
        # 非法字节 → surrogateescape 保留原字节可往返
        m.payload = b"\xff\xfe"
        decoded = m.get_text()
        assert decoded.encode("utf-8", "surrogateescape") == b"\xff\xfe"
        # 幂等：二次调用直接 True
        assert jm._patch_paramiko_filename_decoding() is True

    def test_import_failure_false(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "paramiko", types.ModuleType("paramiko"))
        monkeypatch.setitem(sys.modules, "paramiko.message", None)
        assert jm._patch_paramiko_filename_decoding() is False


class FakeSSHClient:
    fail_connect = False
    fail_open_sftp = False
    instances = []

    def __init__(self):
        self.closed = False
        self.kwargs = None
        self._sftp = object()
        FakeSSHClient.instances.append(self)

    def set_missing_host_key_policy(self, p):
        self.policy = p

    def connect(self, **kw):
        self.kwargs = kw
        if FakeSSHClient.fail_connect:
            raise RuntimeError("refused")

    def open_sftp(self):
        if FakeSSHClient.fail_open_sftp:
            raise RuntimeError("chan")
        return self._sftp

    def close(self):
        if getattr(FakeSSHClient, "close_exc", None):
            raise FakeSSHClient.close_exc
        self.closed = True


class TestSftpConnect:
    def _fake_paramiko(self, monkeypatch):
        fake = types.ModuleType("paramiko")
        fake.SSHClient = FakeSSHClient
        fake.AutoAddPolicy = lambda: object()
        monkeypatch.setattr(jm, "_import_paramiko", lambda: (fake, None))
        FakeSSHClient.instances = []

    def test_success(self, monkeypatch):
        self._fake_paramiko(monkeypatch)
        pair, err = jm._sftp_connect("h", "u", 22, None, None, 300)
        assert err is None
        client, sftp = pair
        assert isinstance(client, FakeSSHClient)
        kw = client.kwargs
        assert kw["hostname"] == "h" and kw["username"] == "u"
        assert kw["port"] == 22 and kw["timeout"] == 300
        assert kw["allow_agent"] is True and kw["look_for_keys"] is True

    def test_password_and_key(self, monkeypatch, tmp_path):
        self._fake_paramiko(monkeypatch)
        key = tmp_path / "id_rsa"
        key.write_text("k")
        _, err = jm._sftp_connect("h", "u", 22, str(key), "pw", 300)
        assert err is None
        kw = FakeSSHClient.instances[-1].kwargs
        assert kw["password"] == "pw" and kw["key_filename"] == str(key)

    def test_key_missing_not_passed(self, monkeypatch):
        self._fake_paramiko(monkeypatch)
        _, err = jm._sftp_connect("h", "u", 22, "/no/key", None, 300)
        assert err is None
        assert "key_filename" not in FakeSSHClient.instances[-1].kwargs

    def test_connect_failure_closes_client(self, monkeypatch):
        self._fake_paramiko(monkeypatch)
        FakeSSHClient.fail_connect = True
        FakeSSHClient.close_exc = RuntimeError("close boom")
        try:
            pair, err = jm._sftp_connect("h", "u", 22, None, None, 300)
            assert pair is None
            assert err["status"] == "error"
            assert "SSH 连接失败" in err["message"]
            # close() 自身抛异常被吞，不影响返回 error dict
            assert FakeSSHClient.instances[-1].closed is False
        finally:
            FakeSSHClient.fail_connect = False
            FakeSSHClient.close_exc = None

    def test_open_sftp_failure_closes_client(self, monkeypatch):
        self._fake_paramiko(monkeypatch)
        FakeSSHClient.fail_open_sftp = True
        try:
            pair, err = jm._sftp_connect("h", "u", 22, None, None, 300)
            assert pair is None
            assert "打开 SFTP 通道失败" in err["message"]
            assert FakeSSHClient.instances[-1].closed is True
        finally:
            FakeSSHClient.fail_open_sftp = False

    def test_open_sftp_close_exc_swallowed(self, monkeypatch):
        # open_sftp 失败后 close() 自身抛异常 → 内层 except 吞掉，error dict 照常返回
        self._fake_paramiko(monkeypatch)
        FakeSSHClient.fail_open_sftp = True
        FakeSSHClient.close_exc = RuntimeError("close boom")
        try:
            pair, err = jm._sftp_connect("h", "u", 22, None, None, 300)
            assert pair is None
            assert err["status"] == "error"
            assert "打开 SFTP 通道失败" in err["message"]
            assert FakeSSHClient.instances[-1].closed is False
        finally:
            FakeSSHClient.fail_open_sftp = False
            FakeSSHClient.close_exc = None

    def test_paramiko_missing_error(self, monkeypatch):
        monkeypatch.setattr(jm, "_import_paramiko",
                            lambda: (None, "缺 paramiko"))
        pair, err = jm._sftp_connect("h", "u", 22, None, None, 300)
        assert pair is None and err["message"] == "缺 paramiko"


class FakeAttr:
    def __init__(self, filename, st_mode, st_size=0, st_mtime=0.0):
        self.filename = filename
        self.st_mode = st_mode
        self.st_size = st_size
        self.st_mtime = st_mtime


class TestSftpEntryKind:
    def test_dir(self):
        kind, inferred = jm._sftp_entry_kind(FakeAttr("d", 0o40666))
        assert (kind, inferred) == (jm.SFTP_KIND_DIR, False)

    def test_file(self):
        kind, inferred = jm._sftp_entry_kind(FakeAttr("f", 0o100644, 5))
        assert (kind, inferred) == (jm.SFTP_KIND_FILE, False)

    def test_no_type_bits_with_perms_inferred_file(self):
        # 实测跳板机：文件只给权限位 0o666
        kind, inferred = jm._sftp_entry_kind(FakeAttr("f", 0o666, 5))
        assert (kind, inferred) == (jm.SFTP_KIND_FILE, True)

    def test_no_type_bits_no_perms_with_size_inferred_file(self):
        kind, inferred = jm._sftp_entry_kind(FakeAttr("f", 0, 7))
        assert (kind, inferred) == (jm.SFTP_KIND_FILE, True)

    def test_all_zero_other(self):
        kind, inferred = jm._sftp_entry_kind(FakeAttr("x", 0, 0))
        assert (kind, inferred) == (jm.SFTP_KIND_OTHER, True)

    def test_symlink_other(self):
        kind, inferred = jm._sftp_entry_kind(FakeAttr("l", 0o120777))
        assert (kind, inferred) == (jm.SFTP_KIND_OTHER, False)

    def test_missing_mode_attr(self):
        class Bare:
            pass
        kind, inferred = jm._sftp_entry_kind(Bare())
        assert kind == jm.SFTP_KIND_OTHER


class TestSftpClose:
    def test_both_closed(self):
        closed = []

        class C:
            def close(self):
                closed.append("c")

        class S:
            def close(self):
                closed.append("s")

        jm._sftp_close(C(), S())
        assert closed == ["s", "c"]

    def test_one_raise_other_still_closed(self):
        closed = []

        class C:
            def close(self):
                raise RuntimeError("x")

        class S:
            def close(self):
                closed.append("s")

        jm._sftp_close(C(), S())
        assert closed == ["s"]


class TestSftpMakedirs:
    def _sftp(self):
        class FS:
            def __init__(self):
                self.dirs = set()
                self.fail_mkdir = set()
                self.fail_stat = set()

            def stat(self, p):
                if p in self.fail_stat:
                    raise IOError("no")
                if p in self.dirs:
                    return FakeAttr("d", 0o40666)
                raise IOError("no")

            def mkdir(self, p):
                if p in self.fail_mkdir:
                    raise IOError("perm")
                self.dirs.add(p)

        return FS()

    def test_empty_noop(self):
        fs = self._sftp()
        jm._sftp_makedirs(fs, "")
        assert fs.dirs == set()

    def test_creates_chain(self):
        fs = self._sftp()
        jm._sftp_makedirs(fs, "/a/b/c")
        assert fs.dirs == {"/a", "/a/b", "/a/b/c"}

    def test_relative_path(self):
        fs = self._sftp()
        jm._sftp_makedirs(fs, "a/b")
        assert fs.dirs == {"a", "a/b"}

    def test_backslash_normalized(self):
        fs = self._sftp()
        jm._sftp_makedirs(fs, "/a\\b")
        assert fs.dirs == {"/a", "/a/b"}

    def test_existing_skipped(self):
        fs = self._sftp()
        fs.dirs.add("/a")
        jm._sftp_makedirs(fs, "/a")
        assert "/a" in fs.dirs

    def test_mkdir_race_confirmed_ok(self):
        # mkdir 抛 IOError 但随后 stat 到（别人刚建好）→ 当成功
        fs = self._sftp()
        fs.fail_mkdir.add("/a")

        orig_mkdir = fs.mkdir

        def mkdir_then_exists(p):
            if p in fs.fail_mkdir:
                fs.dirs.add(p)  # 竞态对手刚建好
                fs.fail_mkdir.discard(p)
                raise IOError("EEXIST")
            orig_mkdir(p)

        fs.mkdir = mkdir_then_exists
        jm._sftp_makedirs(fs, "/a")  # 不应 raise

    def test_mkdir_and_stat_fail_raises(self):
        fs = self._sftp()
        fs.fail_mkdir.add("/a")
        fs.fail_stat.add("/a")
        with pytest.raises(IOError):
            jm._sftp_makedirs(fs, "/a")


class FakeSFTP:
    """通用假 SFTP 会话。"""

    def __init__(self):
        self.dirs = set()
        self.puts = []
        self.gets = []
        self.removes = []
        self.dir_entries = {}       # 远端目录 -> [FakeAttr]
        self.stat_attrs = {}        # 远端路径 -> FakeAttr（_pull_paramiko 用）
        self.fail_mkdir = set()
        self.fail_put = set()
        self.fail_get = set()
        self.fail_stat = set()
        self.fail_remove = set()

    def stat(self, p):
        if p in self.fail_stat:
            raise IOError("stat fail")
        if p in self.stat_attrs:
            return self.stat_attrs[p]
        raise IOError("no such file")

    def mkdir(self, p):
        if p in self.fail_mkdir:
            raise IOError("mkdir fail")
        self.dirs.add(p)

    def put(self, l, r):
        if r in self.fail_put:
            raise IOError("put fail")
        self.puts.append((l, r))

    def get(self, r, l):
        if r in self.fail_get:
            raise IOError("get fail")
        self.gets.append((r, l))

    def listdir_attr(self, d):
        if d in self.fail_stat:
            raise IOError("list fail")
        return self.dir_entries.get(d, [])

    def remove(self, p):
        if p in self.fail_remove:
            raise IOError("remove fail")
        self.removes.append(p)


class TestSftpWalkPut:
    def test_tree(self, tmp_path):
        (tmp_path / "a.txt").write_text("123")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("12")
        (tmp_path / "x.log").write_text("1")
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "c.js").write_text("1")
        sftp = FakeSFTP()
        counter = {"files": 0, "bytes": 0, "skipped": 0}
        errors = []
        jm._sftp_walk_put(sftp, str(tmp_path), "/r", ["*.log", "node_modules"],
                          counter, errors)
        assert counter["files"] == 2
        assert counter["bytes"] == 5
        assert errors == []
        # _sftp_makedirs 是 mkdir -p 语义：父链一起建
        assert sftp.dirs == {"/r", "/r/sub"}
        remote_targets = sorted(r for _, r in sftp.puts)
        assert remote_targets == ["/r/a.txt", "/r/sub/b.txt"]

    def test_put_failure_recorded(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        sftp = FakeSFTP()
        sftp.fail_put.add("/r/a.txt")
        counter = {"files": 0, "bytes": 0, "skipped": 0}
        errors = []
        jm._sftp_walk_put(sftp, str(tmp_path), "/r", [], counter, errors)
        assert counter["files"] == 0
        assert len(errors) == 1 and "上传失败" in errors[0]


class TestSftpWalkGet:
    def test_tree(self, tmp_path):
        local = tmp_path / "out"
        local.mkdir()
        sftp = FakeSFTP()
        sftp.dir_entries["/r"] = [
            FakeAttr("a.txt", 0o100644, 5),
            FakeAttr("sub", 0o40666),
            FakeAttr("link", 0o120777),     # other → skipped
            FakeAttr("../evil", 0o100644),  # 不安全名 → 跳过
            FakeAttr("x.log", 0o100644),    # exclude → 跳过
        ]
        sftp.dir_entries["/r/sub"] = [FakeAttr("b.txt", 0o100644, 2)]
        counter = {"files": 0, "bytes": 0, "skipped": 0}
        errors = []
        jm._sftp_walk_get(sftp, "/r", str(local), ["*.log"], counter, errors)
        assert counter["files"] == 2
        assert counter["bytes"] == 7
        assert counter["skipped"] == 1
        assert errors == []
        assert (local / "sub").is_dir()

    def test_mode_inferred_counted(self, tmp_path):
        local = tmp_path / "out"
        local.mkdir()
        sftp = FakeSFTP()
        sftp.dir_entries["/r"] = [FakeAttr("a.txt", 0o666, 5)]  # 无类型位
        counter = {"files": 0, "bytes": 0, "skipped": 0}
        jm._sftp_walk_get(sftp, "/r", str(local), [], counter, [])
        assert counter["files"] == 1
        assert counter["mode_inferred"] == 1

    def test_get_failure_recorded(self, tmp_path):
        local = tmp_path / "out"
        local.mkdir()
        sftp = FakeSFTP()
        sftp.dir_entries["/r"] = [FakeAttr("a.txt", 0o100644)]
        sftp.fail_get.add("/r/a.txt")
        counter = {"files": 0, "bytes": 0, "skipped": 0}
        errors = []
        jm._sftp_walk_get(sftp, "/r", str(local), [], counter, errors)
        assert counter["files"] == 0
        assert "下载失败" in errors[0]


class TestParamikoResult:
    def test_ok(self):
        out = jm._paramiko_result({"files": 3, "bytes": 9, "skipped": 0}, [])
        assert out == {"status": "ok", "files_transferred": 3, "bytes": 9,
                       "transport": "paramiko"}

    def test_partial_with_errors(self):
        out = jm._paramiko_result({"files": 0, "bytes": 0, "skipped": 0},
                                  ["e%d" % i for i in range(15)])
        assert out["status"] == "partial"
        assert len(out["errors"]) == 10

    def test_skipped_and_mode_inferred(self):
        out = jm._paramiko_result({"files": 0, "bytes": 0, "skipped": 2,
                                   "mode_inferred": 1}, [], extra={"x": 1})
        assert out["skipped_non_regular"] == 2
        assert out["mode_inferred"] == 1
        assert out["x"] == 1


# ═══════════════ paramiko push/pull/scan/sync ═══════════════

class TestPushParamiko:
    def _connect_ok(self, monkeypatch, sftp):
        monkeypatch.setattr(jm, "_sftp_connect",
                            lambda *a, **k: ((object(), sftp), None))
        closed = []
        monkeypatch.setattr(jm, "_sftp_close",
                            lambda c, s: closed.append(True))

    def test_single_file(self, tmp_path, monkeypatch):
        f = tmp_path / "a.jar"
        f.write_text("hello")
        sftp = FakeSFTP()
        self._connect_ok(monkeypatch, sftp)
        out = jm._push_paramiko(str(f), "/r/a.jar", "h", "u")
        assert out["status"] == "ok"
        assert out["files_transferred"] == 1 and out["bytes"] == 5
        assert sftp.puts == [(str(f), "/r/a.jar")]
        assert sftp.dirs == {"/r"}  # 父目录先建

    def test_dir_recursive(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("22")
        sftp = FakeSFTP()
        self._connect_ok(monkeypatch, sftp)
        out = jm._push_paramiko(str(tmp_path), "/r", "h", "u", exclude=["sub"])
        assert out["status"] == "ok"
        assert out["files_transferred"] == 1

    def test_missing_local(self, tmp_path, monkeypatch):
        sftp = FakeSFTP()
        self._connect_ok(monkeypatch, sftp)
        out = jm._push_paramiko(str(tmp_path / "nope"), "/r", "h", "u")
        assert out["status"] == "error"
        assert "本地路径不存在" in out["message"]

    def test_put_failure_partial(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("1")
        sftp = FakeSFTP()
        sftp.fail_put.add("/r/a.txt")
        self._connect_ok(monkeypatch, sftp)
        out = jm._push_paramiko(str(tmp_path), "/r", "h", "u")
        assert out["status"] == "partial"
        assert "上传失败" in out["errors"][0]

    def test_exception_error_dict(self, tmp_path, monkeypatch):
        sftp = FakeSFTP()
        sftp.fail_put.add("/r/a.jar")
        self._connect_ok(monkeypatch, sftp)
        f = tmp_path / "a.jar"
        f.write_text("x")
        out = jm._push_paramiko(str(f), "/r/a.jar", "h", "u")
        assert out["status"] == "error"
        assert "SFTP 推送失败" in out["message"]

    def test_connect_error_passthrough(self, monkeypatch):
        monkeypatch.setattr(jm, "_sftp_connect",
                            lambda *a, **k: (None, {"status": "error",
                                                    "message": "refused"}))
        out = jm._push_paramiko("/l", "/r", "h", "u")
        assert out["message"] == "refused"


class TestPullParamiko:
    def _connect_ok(self, monkeypatch, sftp):
        monkeypatch.setattr(jm, "_sftp_connect",
                            lambda *a, **k: ((object(), sftp), None))
        monkeypatch.setattr(jm, "_sftp_close", lambda c, s: None)

    def test_single_file_into_dir(self, tmp_path, monkeypatch):
        outdir = tmp_path / "out"
        outdir.mkdir()
        sftp = FakeSFTP()
        sftp.stat_attrs["/r/a.jar"] = FakeAttr("a.jar", 0o100644, 5)
        self._connect_ok(monkeypatch, sftp)
        out = jm._pull_paramiko("/r/a.jar", str(outdir), "h", "u")
        assert out["status"] == "ok"
        assert out["files_transferred"] == 1 and out["bytes"] == 5
        assert sftp.gets == [("/r/a.jar", str(outdir / "a.jar"))]

    def test_single_file_to_exact_target(self, tmp_path, monkeypatch):
        target = tmp_path / "out.bin"
        sftp = FakeSFTP()
        sftp.stat_attrs["/r/a.jar"] = FakeAttr("a.jar", 0o100644, 5)
        self._connect_ok(monkeypatch, sftp)
        out = jm._pull_paramiko("/r/a.jar", str(target), "h", "u")
        assert out["status"] == "ok"
        assert sftp.gets == [("/r/a.jar", str(target))]

    def test_dir_recursive(self, tmp_path, monkeypatch):
        outdir = tmp_path / "out"
        outdir.mkdir()
        sftp = FakeSFTP()
        sftp.stat_attrs["/r"] = FakeAttr("r", 0o40666)
        sftp.dir_entries["/r"] = [FakeAttr("a.txt", 0o100644, 3)]
        self._connect_ok(monkeypatch, sftp)
        out = jm._pull_paramiko("/r", str(outdir), "h", "u")
        assert out["status"] == "ok"
        assert out["files_transferred"] == 1

    def test_remote_unreadable(self, tmp_path, monkeypatch):
        sftp = FakeSFTP()
        self._connect_ok(monkeypatch, sftp)
        out = jm._pull_paramiko("/r/none", str(tmp_path), "h", "u")
        assert out["status"] == "error"
        assert "远端路径不可读" in out["message"]

    def test_bug_j2_no_type_bits_falsely_rejected(self, tmp_path, monkeypatch):
        """BUG-J2 佐证：单文件 stat 无类型位（0o666）→ 报「既不是文件也不是目录」。

        _sftp_entry_kind 对这种模式有兜底（判 file），walk/scan 都受益，
        但 _pull_paramiko 的直接 stat 路径用裸 S_ISREG/S_ISDIR —— 同一模块
        两套判定，实测跳板机上单文件拉取恒失败。修 BUG 后改断言。
        """
        outdir = tmp_path / "out"
        outdir.mkdir()
        sftp = FakeSFTP()
        sftp.stat_attrs["/r/a.jar"] = FakeAttr("a.jar", 0o666, 5)
        self._connect_ok(monkeypatch, sftp)
        out = jm._pull_paramiko("/r/a.jar", str(outdir), "h", "u")
        assert out["status"] == "error"  # ← BUG：本应作为文件拉取
        assert "既不是文件也不是目录" in out["message"]

    def test_symlink_rejected(self, tmp_path, monkeypatch):
        outdir = tmp_path / "out"
        outdir.mkdir()
        sftp = FakeSFTP()
        sftp.stat_attrs["/r/l"] = FakeAttr("l", 0o120777)
        self._connect_ok(monkeypatch, sftp)
        out = jm._pull_paramiko("/r/l", str(outdir), "h", "u")
        assert out["status"] == "error"
        assert "既不是文件也不是目录" in out["message"]

    def test_get_failure_single_file_is_error_not_partial(self, tmp_path, monkeypatch):
        # 单文件分支的 get 失败走外层 except（walk 分支才是逐文件 partial）
        outdir = tmp_path / "out"
        outdir.mkdir()
        sftp = FakeSFTP()
        sftp.stat_attrs["/r/a.jar"] = FakeAttr("a.jar", 0o100644, 5)
        sftp.fail_get.add("/r/a.jar")
        self._connect_ok(monkeypatch, sftp)
        out = jm._pull_paramiko("/r/a.jar", str(outdir), "h", "u")
        assert out["status"] == "error"
        assert "SFTP 拉取失败" in out["message"]

    def test_connect_error_passthrough(self, tmp_path, monkeypatch):
        outdir = tmp_path / "out"
        outdir.mkdir()
        FakeSSHClient.fail_connect = True
        try:
            out = jm._pull_paramiko("/r/a.jar", str(outdir), "h", "u")
        finally:
            FakeSSHClient.fail_connect = False
        assert out["status"] == "error"
        assert "SSH 连接失败" in out["message"]


class TestScanRemoteFilesParamiko:
    def _connect_ok(self, monkeypatch, sftp):
        monkeypatch.setattr(jm, "_sftp_connect",
                            lambda *a, **k: ((object(), sftp), None))
        monkeypatch.setattr(jm, "_sftp_close", lambda c, s: None)

    def test_scan_tree(self, monkeypatch):
        sftp = FakeSFTP()
        sftp.dir_entries["/r"] = [
            FakeAttr("a.txt", 0o100644, 5, 1719600000.0),
            FakeAttr("sub", 0o40666),
            FakeAttr("other", 0o120777),
            FakeAttr("x.log", 0o100644, 1),
        ]
        sftp.dir_entries["/r/sub"] = [FakeAttr("b.txt", 0o100644, 2, 1719600001.0)]
        self._connect_ok(monkeypatch, sftp)
        files = jm.scan_remote_files_paramiko("/r", "h", "u", exclude=["*.log"])
        assert set(files) == {"a.txt", "sub/b.txt"}
        assert files["a.txt"] == {"size": 5, "mtime": 1719600000.0}

    def test_connect_error(self, monkeypatch):
        monkeypatch.setattr(jm, "_sftp_connect",
                            lambda *a, **k: (None, {"status": "error",
                                                    "message": "refused"}))
        out = jm.scan_remote_files_paramiko("/r", "h", "u")
        assert out == {"__error__": "refused"}

    def test_listdir_ioerror(self, monkeypatch):
        sftp = FakeSFTP()
        sftp.fail_stat.add("/r")
        self._connect_ok(monkeypatch, sftp)
        out = jm.scan_remote_files_paramiko("/r", "h", "u")
        assert "__error__" in out and "列目录失败" in out["__error__"]

    def test_unsafe_name_skipped(self, monkeypatch):
        sftp = FakeSFTP()
        sftp.dir_entries["/r"] = [FakeAttr("../evil", 0o100644, 5)]
        self._connect_ok(monkeypatch, sftp)
        assert jm.scan_remote_files_paramiko("/r", "h", "u") == {}

    def test_inferred_counter_out_param(self, monkeypatch):
        sftp = FakeSFTP()
        sftp.dir_entries["/r"] = [FakeAttr("a.txt", 0o666, 5)]  # 无类型位
        self._connect_ok(monkeypatch, sftp)
        counter = []
        files = jm.scan_remote_files_paramiko("/r", "h", "u",
                                              inferred_counter=counter)
        assert set(files) == {"a.txt"}
        assert counter == [1]

    def test_no_counter_param_no_crash(self, monkeypatch):
        sftp = FakeSFTP()
        sftp.dir_entries["/r"] = [FakeAttr("a.txt", 0o666, 5)]
        self._connect_ok(monkeypatch, sftp)
        files = jm.scan_remote_files_paramiko("/r", "h", "u")
        assert set(files) == {"a.txt"}


class TestSyncParamiko:
    def _local(self, tmp_path):
        (tmp_path / "a.txt").write_text("123")

    def _scan(self, monkeypatch, remote_files, inferred=0):
        def fake_scan(remote_path, remote_host, remote_user, port, key_path,
                      password, exclude, timeout, inferred_counter=None):
            if inferred_counter is not None:
                inferred_counter.append(inferred)
            return dict(remote_files)

        monkeypatch.setattr(jm, "scan_remote_files_paramiko", fake_scan)

    def _connect_ok(self, monkeypatch, sftp):
        monkeypatch.setattr(jm, "_sftp_connect",
                            lambda *a, **k: ((object(), sftp), None))
        monkeypatch.setattr(jm, "_sftp_close", lambda c, s: None)

    def test_dry_run(self, tmp_path, monkeypatch):
        self._local(tmp_path)
        self._scan(monkeypatch, {"b.txt": {"size": 1, "mtime": 1.0}})
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u", dry_run=True)
        assert out["status"] == "ok" and out["dry_run"] is True
        assert out["transport"] == "paramiko"
        assert out["upload"] == 1 and out["download"] == 1
        assert out["skip"] == 0 and out["delete"] == 0

    def test_full_both(self, tmp_path, monkeypatch):
        self._local(tmp_path)
        self._scan(monkeypatch, {"b.txt": {"size": 1, "mtime": 1.0}})
        sftp = FakeSFTP()
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u")
        assert out["status"] == "ok"
        assert out["uploaded"] == 1 and out["downloaded"] == 1
        assert out["files_transferred"] == 2
        assert len(sftp.puts) == 1 and len(sftp.gets) == 1

    def test_delete_flow(self, tmp_path, monkeypatch):
        self._local(tmp_path)
        self._scan(monkeypatch, {"b.txt": {"size": 1, "mtime": 1.0}})
        sftp = FakeSFTP()
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u",
                                direction="upload", delete=True)
        assert out["status"] == "ok"
        assert sftp.removes == ["/r/b.txt"]

    def test_conflict_strategy_remote_pulls(self, tmp_path, monkeypatch):
        self._local(tmp_path)
        self._scan(monkeypatch, {"a.txt": {"size": 9, "mtime": 1.0}})
        sftp = FakeSFTP()
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u", strategy="remote")
        assert out["conflicts"] == 1
        assert len(sftp.gets) == 1 and len(sftp.puts) == 0

    def test_conflict_strategy_local_pushes(self, tmp_path, monkeypatch):
        self._local(tmp_path)
        self._scan(monkeypatch, {"a.txt": {"size": 9, "mtime": 1.0}})
        sftp = FakeSFTP()
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u", strategy="local")
        assert out["conflicts"] == 1
        assert len(sftp.puts) == 1

    def test_errors_partial(self, tmp_path, monkeypatch):
        self._local(tmp_path)
        self._scan(monkeypatch, {})
        sftp = FakeSFTP()
        sftp.fail_put.add("/r/a.txt")
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u")
        assert out["status"] == "partial"
        assert "上传失败" in out["errors"][0]

    def test_skip_counted(self, tmp_path, monkeypatch):
        import time as _t
        self._local(tmp_path)
        m = os.stat(str(tmp_path / "a.txt")).st_mtime
        self._scan(monkeypatch, {"a.txt": {"size": 3, "mtime": m}})
        sftp = FakeSFTP()
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u")
        assert out["status"] == "ok"
        assert out["skipped"] == 1 and out["files_transferred"] == 0

    def test_mode_inferred_passthrough(self, tmp_path, monkeypatch):
        self._local(tmp_path)
        self._scan(monkeypatch, {}, inferred=3)
        sftp = FakeSFTP()
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u")
        assert out["mode_inferred"] == 3

    def test_connect_error(self, tmp_path, monkeypatch):
        self._local(tmp_path)
        self._scan(monkeypatch, {})
        monkeypatch.setattr(jm, "_sftp_connect",
                            lambda *a, **k: (None, {"status": "error",
                                                    "message": "refused"}))
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u")
        assert out["message"] == "refused"

    def test_scan_error(self, tmp_path, monkeypatch):
        self._local(tmp_path)
        monkeypatch.setattr(jm, "scan_remote_files_paramiko",
                            lambda *a, **k: {"__error__": "down"})
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u")
        assert out == {"status": "error", "message": "down"}

    def test_download_failure_partial(self, tmp_path, monkeypatch):
        self._local(tmp_path)
        self._scan(monkeypatch, {"b.txt": {"size": 1, "mtime": 1.0}})
        sftp = FakeSFTP()
        sftp.fail_get.add("/r/b.txt")
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u")
        assert out["status"] == "partial"
        assert any("下载失败" in e for e in out["errors"])
        assert out["downloaded"] == 0

    def test_delete_failure_partial(self, tmp_path, monkeypatch):
        self._local(tmp_path)
        self._scan(monkeypatch, {"b.txt": {"size": 1, "mtime": 1.0}})
        sftp = FakeSFTP()
        sftp.fail_remove.add("/r/b.txt")
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u",
                                direction="upload", delete=True)
        assert out["status"] == "partial"
        assert any("删除失败" in e for e in out["errors"])

    def test_conflict_put_failure_partial(self, tmp_path, monkeypatch):
        # strategy=local 走 put → put 失败 → 冲突解决失败计入 errors
        self._local(tmp_path)
        self._scan(monkeypatch, {"a.txt": {"size": 9, "mtime": 1.0}})
        sftp = FakeSFTP()
        sftp.fail_put.add("/r/a.txt")
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u", strategy="local")
        assert out["status"] == "partial"
        assert any("冲突解决失败" in e for e in out["errors"])
        assert out["conflicts"] == 0

    def test_conflict_get_failure_partial(self, tmp_path, monkeypatch):
        # strategy=remote 走 get → get 失败 → 冲突解决失败计入 errors
        self._local(tmp_path)
        self._scan(monkeypatch, {"a.txt": {"size": 9, "mtime": 1.0}})
        sftp = FakeSFTP()
        sftp.fail_get.add("/r/a.txt")
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u", strategy="remote")
        assert out["status"] == "partial"
        assert any("冲突解决失败" in e for e in out["errors"])

    def test_plan_iter_raise_hits_outer_except(self, tmp_path, monkeypatch):
        """plan["upload"] 迭代自身抛异常 → 外层 except 兜底（行 1203-1204）。"""
        self._local(tmp_path)
        self._scan(monkeypatch, {})

        class Boom(list):
            def __iter__(self):
                raise RuntimeError("plan broken")

        monkeypatch.setattr(jm, "compute_sync_plan",
                            lambda *a, **k: {"upload": Boom(["a.txt"]),
                                             "download": [], "conflict": [],
                                             "skip": [], "delete": []})
        sftp = FakeSFTP()
        self._connect_ok(monkeypatch, sftp)
        out = jm._sync_paramiko(str(tmp_path), "/r", "h", "u")
        assert out["status"] == "error"
        assert "SFTP 同步失败" in out["message"]
        assert "plan broken" in out["message"]


# ═══════════════ 导出 ═══════════════

class TestAll:
    def test_all_importable(self):
        for name in jump.__all__:
            assert hasattr(jump, name), name

    def test_core_api_present(self):
        for name in ("push", "pull", "sync", "shquote", "remote_join",
                     "compute_sync_plan", "collect_files", "scan_local_files",
                     "scan_remote_files", "scan_remote_files_paramiko",
                     "upload_single", "download_single", "batch_upload",
                     "batch_download", "resolve_conflict", "build_ssh_opts",
                     "should_exclude"):
            assert hasattr(jump, name), name
