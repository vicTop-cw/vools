# vools-rhop — 中继跳转编排协议 {#A21}

> **模块路径**：`vools.rhop`（独立子项目 `rhop/`）
> **依赖版本**：Python 3.6+（WSL/Docker py3.6 已全量验证）
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试（Step 1 全量 52/52 通过）
> **编号**：#A21
> **最后更新**：2026-10-18

---

## 一句话介绍

**R**elay **H**op **O**rchestration **P**rotocol — 双方对等镜像任务中继协议。rhop 提供抽象密钥（加密/解密验证）与 shared path 传输（在线优先 / 离线回退），并配合 vools-rx 触发器实现「有网走在线通道、无网自动回退本地镜像目录」的双向文件镜像。

---

## MVP 范围

| MVP | 内容 | 落点 |
|---|---|---|
| MVP-1 | 抽象密钥函数：本地固定密钥加密 JSON / 解密验证 | `rhop/vools/rhop/crypto.py` |
| MVP-2 | shared path 传输（在线优先 / 离线回退）+ vools-rx 触发器监控 | `rhop/vools/rhop/transport/`、`rhop/vools/rhop/watch.py` |

完整 v2 设计（镜像 DB / 状态机 / 业务 API）见 `analysis/rhop-PLAN.md`。

## 地基规划进度（2026-10-18）

- **Step 1 已完成**：SftpChannel 升级为 **paramiko 优先 + 注入式回退**（真实 put/get/listdir/mkdirs/exists，缺失回退不阻断链路）；52/52 测试通过，本地 paramiko SFTPServer 真实往返验证通过。
- **Step 2-4 待办**：actus jump 改装公开动作集 → A/B/C 三角与身份互换 → 配置驱动入口 + vq 迁移。

拓扑约束：废弃 p0..pN 跳板链，统一 A[发送端] / B[接收端] / C[中转] 三角，A/B 反向传递只需调换身份。

---

## 核心模块

| 模块 | 能力 |
|------|------|
| `vools.rhop.crypto` | 本地固定密钥抽象：`load_key` / `RhopCrypto` / `encrypt_json` / `decrypt_verify`（Fernet 信封） |
| `vools.rhop.transport` | 通道选择与镜像传输：`select_transport` / `OnlineChannel` / `SharedPath` / `SftpChannel` / `GitChannel` |
| `vools.rhop.watch` | `RhopWatcher`：shared path 新文件监控 + 解密验证回调 |

## 公开 API

### 密钥抽象（crypto）

```python
from vools.rhop.crypto import RhopCrypto, load_key

# 方式一：直接给密钥文本
crypto = RhopCrypto.from_key("my-fixed-secret")

# 方式二：从文件读取（load_key 支持 path / env_name / source 三种来源）
crypto = RhopCrypto.from_path("C:/secrets/rhop.key")
crypto = RhopCrypto.from_env("RHOP_KEY")          # 默认环境变量名见 ENV_RHOP_KEY

# 加密 / 解密验证（失败可明确区分，不抛模糊异常）
packed = crypto.encrypt_json({"cmd": "sync", "at": 1})
ok, payload = crypto.decrypt_verify(packed)
```

- 密钥加载顺序：`source`（直接文本）→ `path`（配置文件路径，读其内容）→ `env_name`（环境变量），未找到时抛 `ValueError`。
- 输出格式：`{"v":1,"alg":"fernet","ct":"<token>"}`，基于 Fernet 信封。

### 通道选择（transport）

```python
from vools.rhop.transport import select_transport, SharedPath

ch = select_transport(
    online_channels=[...],      # 在线通道（如 SftpChannel / GitChannel）列表
    shared_path=SharedPath("C:/mirror/relay"),   # 离线回退镜像目录
)
# 在线可用 → 返回第一个在线通道；否则返回 shared path 通道
```

| 通道 | 说明 |
|------|------|
| `OnlineChannel` | 在线通道基类/接口 |
| `SharedPath` | 本地镜像目录通道：`write_text` / `read_text` / 列表等 |
| `SftpChannel` | SFTP 镜像在线通道，**paramiko 优先 + 注入式回退**（详见 [SftpChannel 使用说明](sftp-channel.md)） |
| `GitChannel` | Git 介质在线通道 |

### 新文件监控（watch）

```python
from vools.rhop.transport import SharedPath
from vools.rhop.crypto import RhopCrypto
from vools.rhop.watch import RhopWatcher

watcher = RhopWatcher(
    shared_path=SharedPath("C:/mirror/relay"),
    crypto=RhopCrypto.from_env("RHOP_KEY"),
    on_packet=lambda filename, result: print(filename, result.verified),
)
watcher.start()   # 依赖 vools-rx 的 from_filesystem 监控新文件
# ... 收包处理 ...
watcher.stop()
```

- 依赖 `vools-rx`（`vools.reactive.monitoring.file_watcher`）提供文件事件；未安装时构造抛 `RuntimeError`。
- `_is_target` 按扩展名白名单（`extensions`，默认见 `DEFAULT_EXTENSIONS`）过滤；收到目标文件后读文本 → 解密验证 → 回调 `on_packet(filename, result)`。

---

## 规划状态与文档索引

| 文档 | 内容 |
|------|------|
| `analysis/rhop-PLAN.md` | 详细规划与出口判据（附录 C：Step 1-4 与 vq 迁移） |
| `rhop/docs/groundwork.md` | 地基规划状态一览（C2.1 完成，C2.2-2.4 待办） |
| [SftpChannel 使用说明](sftp-channel.md) | SftpChannel 构造参数、公开 API、示例与验证记录 |
