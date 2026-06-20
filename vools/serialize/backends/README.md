# vools.serialize.backends — 序列化后端

支持的序列化后端：

| 后端 | 类 | 说明 |
|------|-----|------|
| JSON | `JsonBackend` | JSON 格式（跨语言、可读） |
| Pickle | `PickleBackend` | Python pickle（高性能） |
| MessagePack | `MsgpackBackend` | MessagePack 格式（二进制、紧凑） |
