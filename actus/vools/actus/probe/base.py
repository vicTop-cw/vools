"""probe/base.py — 探测基类与数据结构。

ProbeItem: 单个探测项的标准化结果
Prober: 探测基类，提供 run() 模板方法
"""

__all__ = ['ProbeItem', 'Prober']

import time
from typing import Any, Dict, List, Optional


class ProbeItem:
    """单个探测项的结果。"""

    def __init__(self, name: str, category: str = "", **kwargs: Any):
        self.name = name
        self.category = category
        self.available = kwargs.get("available", False)
        self.path = kwargs.get("path")
        self.version = kwargs.get("version")
        self.error = kwargs.get("error")
        self.extra = kwargs.get("extra", {})
        self._elapsed_ms = kwargs.get("elapsed_ms")

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "name": self.name,
            "category": self.category,
            "available": self.available,
            "path": self.path,
            "version": self.version,
        }
        if self.error:
            d["error"] = self.error
        if self.extra:
            d["extra"] = self.extra
        if self._elapsed_ms is not None:
            d["elapsed_ms"] = round(self._elapsed_ms, 1)
        return d

    def __repr__(self):
        status = "✓" if self.available else "✗"
        ver = f" {self.version}" if self.version else ""
        return f"{status} {self.name}{ver}"


class Prober:
    """探测基类。子类实现 probe() 方法。"""

    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self._results: List[ProbeItem] = []

    def run(self) -> List[ProbeItem]:
        """执行探测，返回结果列表。"""
        t0 = time.time()
        try:
            self._results = self.probe()
        except Exception as e:
            self._results = [ProbeItem(
                name=self.__class__.__name__,
                category=self.__class__.__name__,
                available=False,
                error=str(e),
            )]
        elapsed = (time.time() - t0) * 1000
        for item in self._results:
            if item._elapsed_ms is None:
                item._elapsed_ms = elapsed
        return self._results

    def probe(self) -> List[ProbeItem]:
        """子类实现：执行具体探测逻辑。"""
        raise NotImplementedError