# -*- coding: utf-8 -*-
"""actus 测试套件全局夹具：**运行时数据目录默认隔离**（测试卫生）。

背景（第 15 轮，真实事故）：测试套件跑完会把真实仓库 `_meta/` 写脏
（`events.jsonl` / `probe_cache.json` / `actions.index.json` / `call_log.db` /
`runs/*.json` / `status.json` / `logs/*`）。它们是 gitignore 的运行时状态，但同属
「测试写真实仓库文件」——与 `calculator.actus.schema.md` 被中断污染同族：
并发跑、CI 次跑之间会互相影响，也让「零副作用」类断言失真。

做法：autouse 把 `ACTUS_META_DIR` 默认指到 per-test tmp 目录。各用例自己
`monkeypatch.setenv("ACTUS_META_DIR", ...)` 时（更具体）仍以用例为准。
本夹具**不碰** `actions/`、`contracts/` 等真实产物目录（那是产物，不是运行时状态）。
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_meta_dir(tmp_path, monkeypatch):
    """默认把 `_meta` 运行时目录隔离到 tmp，防止测试写真实仓库的 `_meta/`。"""
    monkeypatch.setenv("ACTUS_META_DIR", str(tmp_path / "_meta_runtime"))
