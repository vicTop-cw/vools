---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 9f2a11add43fbf12a546606fb2b962ab_ddb8099ccab911f18b7f525400393706
    ReservedCode1: Blnf+mMK7m9xPu9wuG50Zuw67wLDQIGseWpDJRwm/JLF54GgX9khlytvIZVLPmO0ku+uH+04Zl5PD2iOzp0u9/8gmIxypT9rIH+9NTbHJYSU+ldiKcwtnq2ddjiQ5/1mJFbqop1OxIEjUTJxXSoc22YEB3egffG3WDMo0bCUaG2m2sqGo2mYl4DYx38=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 9f2a11add43fbf12a546606fb2b962ab_ddb8099ccab911f18b7f525400393706
    ReservedCode2: Blnf+mMK7m9xPu9wuG50Zuw67wLDQIGseWpDJRwm/JLF54GgX9khlytvIZVLPmO0ku+uH+04Zl5PD2iOzp0u9/8gmIxypT9rIH+9NTbHJYSU+ldiKcwtnq2ddjiQ5/1mJFbqop1OxIEjUTJxXSoc22YEB3egffG3WDMo0bCUaG2m2sqGo2mYl4DYx38=
---

# vools-rhop

**R**elay **H**op **O**rchestration **P**rotocol — 双方对等镜像任务中继协议。

当前为 **MVP 范围**（2026-10-18 确认），只做两件事：

| MVP | 内容 | 落点 |
|---|---|---|
| MVP-1 | 抽象密钥函数：本地固定密钥加密 JSON / 解密验证 | `vools/rhop/crypto.py` |
| MVP-2 | shared path 传输（在线优先 / 离线回退）+ vools-rx 触发器监控 | `vools/rhop/transport/`、`vools/rhop/watch.py` |

MVP 出口判据：

1. 本地固定密钥能对 JSON 加密，且解密验证通过 / 失败可明确区分
2. 同一机器两进程（A/B 模拟）通过 shared path 收发一包加密 JSON 成功
3. 有网介质（Git/SFTP）可用时优先走在线通道，不可用时自动回退 shared path
4. 接收方用 vools-rx 触发器监控到新文件并成功解密验证

完整 v2 设计（镜像 DB / 状态机 / 业务 API）见 `analysis/rhop-PLAN.md`。

## 地基规划（2026-10-18）

将 rhop 打磨为**配置驱动、A/B/C 三角拓扑**交互地基：只提供配置 + 指定动作方式，即可完成任意双方交互。

- **Step 1 已完成**：SftpChannel 升级为 **paramiko 优先 + 注入式回退**（真实 put/get/listdir/mkdirs/exists，缺失回退不阻断链路）；52/52 测试通过，本地 paramiko SFTPServer 真实往返验证通过。
- **Step 2-4 待办**：actus jump 改装公开动作集 → A/B/C 三角与身份互换 → 配置驱动入口 + vq 迁移。

拓扑约束：废弃 p0..pN 跳板链，统一 A[发送端]/B[接收端]/C[中转] 三角，A/B 反向传递只需调换身份。

文档索引：

- 地基规划状态一览：`docs/groundwork.md`
- SftpChannel 使用说明与验证记录：`docs/sftp-channel.md`
- 详细规划与出口判据：`analysis/rhop-PLAN.md` 附录 C
*（内容由AI生成，仅供参考）*
