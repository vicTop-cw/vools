# Tasks - vools.dll32 子包开发

## 任务列表

- [ ] Task 1: 创建 dll32 子包基础结构
  - [ ] 创建 `vools/dll32/__init__.py`
  - [ ] 创建 `vools/dll32/_core/` 核心模块目录
  - [ ] 创建 `vools/dll32/_dlls/` 预置 DLL 目录
  - [ ] 创建 `vools/dll32/_python32/` Python 3.6 32位目录占位

- [ ] Task 2: 下载并配置 Python 3.6 32 位嵌入包
  - [ ] 下载 Python 3.6 32 位 Windows 嵌入式包
  - [ ] 解压到 `vools/dll32/_python32/`
  - [ ] 创建启动脚本 `python32_launcher.py`

- [ ] Task 3: 实现 32 位 Python 进程管理
  - [ ] 创建 `_spawn32.py` — 启动和管理 32 位 Python 进程
  - [ ] 实现 `_pipe_comm.py` — 管道通信模块
  - [ ] 实现 `_json_rpc.py` — JSON-RPC 风格调用协议

- [ ] Task 4: 实现 @dll32 装饰器
  - [ ] 创建 `dll.py` — `@dll32` 装饰器实现
  - [ ] 实现参数类型映射（int/float/str/bytes/bool）
  - [ ] 实现返回值处理
  - [ ] 实现 fallback 机制

- [ ] Task 5: 复制预置 DLL 文件
  - [ ] 复制 `VB6Plus.dll` 到 `_dlls/`
  - [ ] 复制 `VB6MQTT.dll` 到 `_dlls/`
  - [ ] 复制 `VB6OpenSSL.dll` 到 `_dlls/`
  - [ ] 更新 `__init__.py` 导出内置 DLL 快捷访问

- [ ] Task 6: 创建内置 DLL 包装模块
  - [ ] 创建 `vb6plus.py` — VB6Plus.dll 包装
  - [ ] 创建 `mqtt.py` — VB6MQTT.dll 包装
  - [ ] 创建 `openssl.py` — VB6OpenSSL.dll 包装

- [ ] Task 7: 创建示例和测试
  - [ ] 创建 `examples/basic_usage.py` — 基本用法示例
  - [ ] 创建 `tests/test_dll32.py` — 单元测试
  - [ ] 创建 `tests/test_vb6plus.py` — VB6Plus 测试
  - [ ] 创建 `tests/test_mqtt.py` — MQTT 测试

- [ ] Task 8: 创建 README 文档
  - [ ] 创建 `vools/dll32/README.md`
  - [ ] 编写安装说明
  - [ ] 编写使用示例
  - [ ] 编写 API 速查

---

## 任务依赖关系

```
Task 1 (基础结构)
    ↓
Task 2 (Python 32位) ← 独立，可与 Task 1 并行
    ↓
Task 3 (进程管理) ← 依赖 Task 2
    ↓
Task 4 (@dll32装饰器) ← 依赖 Task 3
    ↓
Task 5 (复制DLL) ← 独立，可与 Task 4 并行
    ↓
Task 6 (内置包装) ← 依赖 Task 4、5
    ↓
Task 7 (测试示例) ← 依赖 Task 4、6
    ↓
Task 8 (文档) ← 依赖所有
```
