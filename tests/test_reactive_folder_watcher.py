"""tests/test_reactive_folder_watcher - FolderWatcher 模块测试"""

import os
import sys
import tempfile
import time
import threading

import pytest

from vools.reactive import (
    FolderChangeType,
    FolderData,
    FolderDispatcher,
    FolderSubject,
    FolderObserver,
    from_foldersystem,
    write_to_foldersystem,
)


# ====================================================================
# FolderChangeType 枚举测试
# ====================================================================


def test_folder_change_type_values():
    """7 个成员，值 0..6。"""
    assert int(FolderChangeType.FOLDER_CREATED) == 0
    assert int(FolderChangeType.FOLDER_DELETED) == 1
    assert int(FolderChangeType.FOLDER_RENAMED) == 2
    assert int(FolderChangeType.FOLDER_MOVED_IN) == 3
    assert int(FolderChangeType.FOLDER_MOVED_OUT) == 4
    assert int(FolderChangeType.FOLDER_ATTRIB) == 5
    assert int(FolderChangeType.FOLDER_CONTENT) == 6
    assert len(list(FolderChangeType)) == 7


def test_folder_change_type_str():
    assert str(FolderChangeType.FOLDER_CREATED) == "FOLDER_CREATED"


# ====================================================================
# FolderData 数据类测试
# ====================================================================


def test_folder_data_now():
    fd = FolderData.now(
        path="/tmp/a",
        change_type=FolderChangeType.FOLDER_CREATED,
        tags=["tag1"],
        metadata={"k": "v"},
    )
    assert fd.path == "/tmp/a"
    assert fd.old_path is None
    assert fd.change_type == FolderChangeType.FOLDER_CREATED
    assert fd.tags == ["tag1"]
    assert fd.metadata == {"k": "v"}
    assert fd.sequence > 0


def test_folder_data_json_roundtrip():
    fd = FolderData.now(
        path="/tmp/你好",
        old_path="/tmp/old",
        change_type=FolderChangeType.FOLDER_RENAMED,
        tags=["cn"],
        metadata={"created_by": "test"},
    )
    j = fd.to_json()
    fd2 = FolderData.from_json(j)
    assert fd2.path == fd.path
    assert fd2.old_path == fd.old_path
    assert fd2.change_type == fd.change_type
    assert fd2.tags == fd.tags
    assert fd2.metadata == fd.metadata
    assert fd2.sequence == fd.sequence


def test_folder_data_from_dict_missing_fields():
    fd = FolderData.from_dict({"path": "/tmp/x"})
    assert fd.path == "/tmp/x"
    assert fd.old_path is None
    assert fd.change_type == FolderChangeType.FOLDER_CONTENT


# ====================================================================
# FolderSubject / FolderObserver 响应式
# ====================================================================


def test_folder_subject_is_subject():
    with FolderSubject(paths=[], backend="polling", auto_start=False) as fs:
        # FolderSubject 继承自 Subject
        from vools.reactive import Subject

        assert isinstance(fs, Subject)


def test_folder_observer_routing():
    """手动发射不同事件，验证路由正确。"""
    received_c = []
    received_d = []
    received_r = []
    received_attrib = []
    received_any = []

    obs = FolderObserver(
        on_folder_created=lambda fd: received_c.append(fd),
        on_folder_deleted=lambda fd: received_d.append(fd),
        on_folder_renamed=lambda fd: received_r.append(fd),
        on_folder_attrib=lambda fd: received_attrib.append(fd),
        on_any=lambda fd: received_any.append(fd),
    )

    # 直接构造 Subject 测试路由
    from vools.reactive import Subject

    subject: Subject[FolderData] = Subject()
    obs.subscribe(subject)

    subject.on_next(
        FolderData.now(path="/tmp/c", change_type=FolderChangeType.FOLDER_CREATED)
    )
    subject.on_next(
        FolderData.now(path="/tmp/d", change_type=FolderChangeType.FOLDER_DELETED)
    )
    subject.on_next(
        FolderData.now(
            path="/tmp/new",
            old_path="/tmp/old",
            change_type=FolderChangeType.FOLDER_RENAMED,
        )
    )
    subject.on_next(
        FolderData.now(path="/tmp/a", change_type=FolderChangeType.FOLDER_ATTRIB)
    )

    # 每种类型只触发对应的回调
    assert len(received_c) == 1
    assert received_c[0].change_type == FolderChangeType.FOLDER_CREATED
    assert len(received_d) == 1
    assert len(received_r) == 1
    assert received_r[0].old_path == "/tmp/old"
    assert len(received_attrib) == 1
    assert len(received_any) == 4  # on_any 所有事件都经过


# ====================================================================
# FolderDispatcher 测试
# ====================================================================


def test_folder_dispatcher_with_block():
    with tempfile.TemporaryDirectory() as tmpdir:
        with FolderDispatcher(paths=[tmpdir], backend="polling") as d:
            assert d.backend_name == "polling"
            assert d.is_running
        # 退出 with 后停止
        assert not d.is_running


