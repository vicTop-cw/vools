"""简易 Win32 同步 ReadDirectoryChangesW 测试"""
import os, time, tempfile, threading, ctypes
from ctypes import wintypes as wt

FILE_ACTION_ADDED = 1
FILE_ACTION_REMOVED = 2
FILE_ACTION_MODIFIED = 3
FILE_ACTION_RENAMED_OLD_NAME = 4
FILE_ACTION_RENAMED_NEW_NAME = 5

FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
FILE_NOTIFY_CHANGE_DIR_NAME = 0x00000002
FILE_NOTIFY_CHANGE_ATTRIBUTES = 0x00000004
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010

kernel32 = ctypes.windll.kernel32
kernel32.ReadDirectoryChangesW.restype = wt.BOOL
kernel32.ReadDirectoryChangesW.argtypes = [
    wt.HANDLE, ctypes.c_void_p, wt.DWORD, wt.BOOL, wt.DWORD,
    ctypes.POINTER(wt.DWORD), ctypes.c_void_p, ctypes.c_void_p,
]
kernel32.CreateFileW.restype = wt.HANDLE
kernel32.CreateFileW.argtypes = [
    wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
    wt.DWORD, wt.DWORD, ctypes.c_void_p,
]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE_VALUE = -1

BUFFER_SIZE = 4096
FILTER = FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_DIR_NAME | FILE_NOTIFY_CHANGE_ATTRIBUTES | FILE_NOTIFY_CHANGE_LAST_WRITE

def watch_directory(path, stop_event):
    hDir = kernel32.CreateFileW(
        path,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if hDir == INVALID_HANDLE_VALUE:
        print(f"CreateFileW failed for {path}")
        return

    try:
        while not stop_event.is_set():
            buffer = ctypes.create_string_buffer(BUFFER_SIZE)
            bytes_returned = wt.DWORD()

            result = kernel32.ReadDirectoryChangesW(
                hDir,
                ctypes.byref(buffer),
                BUFFER_SIZE,
                True,  # watch subtree
                FILTER,
                ctypes.byref(bytes_returned),
                None,  # no overlap => synchronous
                None,  # no completion routine
            )

            if result == 0:
                print("ReadDirectoryChangesW returned 0 (error)")
                break

            if stop_event.is_set():
                break

            # Parse
            pos = 0
            while True:
                next_offset = int.from_bytes(buffer.raw[pos:pos+4], 'little', signed=False)
                action = int.from_bytes(buffer.raw[pos+4:pos+8], 'little', signed=False)
                fname_len = int.from_bytes(buffer.raw[pos+8:pos+12], 'little', signed=False)
                fname_bytes = bytes(buffer.raw[pos+12:pos+12+fname_len])
                fname = fname_bytes.decode('utf-16-le', errors='replace')
                full_path = os.path.join(path, fname)
                is_dir = os.path.isdir(full_path)

                print(f"  [raw] action={action}, name={fname}, is_dir={is_dir}")

                if next_offset == 0:
                    break
                pos += next_offset

    finally:
        kernel32.CloseHandle(hDir)
        print("watch_directory thread exiting")


def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Watching: {tmpdir}")

        stop_event = threading.Event()
        t = threading.Thread(target=watch_directory, args=(tmpdir, stop_event), daemon=True)
        t.start()
        time.sleep(0.3)

        child = os.path.join(tmpdir, "new_dir")
        print(f"\n=== Creating directory: {child} ===")
        os.mkdir(child)
        time.sleep(1.0)

        print(f"\n=== Removing directory: {child} ===")
        os.rmdir(child)
        time.sleep(1.0)

        print(f"\n=== Renaming ===")
        old = os.path.join(tmpdir, "old_dir")
        new = os.path.join(tmpdir, "new_dir2")
        os.mkdir(old)
        time.sleep(0.3)
        os.rename(old, new)
        time.sleep(1.0)

        stop_event.set()
        t.join(timeout=2)
        print("\nDone")


if __name__ == "__main__":
    main()
