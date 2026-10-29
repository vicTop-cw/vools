# -*- coding: utf-8 -*-
"""file-key 模式的**可替换密钥目录替身**（KEK 轮换第 3 步的骨架补强）。

文件系统比 keyring 多出四类失败模式，keyring 替身覆盖不到，所以单独做一个：

| 开关 | 模拟的真实场景 | 威胁 |
|---|---|---|
| `fail_create` | 目标文件已存在（**O_EXCL** 的语义）/ 目录只读 | 覆盖掉被引用的 KEK → 数据锁死 |
| `short_write` | 写入过程崩溃/磁盘满 → **文件短写** | 回读比对必须发现长度不对 |
| `fail_unlink` | unlink 抛异常（Windows 文件被占用/权限） | 旧代删不掉 → `cleaned` 必须保持 0 |
| `unlink_lag` | unlink"成功"但文件仍在（AV 隔离/同步恢复） | **删后回读确认**的意义 |

另外提供 `orphans()`：列出"存在但既不被 DB 引用、也不在 `kek_retired` 日志里"的文件，
用来验证"孤儿**只报告不删除**"的保守策略是否被遵守。
"""
import base64
import os


class FakeFileKeys:
    """用内存 dict 模拟 `<vault_dir>/.vault2.key*` 目录。"""

    def __init__(self, root='.vault2.key'):
        self.root = root
        self.files = {}              # {name: bytes(明文 base64 内容)}
        self.fail_create = False
        self.short_write = False
        self.fail_unlink = False
        self.unlink_lag = False
        self.calls = []

    # ── 文件语义 ──
    def create_exclusive(self, name, kek_bytes):
        """O_EXCL 语义：已存在就抛 FileExistsError（绝不覆盖）。"""
        self.calls.append(('create', name, None))
        if self.fail_create or name in self.files:
            raise FileExistsError('FakeFileKeys: 已存在（O_EXCL）：%s' % name)
        payload = base64.b64encode(kek_bytes)
        if self.short_write:
            payload = payload[:8]          # 短写：内容不完整
        self.files[name] = payload

    def read(self, name):
        self.calls.append(('read', name, None))
        return self.files.get(name)

    def exists(self, name):
        return name in self.files

    def unlink(self, name):
        self.calls.append(('unlink', name, None))
        if self.fail_unlink:
            raise PermissionError('FakeFileKeys: unlink 被拒绝：%s' % name)
        if not self.unlink_lag:
            self.files.pop(name, None)

    def chmod_ok(self):
        """POSIX 0600 的替身断言点：真实实现里用 os.open(..., 0o600) + best-effort chmod。"""
        return True

    def names(self):
        return sorted(self.files)

    def orphans(self, referenced, logged):
        """存在但 **既不被引用、也不在日志里** 的文件（保守策略下只报告、不删）。"""
        return sorted(n for n in self.files if n not in referenced and n not in logged)


def decode(name, payload):
    """把替身里的内容解回 32 字节 KEK（长度不对 → 抛错，模拟"短写被回读发现"）。"""
    key = base64.b64decode(payload or b'')
    if len(key) != 32:
        raise ValueError('KEK 文件长度异常（%d != 32）：%s' % (len(key), name))
    return key
