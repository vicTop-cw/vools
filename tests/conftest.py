"""pytest configuration for vools tests"""
import os
import sys

import pytest


# ---------------------------------------------------------------------------
# Custom markers registration (also declared in pyproject.toml).
#  - integration:  tests relying on external resources (clipboard, file system
#                  watchers, keyboard/mouse hooks, etc.)
#  - windows_only: tests that only run on Windows (pywin32 / win32api hooks)
#  - slow:         long running tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_caches():
    """在每个测试前清理所有缓存"""
    from vools.cache import memorize as _mem  # noqa: F401

    try:
        from vools.cache import clear_cache as clear_sig_cache
    except Exception:
        clear_sig_cache = None

    try:
        from vools.decorators.overload import reset_registry
    except Exception:
        reset_registry = None

    if clear_sig_cache is not None:
        try:
            clear_sig_cache()
        except Exception:
            pass

    if reset_registry is not None:
        try:
            reset_registry()
        except Exception:
            pass

    yield

    if clear_sig_cache is not None:
        try:
            clear_sig_cache()
        except Exception:
            pass
    if reset_registry is not None:
        try:
            reset_registry()
        except Exception:
            pass


def pytest_collection_modifyitems(config, items):
    """Auto-skip `windows_only` / `integration` markers on unsupported platforms.

    This complements the `-m "not integration and not windows_only"` filter in CI.
    """
    skip_windows = pytest.mark.skip(reason="requires Windows")
    skip_integration = pytest.mark.skip(
        reason="integration test skipped by default; "
        "run with `-m integration` or `-m 'integration or windows_only'` to enable"
    )

    for item in items:
        if "windows_only" in item.keywords and not sys.platform.startswith("win"):
            item.add_marker(skip_windows)
