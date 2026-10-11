# LibXL DLL 替换与 SqlCel 集成 - 验证清单

## LibXL DLL 替换
- [ ] 两个版本 libxl.dll 的导出函数列表已对比
- [ ] VFB 版本 DLL 的版本信息已确认
- [ ] VFB 版本 DLL 的 xls 格式支持已验证
- [ ] VFB 版本 DLL 的 xlsx 格式支持已验证
- [ ] 现有 xl 测试套件在 VFB 版本 DLL 下全部通过
- [ ] 如兼容，DLL 已替换到 vools/xl/_dlls/
- [ ] 替换后所有 xl 功能正常（读写、格式、批量操作）
- [ ] xl README 文档已更新 DLL 版本说明

## SqlCel 子包架构
- [ ] vools/sqlcel/ 子包目录已创建
- [ ] __init__.py 实现延迟导入机制
- [ ] sqlcel_available() 检测函数正常工作
- [ ] 无 SqlCel 环境下 import vools.sqlcel 不报错
- [ ] 无 SqlCel 环境下不影响 vools 其他模块
- [ ] 子包模块结构清晰（core, functions, dataset）
- [ ] 支持通过环境变量指定 SqlCel 安装路径

## .NET 桥接层
- [ ] Bridge.dll 成功加载
- [ ] Bridge.AddInFuncs 类型成功获取
- [ ] 公开方法枚举正常
- [ ] 方法调用机制实现
- [ ] Python <-> .NET 类型转换正确
- [ ] 异常处理和错误转换完善
- [ ] AlittleTest 等简单方法调用验证通过

## D_ 系列函数封装
- [ ] D_SUMIF 函数封装完成
- [ ] D_SUMIFS 函数封装完成
- [ ] D_COUNTIF 函数封装完成
- [ ] D_COUNTIFS 函数封装完成
- [ ] D_VLOOKUP 函数封装完成
- [ ] D_FIND 函数封装完成
- [ ] D_AVERAGEIF 函数封装完成
- [ ] D_MAX / D_MIN 函数封装完成
- [ ] D_SUMPRODUCT 函数封装完成
- [ ] 至少 10 个核心 D_ 函数可用
- [ ] 每个函数都有文档字符串
- [ ] 每个函数都有单元测试
- [ ] 支持 list of dict 输入格式
- [ ] 支持 vools.data.Table 输入格式
- [ ] 计算结果正确性已验证

## 数据集操作 API
- [ ] SqlCelDataset 类已实现
- [ ] 筛选功能（where/filter）正常
- [ ] 排序功能（order_by/sort）正常
- [ ] 分组聚合功能（group_by/agg）正常
- [ ] 与 vools.data.Table 双向转换正常
- [ ] 链式调用 API 可用
- [ ] 从 Excel 读取数据集功能正常
- [ ] 写回 Excel 功能正常

## 与 xl/data 模块集成
- [ ] vools.xl 读取的数据可直接传入 SqlCel
- [ ] SqlCel 结果可用 vools.xl 写回 Excel
- [ ] Table 与 SqlCelDataset 互转无损
- [ ] 集成方式松耦合，SqlCel 可选
- [ ] xl README 中有 SqlCel 集成说明

## 文档与测试
- [ ] vools/sqlcel/README.md 已撰写
- [ ] README 包含功能介绍
- [ ] README 包含安装要求
- [ ] README 包含快速开始示例
- [ ] README 包含 API 参考
- [ ] README 包含注意事项和限制
- [ ] 测试文件归档在 tests/sqlcel/
- [ ] 无 SqlCel 环境测试通过
- [ ] 有 SqlCel 环境功能测试通过
- [ ] Python 3.6 语法兼容性已验证
- [ ] Python 3.13 兼容性已验证
