# 测试盲区谱系（16 轮积累）

> 核实于 2026-10-29。扫描器：`actus/tools/audit/test_blindspots.py`（可复跑，只读）。

## 为什么需要这份文档

`pytest -k vault` 曾经 **54 passed 全绿**，而 `master_key` 的派生把 60 秒 TOTP
动态码混进了 KDF —— **L2/L3 的 secrets 在下一个时间窗口就永久解不开**。

**测试没有抓到，不是因为它写得差，而是因为所有用例都在同一个 60 秒窗口内跑完。**

> **测试全绿不是因为它对，而是因为它跑得太快。**

这份文档把 16 轮陆续发现的盲区类型固化下来，作为**写新测试时的检查清单**。

---

## 五类已知盲区

### 1. 只测一个入口

**表现**：同一个能力有 CLI / MCP / Python API 三个入口，测试只覆盖一个。

**例子**：`vault set` 在 CLI 返回 `rc=0` 而 MCP 返回 `isError=True`（同一份 refused 结果）。

**判据**：**同一能力是否有对拍**（不是"文件里是否出现两个词"）。
合理的分层测试（`test_cli_*` 只测 CLI、`test_mcp_*` 只测协议）**不算盲区**，
除非该能力缺一条跨入口的一致性用例。

**修法**：加三方一致性矩阵 / 同 target 输出对拍。

### 2. 断言源码字符串

**表现**：`assert "depth >= 5" in src`、`assert "CERT_NONE" not in src`。

**后果**：行为坏了不红（字符串还在），**重构必红**（改了字面量）。

**例子**：`test_kind_dispatch.py` 把守卫改成 `if depth >= 5 and False:`（永久失效）→ 三条子串断言**仍全部命中**。

**修法**：改成行为断言；负向断言（`CERT_NONE`）保留但要加行为对照。

### 3. 假设基线干净

**表现**：断言绝对数量，而进程里已有前一个用例留下的状态。

**例子**：`assert bus.subscriber_count() == before + 2`，但 `before` 实际是 2（不是 0）→
单独跑绿、整套跑红。

**修法**：断言**相对增量**（`after == before + N`）或**不累积**（`after_second == after_first`）。

### 4. 断言旧语义

**表现**：产品已改成零写/新语义，测试仍断言旧行为。

**最危险的一种：护栏反向。**
> `test_cli_no_side_effects.py` 的白名单仍允许 `info` 写 mtimes 缓存，
> 而 `info` 早已修为零写 → 一旦回归成写，这套"防回归"测试**照样绿**。

**修法**：白名单每一条都必须写明"**为什么这个写是合理的**"，并**拒绝**
「现在会写 / 因为它现在…」这类借口 —— 那正是护栏反向的成因。

### 5. 时间跨度不够 ★

**表现**：所有涉及时间/过期/超时的断言都在**单个时间点**验证。

**例子（这是 P0 的根因）**：
- `test_expired_token_rejected` 手动 `expires_at = 0`（epoch 远过去）→ 只测"极端点"
- 缓存过期用 `timestamp: 1` + `max_age=999999`（永不过期）→ 边界完全没测
- `SESSION_TTL` 在 tests 中 **grep = 0**

**修法**：用可控假时钟推进时间，测**边界两侧**（`TTL-1` 仍有效 / `TTL+1` 失效）。

---

## 第 6 类（2026-10-29 新发现）：全局单例 / 进程状态顺序依赖

**表现**：测试绿不绿取决于**整套执行顺序与手动清理**。

**证据**：
- `test_round11_capabilities.py` 注释自认「其它测试文件遗留的转发订阅」，用例开头手动 `_detach_event_forwarding()`
- `test_mcp_async_tasks.py` 有 autouse fixture 手动 `_TASKS.clear()`
- `vault2._vault2_singleton` / `security._scanner` / `eventbus._bus` 均为进程单例，无统一 fixture 重置

**后果**：**pytest-xdist / 顺序变化下随机红**，且**掩盖"单例状态未清理"的真实产品缺陷**。

> **"随机红"比"稳定红"更糟** —— 因为人会开始忽略红灯。

**修法**：`conftest.py` 加 `reset_globals` autouse fixture（用例**前后各一次**），
并**删除**各文件里的手动清理（保留会让人以为"每个测试都要自己清"）。

---

## 6b. 常量转述式断言（小类）

`assert args3.max_age == 3600`、`assert QUALITY_LEVELS == (...)` ——
断言的是**实现常量**，不是行为。合法改默认值会红，行为坏了不会红。

**修法**：断言"默认值来自配置/可覆盖"或"等级只断言排序/成员语义"。

---

## 必备夹具：`advance_totp_window(n)`（`tests/conftest.py`）

**存在原因 = 14 轮全绿但 P0 存在的根因是测试时间跨度不够。**

```python
class _TotpClock:                     # 可推进假时钟
    def time(self): return self.now
    def __getattr__(self, name): return getattr(_real_time, name)

@pytest.fixture
def advance_totp_window(monkeypatch):
    from vools.actus import vault2 as _vault2
    from vools.security import otp as _otp
    clock = _TotpClock(_real_time.time())
    monkeypatch.setattr(_vault2, "time", clock)   # 会话过期/审计/used_codes
    monkeypatch.setattr(_otp, "time", clock)      # ★ TOTP 算法本体（core otp.py）
    def advance(n=1):
        clock.now += float(n) * 60.0
        return clock.now
    advance.clock = clock
    advance.seconds = lambda n: ...   # 秒级推进（TTL 边界用）
    return advance
```

**必须同时 patch 两处** —— `generate_dynamic_code` 定义在 **core 的 `vools/security/otp.py`**，
`vault2` 只是 import 引用。只 patch `vault2.time` 时动态码仍按真实时间生成 →
窗口推进后第二次 auth 会报「动态码已被使用」（replay），**根本走不到跨窗口解密**。

（cmd-engine 和 cmd-test **各自独立踩到了这个坑**，所以写在这里。）

---

## 写新测试时的检查清单

- [ ] 这个能力有 CLI / MCP / API 三个入口吗？**至少一条跨入口对拍**
- [ ] 有没有 `assert "...in src"`？→ 改行为断言
- [ ] 有没有断言绝对数量？→ 改相对增量
- [ ] 产品最近改过语义吗？→ 确认断言的是**新语义**
- [ ] 涉及时间/过期吗？→ **用假时钟测边界两侧，禁止 `sleep`**
- [ ] 有没有依赖进程单例？→ 用 `reset_globals` fixture，**不要手动清理**
- [ ] 断言的是实现常量吗？→ 改行为/语义断言

---

## 正面样本（怎么写对的）

1. `test_vault_cross_window.py` + `conftest.advance_totp_window` —— 不 sleep、patch 两处 time、验证跨窗口密码学前提
2. `test_vault_readonly_contracts.py::test_resolve_secret_reads_are_byte_identical` —— `sleep(1.05)` 保证 seconds 级写必然可见 + db sha256/mtime 快照
3. `test_cli_no_side_effects.py` —— 递归快照路径 + size + mtime_ns + sha256，断言**磁盘状态**而不是输出内容
4. `test_new_capabilities.py` 的 CLI/MCP **共用同一份 success 判据**
5. `test_round11_capabilities.py::test_cleanup_artifacts_really_deletes_files` —— 真文件 + `files_removed`/`reclaimed_bytes` 双断言
6. **变异验证**：不只是"让测试红"，而是"**重演真实的历史 bug，看测试能不能抓到同一个现场**"，
   且**对照组保持绿**（证明精确性，不是碰巧全红）
