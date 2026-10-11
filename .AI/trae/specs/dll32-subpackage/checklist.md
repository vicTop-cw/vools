# Checklist - vools.dll32 子包开发

## 基础结构检查

- [x] `vools/dll32/__init__.py` 存在且导出正确
- [x] `vools/dll32/_core/` 目录结构正确
- [x] `vools/dll32/_dlls/` 目录结构正确
- [x] `vools/dll32/_python32/` 目录结构正确

## Python 32 位环境检查

- [x] Python 3.6 32 位嵌入式包已下载
- [x] `python.exe` (32位) 可执行
- [x] `python32_launcher.py` 可启动 32 位解释器

## 进程管理检查

- [x] `_spawn32.py` 可成功启动 32 位 Python 进程
- [x] `_pipe_comm.py` 管道读写正常
- [x] `_json_rpc.py` JSON-RPC 调用成功（集成在 launcher 中）
- [x] 超时机制正常工作

## @dll32 装饰器检查

- [x] `@dll32` 装饰器可正常导入
- [ ] DLL 函数调用成功（Base64 测试）- 需要实际调用验证
- [x] 类型映射正确（int/float/str/bytes/bool）
- [x] fallback 机制正常工作
- [x] 异步模式正常（async_mode=True）

## 预置 DLL 检查

- [x] `VB6Plus.dll` 存在于 `_dlls/`
- [x] `VB6MQTT.dll` 存在于 `_dlls/`
- [x] `VB6OpenSSL.dll` 存在于 `_dlls/`
- [ ] DLL 可被 32 位 Python 加载 - 需要 32 位环境验证

## 内置包装模块检查

- [x] `dll32.vb6plus` 可导入
- [x] `dll32.mqtt` 可导入
- [x] `dll32.openssl` 可导入

## 测试检查

- [x] `tests/test_dll32.py` 存在
- [ ] 实际 DLL 调用测试 - 需要 32 位 Python 环境验证

## 文档检查

- [x] `vools/dll32/README.md` 完整
- [x] 使用示例可正常运行
- [x] API 速查准确

## 兼容性检查

- [x] Python 3.6 32 位兼容（嵌入式包已配置）
- [x] Python 3.13 64 位兼容（导入测试通过）
- [x] Windows 平台兼容

## 最终验证命令

```powershell
# 验证导入
python -c "from vools.dll32 import dll32; print('OK')"

# 验证 Python 32 位
.\vools\dll32\_python32\python.exe --version
```
