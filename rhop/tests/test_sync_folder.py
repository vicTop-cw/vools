"""sync_folder 测试：拉取 / 幂等 / 内容变更重拉 / pattern 过滤 / 守护退出 / 回调。"""

import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, r'E:\IDEProjects\AI\vools')
sys.path.insert(0, r'E:\IDEProjects\AI\vools\rhop')

from vools.rhop.sync_folder import (
    MANIFEST_NAME,
    LocalDirSource,
    SyncFolder,
    sync_folder_once,
)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(path, mode, encoding=None if isinstance(content, bytes) else "utf-8") as fh:
        fh.write(content)


class TestSyncOnce:
    def test_pulls_new_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write(str(src / "a.parquet"), b"PAR1-binary-data")
        _write(str(src / "b.xlsx"), b"XL-binary")

        tgt = tmp_path / "tgt"
        out = sync_folder_once(str(src), str(tgt))
        assert sorted(out["pulled"]) == ["a.parquet", "b.xlsx"]
        assert out["errors"] == []
        assert (tgt / "a.parquet").read_bytes() == b"PAR1-binary-data"

    def test_idempotent_second_round(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        src.mkdir()
        _write(str(src / "f.bin"), b"data-v1")
        sync_folder_once(str(src), str(tgt))
        out2 = sync_folder_once(str(src), str(tgt))
        assert out2["pulled"] == []
        assert out2["skipped"] == 1

    def test_content_change_repulls(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        src.mkdir()
        _write(str(src / "f.bin"), b"data-v1")
        sync_folder_once(str(src), str(tgt))
        _write(str(src / "f.bin"), b"data-v2-longer")
        out = sync_folder_once(str(src), str(tgt))
        assert out["pulled"] == ["f.bin"]
        assert (tgt / "f.bin").read_bytes() == b"data-v2-longer"

    def test_manifest_never_pulled(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        src.mkdir()
        # 源目录里恰好有个同名 manifest（意外情形也不该被拉）
        _write(str(src / MANIFEST_NAME), "{}")
        out = sync_folder_once(str(src), str(tgt))
        assert out["pulled"] == []
        assert not (tgt / MANIFEST_NAME).exists()

    def test_pattern_filter(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        src.mkdir()
        _write(str(src / "keep.parquet"), b"p")
        _write(str(src / "skip.tmp"), b"t")
        out = sync_folder_once(str(src), str(tgt), pattern="*.parquet")
        assert out["pulled"] == ["keep.parquet"]
        assert not (tgt / "skip.tmp").exists()

    def test_missing_source_dir(self, tmp_path):
        """源目录不存在：守护模式常态（网络盘未挂载），静默空轮次不报错。"""
        out = sync_folder_once(str(tmp_path / "nope"), str(tmp_path / "tgt"))
        assert out == {"pulled": [], "skipped": 0, "errors": []}

    def test_recursive_subdirs(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        _write(str(src / "sub" / "deep.parquet"), b"deep")
        out = sync_folder_once(str(src), str(tgt), recursive=True)
        assert out["pulled"] == ["sub/deep.parquet"]
        assert (tgt / "sub" / "deep.parquet").read_bytes() == b"deep"

    def test_target_file_deleted_repulled(self, tmp_path):
        """target 被清理但 manifest 还有记录 → 文件缺失也应重拉。"""
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        src.mkdir()
        _write(str(src / "f.bin"), b"data")
        sync_folder_once(str(src), str(tgt))
        os.remove(str(tgt / "f.bin"))
        out = sync_folder_once(str(src), str(tgt))
        assert out["pulled"] == ["f.bin"]


class TestOnPullCallback:
    def test_callback_fires_per_pull(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        src.mkdir()
        _write(str(src / "a.bin"), b"1")
        _write(str(src / "b.bin"), b"2")
        seen = []
        sf = SyncFolder(LocalDirSource(str(src)), str(tgt),
                        on_pull=lambda name, path: seen.append(name))
        sf.sync_once()
        assert sorted(seen) == ["a.bin", "b.bin"]

    def test_callback_exception_not_fatal(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        src.mkdir()
        _write(str(src / "a.bin"), b"1")

        def boom(name, path):
            raise RuntimeError("callback boom")

        sf = SyncFolder(LocalDirSource(str(src)), str(tgt), on_pull=boom)
        out = sf.sync_once()
        assert out["pulled"] == ["a.bin"]
        assert (tgt / "a.bin").read_bytes() == b"1"


class TestRunForever:
    def test_stops_via_event(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        src.mkdir()
        _write(str(src / "f.bin"), b"x")
        stop = threading.Event()
        sf = SyncFolder(LocalDirSource(str(src)), str(tgt))

        def stop_soon():
            stop.set()

        # 立即置位 → run_forever 至多跑一轮就退出
        timer = threading.Timer(0.05, stop_soon)
        timer.start()
        summary = sf.run_forever(poll_interval=0.01, stop_event=stop)
        timer.join()
        assert summary["rounds"] >= 1
        assert summary["total_pulled"] == ["f.bin"]

    def test_multi_round_accumulates(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        src.mkdir()
        stop = threading.Event()
        sf = SyncFolder(LocalDirSource(str(src)), str(tgt))

        def feed_and_stop():
            _write(str(src / "late.bin"), b"L")
            # 留足轮询周期让下一轮 sync_once 真正拉到文件后再停
            threading.Timer(0.15, stop.set).start()

        timer = threading.Timer(0.05, feed_and_stop)
        timer.start()
        summary = sf.run_forever(poll_interval=0.05, stop_event=stop)
        timer.join()
        assert "late.bin" in summary["total_pulled"]

    def test_manifest_is_valid_json(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        src.mkdir()
        _write(str(src / "f.bin"), b"x")
        sf = SyncFolder(LocalDirSource(str(src)), str(tgt))
        sf.sync_once()
        with open(str(tgt / MANIFEST_NAME), encoding="utf-8") as fh:
            body = json.load(fh)
        assert "f.bin" in body
        assert body["f.bin"]["size"] == 1
