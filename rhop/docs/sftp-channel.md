---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 9f2a11add43fbf12a546606fb2b962ab_67f8fdb6caed11f18b7f525400393706
    ReservedCode1: giJaBGCjuRxXubKh776WeJ35qBIglb7Ctd68BvN9auXxGPAOrEp8OTFooGCmvwOMqhaHOG3qqwLJrOaTrTtCj0HveO5lCMZvw+SUygzsIOHhSAbeI3HeqA6U2YJmPD1JmpdSWSklVcm+NqOsZwN0eFslb4dqXQN6aS0yHaYgYI9cOpNKEgixGy7LZR8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 9f2a11add43fbf12a546606fb2b962ab_67f8fdb6caed11f18b7f525400393706
    ReservedCode2: giJaBGCjuRxXubKh776WeJ35qBIglb7Ctd68BvN9auXxGPAOrEp8OTFooGCmvwOMqhaHOG3qqwLJrOaTrTtCj0HveO5lCMZvw+SUygzsIOHhSAbeI3HeqA6U2YJmPD1JmpdSWSklVcm+NqOsZwN0eFslb4dqXQN6aS0yHaYgYI9cOpNKEgixGy7LZR8=
---

# SftpChannel 使用说明

`vools.rhop.transport.online.SftpChannel`：SFTP 镜像在线通道，**paramiko 优先 + 注入式回退**。

## 设计要点

- **paramiko 可用**：内建 `_ParamikoSftpBackend`，`send/receive` 走真实 SFTP 读写（put/get），并额外提供 `exists / listdir / mkdirs / read_text / write_text`。
- **paramiko 缺失 / 导入失败**：完全回退注入式 `reader/writer`（兼容旧 MVP 形态），`exists / listdir / mkdirs` 不可用（抛 `NotImplementedError`）。
- **连接失败**：paramiko 后端异常且存在注入 `writer/reader` 时回退注入式；无注入则原样抛出。
- **可用性探测**：`probe` 注入优先；`probe_mode="tcp"`（默认）走 TCP 端口探测；`probe_mode="sftp"` 且 paramiko 可用时走真实 SFTP 连接探测。
- **sftp_cfg 统一入口**：兼容 vq/sparksql-exe `configs.py` 的 `FTP_connect` 形态 `{host, port, user, password, key_path, dir}`，显式参数优先。

## 构造参数

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `host` | str | 必填 | SFTP 主机地址（`sftp_cfg.host` 可覆盖） |
| `remote_dir` | str | 必填 | 远端镜像目录（`sftp_cfg.dir / remote_dir` 可覆盖） |
| `username` | str | `""` | 登录用户（`sftp_cfg.user / username` 可覆盖） |
| `port` | int | `22` | 端口（`sftp_cfg.port` 可覆盖） |
| `password` | str / None | `None` | 密码认证 |
| `key_path` | str / None | `None` | 密钥文件路径（`sftp_cfg.key_path` 可覆盖） |
| `probe` | Callable | `None` | 注入可用性探测函数，优先于 `probe_mode` |
| `reader` | Callable | `None` | 回退读取器 `(channel, filename) -> str` |
| `writer` | Callable | `None` | 回退写入器 `(channel, filename, content)` |
| `probe_mode` | str | `"tcp"` | `"tcp"` TCP 端口探测 / `"sftp"` 真实 SFTP 连接探测 |
| `sftp_cfg` | dict / None | `None` | 统一配置入口（vq 形态），显式参数优先 |

`sftp_cfg` 合并规则：非空字段覆盖同名显式参数；键名兼容 `user`/`username`、`dir`/`remote_dir` 两种写法。

## 公开 API

| 方法 | 语义 | paramiko 缺失时 |
|---|---|---|
| `available()` | 可用性探测（注入 probe > probe_mode） | TCP 探测仍可用 |
| `send(filename, content)` / `put(...)` | 写入远端文件（paramiko 优先，失败回退 writer） | 回退 writer，无 writer 抛错 |
| `receive(filename)` / `get(...)` | 读取远端文件（paramiko 优先，失败回退 reader） | 回退 reader，无 reader 抛错 |
| `read_text(filename)` / `write_text(filename, text)` | 文本读写别名 | 同上 |
| `exists(filename)` | 远端文件存在性（真实 stat） | 抛 `NotImplementedError` |
| `listdir(sub="")` | 远端目录列表 | 抛 `NotImplementedError` |
| `mkdirs(sub="")` | 远端递归建目录 | 抛 `NotImplementedError` |
| `close()` | 关闭 SSH 客户端（复用连接时释放） | 无操作 |

## 使用示例

```python
from vools.rhop.transport import SftpChannel

# 方式一：显式参数 + TCP 探测
ch = SftpChannel(
    host="47.93.7.122",
    port=10022,
    username="test",
    password="***",
    remote_dir="/mirror",
    probe_mode="tcp",
)
ch.send("hello.json", '{"ok": true}')
print(ch.receive("hello.json"))
ch.close()

# 方式二：vq/sparksql-exe 风格统一配置（configs.py FTP_connect 形态）
cfg = {"host": "47.93.7.122", "port": 10022, "user": "test",
       "password": "***", "dir": "/mirror"}
ch2 = SftpChannel(host="", remote_dir="", sftp_cfg=cfg)

# 方式三：paramiko 缺失环境注入回退读写
ch3 = SftpChannel(host="h", remote_dir="/d",
                  writer=lambda ch, fn, c: store_local(fn, c),
                  reader=lambda ch, fn: load_local(fn))
```

## 验证记录（2026-10-18）

- 全量测试 **52/52 通过**；新增 `TestSftpChannelParamiko`（真实 paramiko 后端读写）与 `TestSftpChannelParamikoMissing`（缺失回退）。
- 外网端点 `test@47.93.7.122:10022` 本机无 sshd、TCP 超时不可达（外部环境问题，非代码缺陷）；改用**本地线程内 paramiko SFTPServer 真实往返验证**，业务 `SftpChannel` 走真实 paramiko 后端，输出 `BACKEND_OK / PROBE_OK / ROUNDTRIP_OK / FS_OK` 全通过。
- `select_transport` 中 SftpChannel 可用性判定正确（在线优先 / 离线回退 shared path）。

## 依赖说明

- `paramiko` 为**可选依赖**（本机已装 5.0.0）。vq/sparksql-exe 已打包 paramiko wheel，安装后即走真实 SFTP 后端。
- 未安装 paramiko 不阻断链路上层：SftpChannel 自动回退注入式 reader/writer，`select_transport` 仍可正常工作。
*（内容由AI生成，仅供参考）*
