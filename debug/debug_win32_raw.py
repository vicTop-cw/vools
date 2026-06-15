"""极简 Win32 事件监听测试 - 无过滤"""
import os, time, tempfile, threading, ctypes
from ctypes import wintypes as wt

FILE_LIST_DIRECTORY = 0x0001
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OVERLAPPED = 0x40000000
GENERIC_READ = 0x80000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3

FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
FILE_NOTIFY_CHANGE_DIR_NAME = 0x00000002
FILE_NOTIFY_CHANGE_ATTRIBUTES = 0x00000004
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010

FILE_ACTION_ADDED = 1
FILE_ACTION_REMOVED = 2
FILE_ACTION_MODIFIED = 3
FILE_ACTION_RENAMED_OLD_NAME = 4
FILE_ACTION_RENAMED_NEW_NAME = 5

class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", wt.DWORD),
        ("OffsetHigh", wt.DWORD),
        ("hEvent", ctypes.c_void_p),
    ]

class FILE_NOTIFY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("NextEntryOffset", wt.DWORD),
        ("Action", wt.DWORD),
        ("FileNameLength", wt.DWORD),
        ("FileName", wt.WCHAR * 1),
    ]

kernel32 = ctypes.windll.kernel32

kernel32.CreateFileW.argtypes = [
    wt.LPCWSTR, wt.DWORD, wt.DWORD,
    ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.c_void_p,
]
kernel32.CreateFileW.restype = ctypes.c_void_p

kernel32.CreateIoCompletionPort.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
]
kernel32.CreateIoCompletionPort.restype = ctypes.c_void_p

kernel32.GetQueuedCompletionStatus.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(wt.DWORD),
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(ctypes.POINTER(OVERLAPPED)),
    wt.DWORD,
]
kernel32.GetQueuedCompletionStatus.restype = wt.DWORD

kernel32.ReadDirectoryChangesW.argtypes = [
    ctypes.c_void_p,   # hDirectory
    ctypes.c_void_p,   # lpBuffer
    wt.DWORD,          # nBufferLength
    wt.BOOL,           # bWatchSubtree
    wt.DWORD,          # dwNotifyFilter
    ctypes.POINTER(wt.DWORD),  # lpBytesReturned
    ctypes.POINTER(OVERLAPPED),  # lpOverlapped
    ctypes.c_void_p,   # lpCompletionRoutine
]
kernel32.ReadDirectoryChangesW.restype = wt.BOOL

kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = wt.BOOL

def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Watching: {tmpdir}")

        hDir = kernel32.CreateFileW(
            tmpdir,
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED,
            None,
        )
        if hDir == -1:
            print(f"CreateFileW failed! hDir={hDir}")
            return
        print(f"hDir={hDir}")

        hCompPort = kernel32.CreateIoCompletionPort(hDir, None, 0, 1)
        print(f"hCompPort={hCompPort}")

        BUFFER_SIZE = 65536
        buffer = ctypes.create_string_buffer(BUFFER_SIZE)
        bytes_returned = wt.DWORD()
        overlapped = OVERLAPPED()
        hEvent = kernel32.CreateEventW(None, True, False, None)
        overlapped.hEvent = hEvent

        FILTER = FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_DIR_NAME | FILE_NOTIFY_CHANGE_ATTRIBUTES | FILE_NOTIFY_CHANGE_LAST_WRITE

        success = kernel32.ReadDirectoryChangesW(
            hDir,
            ctypes.byref(buffer),
            BUFFER_SIZE,
            True,
            FILTER,
            ctypes.byref(bytes_returned),
            ctypes.byref(overlapped),
            None,
        )
        print(f"ReadDirectoryChangesW success={success}")

        # Now make an action
        child = os.path.join(tmpdir, "new_dir")
        print(f"Creating directory: {child}")
        os.mkdir(child)
        print(f"Created. Waiting for events...")

        # Wait for events for up to 3 seconds
        for _ in range(30):
            ov2 = OVERLAPPED()
            ov2.hEvent = kernel32.CreateEventW(None, True, False, None)
            buf2 = ctypes.create_string_buffer(BUFFER_SIZE)
            br2 = wt.DWORD()
            kernel32.ReadDirectoryChangesW(
                hDir,
                ctypes.byref(buf2),
                BUFFER_SIZE,
                True,
                FILTER,
                ctypes.byref(br2),
                ctypes.byref(ov2),
                None,
            )
            overlapped_ptr = ctypes.POINTER(OVERLAPPED)()
            bytes_out = wt.DWORD()
            comp_key = ctypes.c_void_p()

            rc = kernel32.GetQueuedCompletionStatus(
                hCompPort,
                ctypes.byref(bytes_out),
                ctypes.byref(comp_key),
                ctypes.byref(overlapped_ptr),
                100,  # 100ms timeout
            )

            if rc == 0:
                # timeout or error
                continue

            # Parse buffer
            buf_addr = ctypes.addressof(buf2)
            pos = 0
            print(f"[EVENT LOOP] bytes_out={bytes_out.value}")

            while True:
                pInfo = ctypes.cast(
                    buf_addr + pos,
                    ctypes.POINTER(FILE_NOTIFY_INFORMATION),
                ).contents

                if pInfo.FileNameLength > 0:
                    name_chars = pInfo.FileNameLength // 2
                    name_buf = ctypes.create_unicode_buffer(name_chars)
                    ctypes.memmove(
                        name_buf,
                        buf_addr + pos + ctypes.sizeof(FILE_NOTIFY_INFORMATION),
                        pInfo.FileNameLength,
                    )
                    full_path = os.path.join(tmpdir, name_buf.value)
                    action = pInfo.Action
                    is_dir = os.path.isdir(full_path)
                    print(f"  ACTION={action}, name={name_buf.value}, is_dir={is_dir}")

                if pInfo.NextEntryOffset == 0:
                    break
                pos += pInfo.NextEntryOffset

        print("Cleanup")
        kernel32.CloseHandle(hDir)
        kernel32.CloseHandle(hCompPort)
        kernel32.CloseHandle(hEvent)

if __name__ == "__main__":
    main()
