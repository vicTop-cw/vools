# vools 集成计划 - 验证检查清单

## 模块实现
- [ ] Checkpoint 1: hash_wrapper.bas 存在且编译成功
- [ ] Checkpoint 2: json_wrapper.bas 存在且编译成功
- [ ] Checkpoint 3: vools/crypto/hash.py 存在且可导入
- [ ] Checkpoint 4: vools/data/json.py 存在且可导入
- [ ] Checkpoint 5: vools/data/vvalidate.py 存在且可导入

## 功能验证
- [ ] Checkpoint 6: md5() 返回正确哈希值（与 hashlib 对比）
- [ ] Checkpoint 7: sha256() 返回正确哈希值（与 hashlib 对比）
- [ ] Checkpoint 8: JSON parse() 正确解析对象和数组
- [ ] Checkpoint 9: JSON stringify() 正确序列化 Python 对象
- [ ] Checkpoint 10: 所有验证函数（is_email, is_mobile, is_idcard, is_plate）返回正确结果

## 架构集成
- [ ] Checkpoint 11: hash_wrapper 和 json_wrapper 已注册到 modules/__init__.py
- [ ] Checkpoint 12: crypto/__init__.py 导出 hash 模块
- [ ] Checkpoint 13: data/__init__.py 导出 json 和 vvalidate 模块
- [ ] Checkpoint 14: @fbc 装饰器可正确调用 hash_wrapper 和 json_wrapper

## 测试与文档
- [ ] Checkpoint 15: 所有单元测试通过
- [ ] Checkpoint 16: 哈希性能达到 hashlib 的 80% 以上
- [ ] Checkpoint 17: 文档更新完成，包含全局唯一性编号
- [ ] Checkpoint 18: 文档内部链接正确