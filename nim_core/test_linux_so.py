import ctypes
import ctypes.util

# Try RTLD_GLOBAL
lib_path = '/mnt/e/IDEProjects/AI/vools/vools/lib/linux/libvools_crypto.so'
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
