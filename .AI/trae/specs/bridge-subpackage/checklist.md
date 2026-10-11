# vools Bridge - 验证检查清单

- [ ] Checkpoint 1: bridge 子包目录结构创建完成
- [ ] Checkpoint 2: `import vools.bridge` 成功
- [ ] Checkpoint 3: `LibraryLoader` 在 Windows 上正确加载 .dll
- [ ] Checkpoint 4: `LibraryLoader` 在 Linux 上正确加载 .so
- [ ] Checkpoint 5: 数据序列化层支持 int/float/string 列表
- [ ] Checkpoint 6: `@bridge_function` 装饰器工作正常
- [ ] Checkpoint 7: `@bridge_module` 装饰器工作正常
- [ ] Checkpoint 8: Nim crypto 桥接功能正确（md5/sha1/sha256/hmac）
- [ ] Checkpoint 9: Nim seq 桥接功能正确（map/filter/sum/sort/unique 等）
- [ ] Checkpoint 10: Nim datetime 桥接功能正确（is_leap_year/days_between 等）
- [ ] Checkpoint 11: Nim encoding 桥接功能正确（base64）
- [ ] Checkpoint 12: Nim curried 桥接功能正确（sum/mean/stddev 等）
- [ ] Checkpoint 13: 自动回退机制正常（删除库后使用 Python 实现）
- [ ] Checkpoint 14: `is_available("nim")` API 返回正确值
- [ ] Checkpoint 15: 现有 vools API（如 `vools.md5`）保持向后兼容
- [ ] Checkpoint 16: 所有测试通过（无功能丢失）
- [ ] Checkpoint 17: 代码结构清晰，无重复逻辑
