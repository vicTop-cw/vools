"""
vools/_nim_crypto.py (Deprecated)

This module is deprecated and will be removed in a future version.
Use vools.bridge.nim.crypto instead.
"""

import warnings

warnings.warn(
    "vools._nim_crypto is deprecated, use vools.bridge.nim.crypto instead",
    DeprecationWarning,
    stacklevel=2
)

from .bridge.nim.crypto import md5, sha1, sha256, hmac_sha256, hmac_md5

def is_nim_available():
    from .bridge.nim._loader import is_nim_available as _is_avail
    return _is_avail()
