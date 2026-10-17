"""Auto-converted to pytest function (fix BUG-298).
Original script body now runs only when this test is invoked,
so pytest collection no longer hangs on compiler probes.
"""

def test_run_linux_so():
    import ctypes
    import ctypes.util
    import os

    # 由本文件位置反推仓库根，避免硬编码绝对路径；可用 VOOOLS_CRYPTO_SO 环境变量覆盖
    _REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    lib_path = os.environ.get(
        "VOOOLS_CRYPTO_SO"
    ) or os.path.join(_REPO_ROOT, "vools", "lib", "linux", "libvools_crypto.so")
    print(f"Loading: {lib_path}")

    # Try with RTLD_GLOBAL
    try:
        lib = ctypes.CDLL(lib_path, ctypes.RTLD_GLOBAL)
        print("Loaded with RTLD_GLOBAL OK")
        # Try to find md5_hash
        try:
            f = lib.md5_hash
            print(f"md5_hash found: {f}")
        except AttributeError as e:
            print(f"md5_hash NOT found: {e}")
    except OSError as e:
        print(f"OSError: {e}")
