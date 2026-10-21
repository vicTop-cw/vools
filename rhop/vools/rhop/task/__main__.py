"""``python -m vools.rhop.task`` 入口。"""

from __future__ import absolute_import

import sys

from .cli import main

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())