def test_folder_dispatcher_polling_created_event():
    """polling 模式下，创建子目录应产生 FOLDER_CREATED 事件。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        received = []
        d = FolderDispatcher(
            paths=[tmpdir],
            backend="polling",
            interval=0.1,
        )
        d.subject.subscribe(on_next=lambda fd: received.append(fd))
        d.start()
        time.sleep(0.2)

        # 创建子目录
        child = os.path.join(tmpdir, "new_child")
        os.mkdir(child)
        time.sleep(0.4)  # 等待 polling 周期

        d.stop()

        assert len(received) >= 1
        types = {fd.change_type for fd in received}
        assert FolderChangeType.FOLDER_CREATED in types


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_folder_dispatcher_win32_created_event():
    """Windows 下 ReadDirectoryChangesW 后端应捕获目录创建。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        received = []
        lock = threading.Lock()

        def handler(fd: FolderData):
            with lock:
                received.append(fd)

        d = FolderDispatcher(paths=[tmpdir], backend="win32")
        d.subject.subscribe(on_next=handler)
        d.start()
        time.sleep(0.3)

        child = os.path.join(tmpdir, "win_child")
        os.mkdir(child)
        time.sleep(1.0)

        d.stop()

        assert d.backend_name == "win32"
        assert len(received) >= 1
        types = {fd.change_type for fd in received}
        assert FolderChangeType.FOLDER_CREATED in types


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_folder_dispatcher_win32_deleted_event():
    """Windows 下删除目录应产生 FOLDER_DELETED 事件。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 先创建一个子目录
        child = os.path.join(tmpdir, "child_to_delete")
        os.mkdir(child)
        time.sleep(0.2)

        received = []
        d = FolderDispatcher(paths=[tmpdir], backend="win32")
        d.subject.subscribe(on_next=lambda fd: received.append(fd))
        d.start()
        time.sleep(0.3)

        os.rmdir(child)
        time.sleep(1.0)

        d.stop()

        types = {fd.change_type for fd in received}
        assert FolderChangeType.FOLDER_DELETED in types


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_folder_dispatcher_win32_renamed_event():
    """Windows 下目录重命名应产生 FOLDER_RENAMED 事件。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        old = os.path.join(tmpdir, "old_name")
        os.mkdir(old)
        time.sleep(0.2)

        received = []
        d = FolderDispatcher(paths=[tmpdir], backend="win32")
        d.subject.subscribe(on_next=lambda fd: received.append(fd))
        d.start()
        time.sleep(0.3)

        new_name = os.path.join(tmpdir, "new_name")
        os.rename(old, new_name)
        time.sleep(1.0)

        d.stop()

        types = {fd.change_type for fd in received}
        assert FolderChangeType.FOLDER_RENAMED in types


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux/inotify only"
)
def test_folder_dispatcher_inotify_created_event():
    """Linux 下 inotify 后端应捕获目录创建。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        received = []
        d = FolderDispatcher(paths=[tmpdir], backend="inotify")
        d.subject.subscribe(on_next=lambda fd: received.append(fd))
        d.start()
        time.sleep(0.3)

        child = os.path.join(tmpdir, "inotify_child")
        os.mkdir(child)
        time.sleep(0.5)

        d.stop()

        assert d.backend_name == "inotify"
        assert len(received) >= 1
        types = {fd.change_type for fd in received}
        assert FolderChangeType.FOLDER_CREATED in types


# ====================================================================
# from_foldersystem / write_to_foldersystem
# ====================================================================


def test_from_foldersystem_factory():
    with tempfile.TemporaryDirectory() as tmpdir:
        obs, d = from_foldersystem(paths=[tmpdir], backend="polling", interval=0.1)
        try:
            assert d is not None
            assert d.is_running
        finally:
            d.stop()


def test_write_to_foldersystem_operator():
    """write_to_foldersystem 应创建目录并产生 FolderData 事件。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        d = FolderDispatcher(paths=[tmpdir], backend="polling", interval=0.1)

        upstream_events = []

        def _on_next(fd: FolderData):
            upstream_events.append(fd)

        # 上游流：FolderData
        from vools.reactive import Observable

        upstream = Observable(
            lambda obs: (
                obs.on_next(
                    FolderData.now(
                        path=os.path.join(tmpdir, "operator_child"),
                        change_type=FolderChangeType.FOLDER_CREATED,
                    )
                ),
                obs.on_completed(),
            )[0]
        )

        subscription = upstream.pipe(
            write_to_foldersystem(d, mode="create"),
        ).subscribe(on_next=_on_next)

        time.sleep(0.3)

        assert os.path.isdir(os.path.join(tmpdir, "operator_child"))
        assert len(upstream_events) >= 1

        # 注意：write_to_foldersystem 产生自己的 FolderData 事件
        # 然后 subject 通过 dispatcher 再分发（根据后端）
        d.stop()


# ====================================================================
# 完整 end-to-end: FolderSubject + FolderObserver
# ====================================================================


def test_folder_subject_observer_e2e_polling():
    with tempfile.TemporaryDirectory() as tmpdir:
        created_events = []
        deleted_events = []

        with FolderSubject(
            paths=[tmpdir], backend="polling", interval=0.1,
        ) as fs:
            assert fs.backend_name == "polling"
            assert fs.is_running

            obs = FolderObserver(
                on_folder_created=lambda fd: created_events.append(fd),
                on_folder_deleted=lambda fd: deleted_events.append(fd),
            )
            obs.attach(fs)

            time.sleep(0.2)

            child = os.path.join(tmpdir, "e2e_child")
            os.mkdir(child)
            time.sleep(0.4)

            os.rmdir(child)
            time.sleep(0.4)

        assert not fs.is_running
        assert len(created_events) >= 1
        assert len(deleted_events) >= 1


# ====================================================================
# 导出符号测试
# ====================================================================


def test_reactive_exports_folder_symbols():
    import vools.reactive as r

    expected = [
        "FolderChangeType",
        "FolderData",
        "FolderSubject",
        "FolderObserver",
        "FolderDispatcher",
        "from_foldersystem",
        "write_to_foldersystem",
    ]
    for sym in expected:
        assert hasattr(r, sym), f"Missing export: {sym}"
        assert sym in r.__all__
