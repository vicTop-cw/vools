---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 9f2a11add43fbf12a546606fb2b962ab_69ee5053caed11f196f9525400248c00
    ReservedCode1: Joo3umcPxQOcSKv0mucvVpgAQNNbJBiB8XbiuJEBF7jQMUvOdlxMBzC+pEQyyY1Ok271QypDRn+QP2VkPwJFJJavoV0YCpUYNO/haRZPmvXcyZS76pSSrFV5/Wd3c8UyD8KA42WuQ6Pkd9F0MAdsM1ttU49MUNQa5id9sUJ7Y7xuYN8gUKG5K5U8hWo=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 9f2a11add43fbf12a546606fb2b962ab_69ee5053caed11f196f9525400248c00
    ReservedCode2: Joo3umcPxQOcSKv0mucvVpgAQNNbJBiB8XbiuJEBF7jQMUvOdlxMBzC+pEQyyY1Ok271QypDRn+QP2VkPwJFJJavoV0YCpUYNO/haRZPmvXcyZS76pSSrFV5/Wd3c8UyD8KA42WuQ6Pkd9F0MAdsM1ttU49MUNQa5id9sUJ7Y7xuYN8gUKG5K5U8hWo=
---

# rhop 地基规划 — 状态一览（2026-10-18）

将 rhop 打磨为**配置驱动、A/B/C 三角拓扑**的交互地基，供 vq/sparksql-exe 与 actus 升级依赖。

## 目标形态

```
rhop 地基 = 传输介质（可插拔） + 公开动作（可验证） + 三角拓扑（可互换）

交互入口:
    rhop.interact(cfg, action="jump.push", payload={...})
    # cfg: 密钥 + 本端角色(A/B/C) + 介质配置(在线通道列表 + shared path 视图) + 对端/中转地址
    # 自动完成: 选通道 → 加密 → 传输 → 解密验证 → 执行动作 → 回传结果
```

- 发送端 A、接收端 B 只是**一次会话的角色标签**，同一份配置可互换复用（反向传递时交换角色即可）。
- 中转 C 是 A/B 不可直连时的暂存/转交角色。
- 通信图只有两种形态：`A → B` 直连、`A → C → B` 中转；**不存在多跳链**（废弃 p0..pN 跳板链）。

## 改造项与状态

| # | 改造项 | 状态 | 落点 |
|---|---|---|---|
| C2.1 | SftpChannel paramiko 优先 + 注入式回退 | **已完成**（2026-10-18 编码并验证） | `vools/rhop/transport/online.py` |
| C2.2 | actus jump 改装 rhop 公开动作（probe/push/pull/sync） | 待办 | 新建 `vools/rhop/actions/` |
| C2.3 | A/B/C 三角拓扑与身份互换（Role = SEND/RECV/RELAY） | 待办 | 新建 `vools/rhop/session.py` |
| C2.4 | 配置驱动入口（`rhop.interact()` 一键交互） | 待办 | 新建 `vools/rhop/config.py` + `interact.py` |

## Step 1 完成判据（全部通过）

- [x] paramiko 存在：SftpChannel 内建 paramiko 后端，真实 put/get/listdir/mkdirs/exists/read_text/write_text 跑通。
- [x] paramiko 缺失/导入失败：回退注入式 reader/writer，行为不变（`TestSftpChannelParamikoMissing` 覆盖）。
- [x] `select_transport` 中 SftpChannel 可用性判定正确（52/52 测试通过）；paramiko 后端真实一包往返成功（本地 SFTPServer 实测 `BACKEND_OK / PROBE_OK / ROUNDTRIP_OK / FS_OK`；外网 `test@47.93.7.122:10022` 当前 TCP 超时不可达，属外部环境问题，非代码缺陷）。

## 后续 Step

