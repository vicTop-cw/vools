"""
vools/_nim_loader.py (Deprecated)

This module is deprecated and will be removed in a future version.
Use vools.bridge.core.loader instead.
"""

import warnings

warnings.warn(
    "vools._nim_loader is deprecated, use vools.bridge.core.loader instead",
    DeprecationWarning,
    stacklevel=2
)

from .bridge.core.loader import load_nim_lib, is_nim_available
