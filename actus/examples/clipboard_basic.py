"""vools.actus 剪贴板能力示例 A：读 / 写 / 清空全链路（真实系统剪贴板）。

演示目标（对齐 docs/DEVELOPMENT_STANDARDS.md r1-doc-as-impl）：
    只调用「配置 + 动作」式 API（clip_write / clip_read / clip_clear），
    完成 写 -> 读回验证 -> 清空 的完整动作序列，无需任何链路控制代码。

运行：
    python examples/clipboard_basic.py

说明：脚本会对系统剪贴板做真实读写（Windows 全局剪贴板），
使用唯一前缀文本避免与其它剪贴板活动互相干扰。
"""
from __future__ import print_function

import os
import sys
import time

# vools.actus 位于 actus/vools/actus，vools.reactive 位于 rx/vools/reactive，
# 两者都要可导入（命名空间包合并）。
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))             # actus 根 -> vools.actus
sys.path.insert(1, os.path.join(_HERE, "..", "..", "rx"))  # rx 根 -> vools.reactive

from vools.actus import clip_clear, clip_read, clip_write  # noqa: E402

_MARK = "actus-example-basic-%d" % int(time.time())


def main():
    # 1) 动作：写
    written = clip_write(_MARK, tags=["actus", "example"], source="clipboard_basic")
    print("[write]", repr(written.content), "tags=", list(written.tags),
          "source=", written.metadata.get("_source"))

    # 2) 动作：读（真实读回验证一致）
    cd = clip_read()
    print("[read]", cd.change_type.name, repr(cd.content))
    if cd.content != _MARK:
        raise SystemExit("读回内容与写入不一致: %r != %r" % (cd.content, _MARK))

    # 3) 动作：清空（清空后为 CLEAR 或空文本，不同平台表现不同）
    clip_clear()
    after = clip_read()
    print("[clear]", after.change_type.name, repr(after.content))
    assert after.change_type.name == "CLEAR" or after.content in ("", None)

    print("CLIP_BASIC_OK")


if __name__ == "__main__":
    main()