- **Step 2 公开动作集**：`rhop.actions` 提供 `jump.probe/push/pull/sync`，复用 actus 已验证逻辑，schema 公开；跨动作调用带 Ω-gate 容错解包。
- **Step 3 A/B/C 三角**：角色声明 + 对端/中转 endpoint；A→B、A→C→B、B→A 反向三条路径测试通过。
- **Step 4 配置驱动 + vq 迁移**：vq/sparksql-exe `configs.py` 的 ROLE p0..p3 废弃/映射到 A/B/C；`utils/sftp.py` 桥接退化为 SftpChannel 回退实现。

## 文档索引

- 详细规划与出口判据：`analysis/rhop-PLAN.md` 附录 C「地基规划 — 配置驱动 A/B/C 三角交互」
- SftpChannel 用法与验证：`docs/sftp-channel.md`
- 包概览与 MVP：`README.md`

---

## 通用任务队列（2026-10-21 完成，v0.2.0）

在地基之上补齐"**A 提交加密 JSON 指令 → B 解密执行，多任务与依赖由 SQLite 管理**"这一层，
仍然只靠配置：方向（A/B/C）+ 介质 + 存储后端 + 执行白名单。

| # | 能力 | 状态 | 落点 |
|---|---|---|---|
| Q1 | 方向驱动配置（无 P0..P3 跳板角色） | **已完成** | `vools/rhop/task/config.py` |
| Q2 | 数据库抽象（共享单一库 / 双方各自持库 / 可注册 PG） | **已完成** | `vools/rhop/task/store/` |
| Q3 | 任务表 + 状态机 + DAG + 重试 + 取消 + 失效锁回收 | **已完成** | `vools/rhop/task/{models,queue}.py` |
| Q4 | 加密载荷与可加密结果（payload_enc / payload_sha） | **已完成** | `vools/rhop/task/queue.py` |
| Q5 | 心跳 `xxxx.heartbeat`（5 秒时间戳 / `closed` 停机 / 后台线程与任务解耦） | **已完成** | `vools/rhop/task/heartbeat.py` |
| Q6 | 执行白名单（默认只放行代码内注册的动作/处理器） | **已完成** | `vools/rhop/task/exec.py` |
| Q7 | 明文/密文双支持 + 明文告警（含生成命令与回填指引） | **已完成** | `vools/rhop/task/secrets.py`、`vools/rhop/secret.py` |
| Q8 | 本地库模式的加密同步收敛 | **已完成** | `vools/rhop/task/sync.py` |
| Q9 | CLI（submit/serve/once/status/watch/check-heartbeat/close/sync/config） | **已完成** | `vools/rhop/task/cli.py` |
| Q10 | 静态 HTML 配置生成器（离线、页内生成密文、与 Python 互通） | **已完成** | `tools/config_generator.html` |

出口判据（全部通过，2026-10-21）：

- [x] 既有 145 个用例全绿不回退；新增 313 个用例全绿（`rhop/tests` 合计 **458 passed**）
- [x] 共享单一库：A `submit` → B `once` 按依赖顺序执行 → A `status` **无需任何同步**即见 `COMPLETED` 与解密结果
- [x] 双方各自持库：`sqlite-local` + `TaskSync` 收敛，结果回流、取消传播、旧版本不覆盖新状态
- [x] 心跳：B 每 5 秒写时间戳（长任务期间由后台线程照跳）；`closed` 触发 B 优雅停机；冻结/缺失 → A 判 `stale`/`missing` 并退出等待
- [x] 明文配了会告警并打印生成密文的命令；密文可解；`--strict-secrets` 可把明文升级为报错
- [x] 存储后端可切换、未知 kind 明确报错、PG 只需 `register_store(kind, factory)`
- [x] 白名单：未放行的命令落 `FAILED` 且不重试；`allow_any` 才放开
- [x] HTML 生成器：`file://` 离线可用，页内密文与 Python 双向互通（Node 交叉验证）

详细文档：`docs/task-queue.md`；规划附录：`analysis/rhop-PLAN.md` 附录 D。
*（内容由AI生成，仅供参考）*
