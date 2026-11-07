# vools-rhop 配置驱动交互示例

> 对齐 `analysis/rhop-PLAN.md` 附录 C「配置驱动 A/B/C 三角交互」：
> **后续只提供配置信息 + 指定动作方式，即可完成任意双方交互**；不存在 p0..pN 跳板链。

## 三角拓扑

任何 rhop 交互都可演化为三种角色，A/B 反向传递只需调换身份复用同一套机制：

| 角色 | 说明 |
|---|---|
| A = SEND | 发送端：加密动作请求包投递到介质/中转 |
| B = RECV | 接收端：取包、解密验证、执行动作、加密回传 |
| C = RELAY | 中转：A/B 不可直连时的暂存/转交（临时自建 HTTP 中转） |

通信图只有两种形态：`A -> B` 直连、`A -> C -> B` 中转，不存在多跳链。

## 配置形态（一份 JSON/dict 描述密钥/角色/介质/动作集）

```json
{
  "name": "demo-roundtrip",
  "key": "demo-key-2026-1107",
  "role": "SEND",
  "sftp": {"host": "...", "user": "...", "dir": "/srv"},
  "online": [{"kind": "sftp", "host": "...", "user": "...", "dir": "/srv"}],
  "shared": {"write": "D:/share", "read": "D:/share"},
  "relay": {"host": "127.0.0.1", "port": 0, "token": "..."}
}
```

- `key`：加密密钥（明文 / `{"path": ...}` / `{"env": ...}` / `{"cipher": ...}`），信封不含密钥
- `role`：本端角色 SEND / RECV / RELAY（一次会话的角色标签，可互换复用）
- 介质三选：`online`（Git/SFTP 在线通道，按优先级）→ `shared`（shared path 多端视图）→ `relay`（中转地址）
- 通道选择链：中转 > 在线通道 > shared path 回退

## 入口：rhop.interact()

```python
from vools.rhop.interact import interact

interact(cfg, action="jump.probe", mode="execute")    # 本端直接执行动作
interact(cfg, action="jump.probe", mode="request")    # 发送侧：加密动作包投递到介质
interact(cfg, action="jump.probe", mode="roundtrip")  # 单机闭环：A->B->A 全链路演示
```

接收侧闭环：`handle_request(cfg, filename)` 取包 -> 解密验证 -> `run_action` -> 加密回传 `res_<filename>`。

公开动作集：`jump.probe / jump.push / jump.pull / jump.sync`（统一 `(cfg, payload) -> dict` 出参，Ω-gate 容错解包）。

## 示例清单

| 文件 | 形态 | 运行方式 |
|---|---|---|
| `roundtrip_demo.py` | 单机闭环（A 发 -> 同进程 B 收执回传 -> A 取回验证） | `python roundtrip_demo.py` |
| `two_proc_send.py` | 双进程 A 端：interact 一键投递 + 轮询取回 | `python two_proc_send.py --wait` |
| `two_proc_recv.py` | 双进程 B 端：handle_request 一键处理回传 | `python two_proc_recv.py --poll` |

### 双进程演示（两个终端）

```bash
# 终端 1（B 端）
python examples/two_proc_recv.py --poll

# 终端 2（A 端）
python examples/two_proc_send.py --wait
```

A 端投递 `jump.probe` 请求包 -> B 端取包解密执行 -> 加密回传 -> A 端取回验证。
全程只有「配置 + 动作名」，无链路控制代码；示例共用 `_demo_share/` 目录作为 shared path 介质。

## 真实介质替换

示例默认使用本地 `_demo_share/` 作为 shared path（零外部依赖即可跑通）。接入真实场景时：

- 换在线通道：配置 `online` 列表（sftp/git），`SftpChannel` 内置 paramiko 优先 + 注入回退；
- 换中转：配置 `relay`（host/port/token），`RelayServer` 收包暂存 + TTL 过期自动关闭；
- 换角色：A/B 反向传递时把 `role` 由 SEND 换成 RECV（或调用 `session.reverse()`），介质与密钥原样复用。
