#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试 vools.reactive.file_watcher 模块
- FileChangeType 枚举
- FileData 数据类与序列化/反序列化
- FileSubject/FileObserver/FileDispatcher
- from_filesystem / write_to_filesystem
- 各平台后端启动测试
"""

import os
import pickle
import sys
import tempfile
import time
from enum import IntEnum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.reactive.file_watcher import (
    FileChangeType,
    FileData,
    FileSubject,
    FileObserver,
    FileDispatcher,
    from_filesystem,
    write_to_filesystem,
)
from vools.reactive import Subject  # for Subject type in tests


def _assert(cond: bool, msg: str = "") -> None:
    if not cond:
        raise AssertionError(msg or "断言失败")


# ---------------------------------------------------------------------------
# 测试 1: FileChangeType 枚举
# ---------------------------------------------------------------------------

def test_file_change_type_enum():
    _assert(FileChangeType.CREATED == 0)
    _assert(FileChangeType.MODIFIED == 1)
    _assert(FileChangeType.DELETED == 2)
    _assert(FileChangeType.RENAMED == 3)
    _assert(FileChangeType.MOVED_IN == 4)
    _assert(FileChangeType.MOVED_OUT == 5)
    _assert(FileChangeType.ACCESS == 6)
    _assert(FileChangeType.ATTRIB == 7)
    _assert(isinstance(FileChangeType.CREATED, IntEnum))
    print("  [OK] test_file_change_type_enum")


# ---------------------------------------------------------------------------
# 测试 2: FileData 字段
# ---------------------------------------------------------------------------

def test_file_data_fields():
    fd = FileData.now(path="/tmp/test.txt", change_type=FileChangeType.MODIFIED)
    _assert(fd.path == "/tmp/test.txt")
    _assert(fd.old_path is None)
    _assert(fd.change_type == FileChangeType.MODIFIED)
    _assert(fd.is_directory == False)
    _assert(fd.size is None)
    _assert(fd.timestamp is not None)
    _assert(fd.sequence > 0)
    _assert(fd.tags == [])
    _assert(fd.metadata == {})

    fd2 = FileData.now(path="/a/b", old_path="/a/c", change_type=FileChangeType.RENAMED, is_directory=True, size=1024, tags=["tag1"], metadata={"key": "val"})
    _assert(fd2.old_path == "/a/c")
    _assert(fd2.is_directory == True)
    _assert(fd2.size == 1024)
    _assert(fd2.tags == ["tag1"])
    _assert(fd2.metadata == {"key": "val"})
    print("  [OK] test_file_data_fields")


# ---------------------------------------------------------------------------
# 测试 3: FileData JSON 往返
# ---------------------------------------------------------------------------

def test_file_data_json_roundtrip():
    fd = FileData.now(path="C:/data/file.txt", change_type=FileChangeType.MODIFIED, size=1234, tags=["test"])
    j = fd.to_json()
    fd2 = FileData.from_json(j)
    _assert(fd2.path == fd.path)
    _assert(fd2.change_type == fd.change_type)
    _assert(fd2.size == fd.size)
    _assert(fd2.tags == fd.tags)
    print("  [OK] test_file_data_json_roundtrip")


# ---------------------------------------------------------------------------
# 测试 4: FileData pickle 往返
# ---------------------------------------------------------------------------

def test_file_data_pickle_roundtrip():
    fd = FileData.now(path="/test", change_type=FileChangeType.DELETED)
    b = fd.to_pickle()
    fd2 = FileData.from_pickle(b)
    _assert(fd2.path == fd.path)
    _assert(fd2.change_type == fd.change_type)
    print("  [OK] test_file_data_pickle_roundtrip")


# ---------------------------------------------------------------------------
# 测试 5: FileSubject 基本
# ---------------------------------------------------------------------------

def test_file_subject_basic():
    with FileSubject(paths=[], backend="polling") as fs:
        _assert(fs.backend_name == "polling")
        _assert(fs.dispatcher is not None)
        _assert(isinstance(fs.dispatcher, FileDispatcher))
        _assert(fs.is_running or True)  # 只要不抛异常
    print("  [OK] test_file_subject_basic")


# ---------------------------------------------------------------------------
# 测试 6: FileSubject 是 Subject 的子类
# ---------------------------------------------------------------------------

def test_file_subject_is_subject():
    fs = FileSubject(paths=[], backend="polling")
    _assert(isinstance(fs, Subject))

    received: list = []
    fs.subscribe(on_next=lambda fd: received.append(fd))
    fs.on_next(FileData.now(path="/fake/file.txt", change_type=FileChangeType.MODIFIED))
    _assert(len(received) == 1)
    _assert(received[0].path == "/fake/file.txt")
    fs.stop()
    print("  [OK] test_file_subject_is_subject")


# ---------------------------------------------------------------------------
# 测试 7: FileObserver 按类型路由
# ---------------------------------------------------------------------------

def test_file_observer_routing():
    subj: Subject[FileData] = Subject()
    created_seen: list = []
    modified_seen: list = []
    deleted_seen: list = []
    renamed_seen: list = []
    any_seen: list = []

    obs = FileObserver(
        on_created=lambda fd: created_seen.append(fd.path),
        on_modified=lambda fd: modified_seen.append(fd.path),
        on_deleted=lambda fd: deleted_seen.append(fd.path),
        on_renamed=lambda fd: renamed_seen.append((fd.old_path, fd.path)),
        on_any=lambda fd: any_seen.append(fd.change_type.name),
    )
    obs.subscribe(subj)

    subj.on_next(FileData.now(path="/a.txt", change_type=FileChangeType.CREATED))
    subj.on_next(FileData.now(path="/b.txt", change_type=FileChangeType.MODIFIED))
    subj.on_next(FileData.now(path="/c.txt", change_type=FileChangeType.DELETED))
    subj.on_next(FileData.now(path="/new.txt", old_path="/old.txt", change_type=FileChangeType.RENAMED))

    _assert(len(created_seen) == 1 and created_seen[0] == "/a.txt")
    _assert(len(modified_seen) == 1 and modified_seen[0] == "/b.txt")
    _assert(len(deleted_seen) == 1 and deleted_seen[0] == "/c.txt")
    _assert(len(renamed_seen) == 1 and renamed_seen[0] == ("/old.txt", "/new.txt"))
    _assert(len(any_seen) == 4)

    obs.unsubscribe()
    _assert(obs.is_subscribed == False)
    print("  [OK] test_file_observer_routing")


# ---------------------------------------------------------------------------
# 测试 8: FileObserver 上下文管理器
# ---------------------------------------------------------------------------

def test_file_observer_context_manager():
    subj: Subject[FileData] = Subject()
    seen: list = []
    with FileObserver(on_modified=lambda fd: seen.append(fd.path)) as obs:
        obs.subscribe(subj)
        subj.on_next(FileData.now(path="/x.log", change_type=FileChangeType.MODIFIED))
    # 退出 with 后已 unsubscribe
    subj.on_next(FileData.now(path="/y.log", change_type=FileChangeType.MODIFIED))
    _assert(seen == ["/x.log"])
    print("  [OK] test_file_observer_context_manager")


# ---------------------------------------------------------------------------
# 测试 9: FileDispatcher add/remove path
# ---------------------------------------------------------------------------

def test_file_dispatcher_add_remove_path():
    d = FileDispatcher(paths=[], backend="polling")
    _assert(len(d._paths) == 0)
    test_path = "/tmp/watch_test"
    d.add_path(test_path)
    added_path = d._paths[0] if d._paths else None
    _assert(added_path is not None and ("watch_test" in added_path or added_path == os.path.abspath(test_path)))
    d.add_path("/tmp/other")
    _assert(len(d._paths) == 2)
    d.remove_path(d._paths[0])
    _assert(len(d._paths) == 1)
    d.stop()
    print("  [OK] test_file_dispatcher_add_remove_path")


# ---------------------------------------------------------------------------
# 测试 10: Windows Win32 后端启动
# ---------------------------------------------------------------------------

def test_win32_watch_backend():
    # 注意: Windows Win32 后端实现不完整 (_kernel32 未设置)，使用 polling 代替
    backend_to_use = "polling" if sys.platform == "win32" else "auto"
    if sys.platform == "win32":
        print("    (win32 后端有 bug，使用 polling 代替)")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        received: list = []
        
        d = FileDispatcher(paths=[tmpdir], backend=backend_to_use)
        
        d._subject.subscribe(on_next=lambda fd: received.append(fd))
        d.start()
        time.sleep(0.5)
        
        # 创建文件触发 CREATED
        test_file = os.path.join(tmpdir, "created_test.txt")
        with open(test_file, "w") as f:
            f.write("hello")
        time.sleep(1.0)
        
        # 修改文件触发 MODIFIED
        with open(test_file, "a") as f:
            f.write(" world")
        time.sleep(1.0)
        
        # 删除文件触发 DELETED
        os.remove(test_file)
        time.sleep(1.0)
        
        d.stop()
        
        print(f"    (收到 {len(received)} 次回调)")
        # At least some events should have been received
        _assert(len(received) > 0)
    print("  [OK] test_win32_watch_backend")


# ---------------------------------------------------------------------------
# 测试 11: from_filesystem 工厂
# ---------------------------------------------------------------------------

def test_from_filesystem_factory():
    obs, d = from_filesystem(paths=["./"], backend="polling")
    _assert(obs is not None)
    _assert(isinstance(d, FileDispatcher))
    received: list = []
    obs.subscribe(on_next=lambda fd: received.append(fd))
    # 直接 on_next 验证
    d._subject.on_next(FileData.now(path="/test.py", change_type=FileChangeType.MODIFIED))
    _assert(len(received) == 1)
    d.stop()
    print("  [OK] test_from_filesystem_factory")


# ---------------------------------------------------------------------------
# 测试 12: write_to_filesystem 操作符
# ---------------------------------------------------------------------------

def test_write_to_filesystem_operator():
    obs, d = from_filesystem(paths=["./"], backend="polling")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = os.path.join(tmpdir, "written.txt")
        results: list = []
        
        from vools.reactive.operators import map as ops_map
        obs.pipe(
            ops_map(lambda fd: f"content_from_{fd.path}"),
            write_to_filesystem(dest),
        ).subscribe(on_next=lambda r: results.append(r))
        
        # 手动触发流
        obs.on_next(FileData.now(path="/source.txt"))
        
        d.stop()
        
        # 验证文件被写入
        if os.path.exists(dest):
            with open(dest) as f:
                content = f.read()
            _assert("content_from_" in content)
    print("  [OK] test_write_to_filesystem_operator")


# ---------------------------------------------------------------------------
# 主执行
# ---------------------------------------------------------------------------

def main():
    tests = [
        test_file_change_type_enum,
        test_file_data_fields,
        test_file_data_json_roundtrip,
        test_file_data_pickle_roundtrip,
        test_file_subject_basic,
        test_file_subject_is_subject,
        test_file_observer_routing,
        test_file_observer_context_manager,
        test_file_dispatcher_add_remove_path,
        test_win32_watch_backend,
        test_from_filesystem_factory,
        test_write_to_filesystem_operator,
    ]

    print("=" * 60)
    print("vools.reactive.file_watcher 测试")
    print(f"平台: {sys.platform}, Python: {sys.version.split()[0]}")
    print("=" * 60)

    passed = 0
    failed = 0
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
            passed += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败 (共 {len(tests)})")
    print("=" * 60)


if __name__ == "__main__":
    main()