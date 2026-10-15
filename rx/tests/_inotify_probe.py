"""WSL 侧 inotify 探针：验证 FolderDispatcher(inotify) 真实可用（供委托测试内部复用）。

不作为 pytest 测试收集（无 test_ 前缀）；由 test_reactive_folder_watcher 的
Windows 分支通过 `wsl python3 _inotify_probe.py` 调用，stdout 打印 PASS/FAIL。
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.reactive import FolderDispatcher, FolderChangeType


def main():
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
        types = {fd.change_type for fd in received}
        if (
            d.backend_name == "inotify"
            and len(received) >= 1
            and FolderChangeType.FOLDER_CREATED in types
        ):
            print("PASS")
            return 0
        print("FAIL backend=%s n=%d types=%s" % (d.backend_name, len(received), types))
        return 1


if __name__ == "__main__":
    sys.exit(main())
