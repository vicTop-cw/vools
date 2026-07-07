"""
vools.bridge.check_bridges - 桥接库安装验证脚本

检查所有桥接库是否正确安装并可用。
"""

from .core.loader import get_loader, is_available


def check_bridges():
    """
    检查所有桥接库是否正确安装

    返回：
        list: [(lang, name, available), ...] 格式的结果列表
    """
    bridges = [
        ("nim", "serialize"),
        ("nim", "hash"),
        ("nim", "base64"),
        ("nim", "json"),
        ("nim", "sigcache"),
        ("nim", "compress"),
        ("rust", "safe_eval"),
    ]

    results = []
    for lang, name in bridges:
        available = is_available(lang)
        results.append((lang, name, available))

    return results


def check_nim_bridges():
    """
    检查所有 Nim 桥接库

    返回：
        dict: {模块名: 是否可用}
    """
    nim_modules = [
        "serialize",
        "hash",
        "base64",
        "json",
        "sigcache",
        "compress",
    ]

    results = {}
    loader = get_loader("nim")
    for module in nim_modules:
        lib_name = f"vools_bridge_{module}"
        available = loader.load(lib_name) is not None
        results[module] = available

    return results


if __name__ == "__main__":
    print("=== Bridge Status Report ===\n")

    print("General bridges:")
    for lang, name, available in check_bridges():
        status = "✓" if available else "✗"
        print(f"  [{status}] {lang}/{name}")

    print("\nNim modules:")
    for module, available in check_nim_bridges().items():
        status = "✓" if available else "✗"
        print(f"  [{status}] nim/{module}")

    print("\n=== Report Complete ===")
