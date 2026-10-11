# vools.dll32 - 32位 DLL 专用桥接包 Spec

## Why

当前 `vools.sys` 包的 `@dll` 装饰器在 64 位 Python 环境下无法调用 32 位 DLL（如 VB6 编译的 DLL）。许多优秀的 Windows 工具库（如 VB6Plus.dll、VB6MQTT.dll、VB6OpenSSL.dll）仍以 32 位形式存在，需要专用方案。

## What Changes

- **新增子包**: `vools.dll32` — 基于 Python 3.6 32 位解释器的独立包
- **嵌入式 32 位 Python**: 将 Python 3.6 32 位解释器嵌入到包内
- **32 位 DLL 集合**: 预置常用 32 位 DLL 文件（VB6Plus.dll、VB6MQTT.dll、VB6OpenSSL.dll 等）
- **统一装饰器接口**: 与 `vools.sys` 保持一致的 `@dll32` 装饰器风格
- **跨进程通信**: 使用管道/IPC 与 32 位 Python 进程通信

## Impact

- **新增目录**: `vools/dll32/`
- **依赖**: Python 3.6 32 位嵌入包
- **兼容**: 与 `vools.sys` 并存，各司其职

---

## ADDED Requirements

### Requirement: 32位 Python 嵌入

系统 SHALL 提供嵌入式 Python 3.6 32 位环境，具备以下能力：
- 独立的 Python 解释器实例
- 与主进程通过管道通信
- 自动启动和管理 32 位 Python 进程

#### Scenario: 加载嵌入式 Python
- **WHEN** 调用 `dll32` 模块时
- **THEN** 自动检测并使用嵌入的 Python 3.6 32 位解释器

### Requirement: @dll32 装饰器

系统 SHALL 提供风格与 `@dll` 一致的 `@dll32` 装饰器，具备以下能力：
- 接受 DLL 路径和函数名
- 自动类型映射（int/float/str/bytes/bool）
- 支持同步和异步模式
- 支持 fallback 回退机制

#### Scenario: 调用 32 位 DLL 函数
- **WHEN** 使用 `@dll32('path/to/dll::func')` 装饰函数
- **AND** 调用该函数时
- **THEN** 通过管道向 32 位 Python 进程发送调用请求
- **AND** 返回 32 位 DLL 的执行结果

### Requirement: 内置 32 位 DLL 集合

系统 SHALL 预置常用 32 位 DLL 文件：
- `VB6Plus.dll` — 加密/编码/PDF/图片处理（57个函数）
- `VB6MQTT.dll` — MQTT 客户端（4个函数）
- `VB6OpenSSL.dll` — HTTPS 请求（2个函数）

#### Scenario: 使用内置 DLL
- **WHEN** 调用 `dll32.vb6plus`, `dll32.mqtt`, `dll32.openssl` 时
- **THEN** 自动使用预置的 32 位 DLL，无需手动指定路径

### Requirement: 跨进程管道通信

系统 SHALL 通过管道实现 64→32 进程通信：
- JSON 序列化的调用请求
- JSON 序列化的调用响应
- 错误信息传递
- 超时控制

#### Scenario: 管道通信
- **WHEN** 64 位 Python 调用 32 位 DLL 函数时
- **THEN** 序列化调用参数为 JSON，通过管道发送到 32 位进程
- **AND** 32 位进程执行后返回结果
- **AND** 64 位进程反序列化并返回给调用者

---

## MODIFIED Requirements

无。

## REMOVED Requirements

无。
