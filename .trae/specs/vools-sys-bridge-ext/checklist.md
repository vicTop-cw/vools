# vools.sys 与 LangBridge 扩展 - Verification Checklist

## @exe 装饰器
- [ ] 能通过 `from vools.sys import exe` 正常导入
- [ ] 基本调用正常：返回 (returncode, stdout, stderr) 元组
- [ ] 短选项映射正确：`_f='val'` → `-f val`
- [ ] 长选项映射正确：`__path='/tmp'` → `--path /tmp`
- [ ] 无值选项正确：`_m=None` → `-m`
- [ ] 位置参数按顺序追加到命令末尾
- [ ] 异步模式 `async_mode=True` 可以 await 调用
- [ ] fallback 参数在 exe 不存在时生效
- [ ] 无参函数签名正常工作
- [ ] 函数体为 pass 时装饰器自动执行命令

## @dll 装饰器
- [ ] 能通过 `from vools.sys import dll` 正常导入
- [ ] 基本调用正常：能正确调用 DLL 中的导出函数
- [ ] int 类型自动映射为 c_int
- [ ] float 类型自动映射为 c_double
- [ ] str 类型自动映射为 c_char_p（自动编码）
- [ ] bytes 类型自动映射为 c_char_p
- [ ] bool 类型自动映射为 c_bool
- [ ] 返回值类型根据注解自动映射
- [ ] 异步模式 `async_mode=True` 可以 await 调用
- [ ] fallback 参数在 DLL 加载失败时生效
- [ ] 无参函数签名正常工作
- [ ] 函数体为 pass 时装饰器自动调用 DLL

## only_code 模式
- [ ] `only_code=True, output_file="..."` 启用代码生成模式
- [ ] 生成的代码正确写入目标文件
- [ ] `write_mode='overwrite'` 覆盖整个文件
- [ ] `write_mode='append'` 追加到文件末尾
- [ ] `write_mode='insert:NN'` 插入到第 NN 行之后
- [ ] `write_mode='replace:MM-NN'` 替换第 MM 到 NN 行
- [ ] `prefix` 参数正确添加代码前缀
- [ ] `suffix` 参数正确添加代码后缀
- [ ] 支持 deps 依赖函数（代码合并）
- [ ] 支持 module_code 模块级代码
- [ ] 不触发编译器调用
- [ ] 不传 only_code 时行为完全不变（向后兼容）

## project 模式
- [ ] `project_dir="...", entry="main"` 启用项目编译模式
- [ ] FreeBASIC 项目能正确编译生成 exe
- [ ] C 项目能正确编译生成 dll/exe
- [ ] 编译产物路径可获取
- [ ] 基于文件内容哈希的缓存机制生效
- [ ] 支持异步模式
- [ ] 不传 project_dir 时行为完全不变（向后兼容）

## 整体质量
- [ ] 所有新增模块无导入错误
- [ ] 所有现有测试仍然通过
- [ ] 错误信息清晰易懂
- [ ] 代码风格与现有代码一致
- [ ] 不引入新的第三方依赖
