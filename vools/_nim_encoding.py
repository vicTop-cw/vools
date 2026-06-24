"""
vools/_nim_encoding.py (Deprecated)

This module is deprecated and will be removed in a future version.
Use vools.bridge.nim.encoding instead.
"""

import warnings

warnings.warn(
    "vools._nim_encoding is deprecated, use vools.bridge.nim.encoding instead",
    DeprecationWarning,
    stacklevel=2
)

from .bridge.nim.encoding import base64_encode, base64_decode, zlib_compress, zlib_decompress

def is_nim_encoding_available():
    from .bridge.nim._loader import is_nim_available as _is_avail
    return _is_avail()
