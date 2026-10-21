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
*（内容由AI生成，仅供参考）*
