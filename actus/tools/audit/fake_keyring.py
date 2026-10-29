# -*- coding: utf-8 -*-
"""可替换的 **keyring 替身**：用于 KEK 轮换第 2 步（keyring 双代 + 日志 + GC）的崩溃矩阵测试。

为什么需要专门的替身（而不是 `keyring` 的内存后端）：
真实 keyring 后端的失败模式**远不止"存/取/删"三种**，而 KEK 轮换的正确性恰恰依赖
"外部条目在哪一刻变成/不再变成事实"。设计文档 §2 的 6 个崩溃点里，有一半只有在
**外部 store 行为异常**时才暴露。本替身把这些异常做成**可开关的故障模式**：

| 模式 | 模拟的真实场景 | 对 GC 的威胁 |
|---|---|---|
| `fail_write` | 凭据库锁了 / 权限不够 / 用户拒绝授权 | 新 KEK 没写成功 → 绝不能提交 DB |
| `stale_read` | 后端缓存 / 同步延迟：刚写的值读回**旧值** | 写后自检会拿到旧 KEK → 误判"新代可用" |
| `fail_delete` | 删除被策略拒绝 / 条目正被其他进程占用 | 旧 KEK 删不掉 → 必须留 `cleaned=0` 待重试 |
| `delete_lag` | 删除"成功"但条目**其实还在**（后端延迟/最终一致） | **最关键**：若 GC 直接标 `cleaned=1`，旧 KEK 永远残留 |
| `restart_drop` | 进程重启后条目丢失（凭据库被清 / 云同步回滚） | 若 DB 已指向该代 → **seed 永久解不开**（I1 违反） |

⚠️ **`delete_lag` 与 `restart_drop` 是本轮骨架的重点**：它们分别对应
"删了但还在"与"条目消失"，是 `cleaned` 标记与 I1/I2 不变式最容易出错的两端。
"""
import base64
import hashlib


class FakeKeyring:
    """keyring 的最小替身（可注入故障、可模拟重启）。"""

    def __init__(self):
        self._store = {}                 # {user: value}
        self._volatile = set()           # 这些 user 在 restart 后丢失（模拟云同步/清库）
        self.fail_write = False
        self.fail_delete = False
        self.stale_read_once = False     # 下一次 get 返回**旧值**（模拟后端缓存）
        self.delete_lag = False          # delete 返回成功但条目仍在
        self.restart_drop_volatile = True
        self.calls = []                  # [(op, user, value/None)]，便于断言顺序
        self._prev = {}                  # user -> 上一次写入前的值（stale_read 用）

    # ── 故障开关 ──
    def break_all(self):
        self.fail_write = self.fail_delete = True
        self.stale_read_once = True
        self.delete_lag = True

    # ── keyring 兼容接口 ──
    def set_password(self, service, user, value):
        self.calls.append(('set', user, value))
        if self.fail_write:
            raise RuntimeError('FakeKeyring: 凭据库拒绝写入（fail_write）')
        self._prev[user] = self._store.get(user)      # 记录旧值，供 stale_read 返回
        self._store[user] = value

    def get_password(self, service, user):
        self.calls.append(('get', user, None))
        if self.stale_read_once:
            # 模拟后端缓存/同步延迟：**这一次**读到的是写入前的旧值
            self.stale_read_once = False
            return self._prev.get(user)
        return self._store.get(user)

    def delete_password(self, service, user):
        self.calls.append(('del', user, None))
        if self.fail_delete:
            raise RuntimeError('FakeKeyring: 删除被拒绝（fail_delete）')
        existed = user in self._store
        if not self.delete_lag:
            self._store.pop(user, None)
        # delete_lag: 声称成功，但条目仍在（最终一致/后端延迟）
        return None if existed else None

    # ── 仿真辅助 ──
    def mark_volatile(self, user):
        """标记该条目"重启后会消失"（模拟云同步回滚 / 凭据库被清）。"""
        self._volatile.add(user)

    def restart(self):
        """模拟进程重启：volatile 条目丢失，其余保留。"""
        if self.restart_drop_volatile:
            for user in self._volatile:
                self._store.pop(user, None)
        self.calls = []
        return self

    def snapshot(self):
        return dict(self._store)

    def has(self, user):
        return user in self._store


class FakeKeyringModule:
    """把替身包装成 `vault2` 期望的 `keyring` 模块形状（有 get/set/delete_password）。"""

    def __init__(self, backend=None):
        self.backend = backend or FakeKeyring()

    def set_password(self, service, user, value):
        return self.backend.set_password(service, user, value)

    def get_password(self, service, user):
        return self.backend.get_password(service, user)

    def delete_password(self, service, user):
        return self.backend.delete_password(service, user)


def kek_locator(identity_id, gen):
    """KEK 在 keyring 里的 locator 约定（设计文档 §4.2）。"""
    return '%s#g%d' % (identity_id, gen)


def make_kek(identity_id, gen, salt_hex='00' * 8):
    """确定性地造一把 32 字节 KEK（测试用；真实实现用 secrets.token_bytes）。"""
    return hashlib.sha256(('%s|%s|%s' % (identity_id, gen, salt_hex)).encode('utf-8')).digest()


def b64(key_bytes):
    return base64.b64encode(key_bytes).decode('ascii')
