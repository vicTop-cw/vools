# Nim 双元操作符实现 Tasks

- [x] Task 1: 创建独立 Nim 项目结构
  - [x] SubTask 1.1: 在 `docs/scala-implicit-operators/nim/` 创建 nimble 项目
  - [x] SubTask 1.2: 配置 `*.nimble` 文件，包含 `srcDir` 和 `tests` 任务
  - [x] SubTask 1.3: 验证 `nimble test` 可空跑通过

- [x] Task 2: 实现 函|函 操作符
  - [x] SubTask 2.1: 实现无参函数组合操作符：`o>`, `<o`, `o>>`, `<<o`
  - [x] SubTask 2.2: 实现无参函数解包操作符：`*o>`, `<o*`
  - [x] SubTask 2.3: 实现单参函数组合操作符：`~>`, `<~`, `~>>`, `<<~`
  - [x] SubTask 2.4: 实现单参函数解包操作符：`*~>`, `<~*`
  - [x] SubTask 2.5: 实现双参函数组合操作符：`~~>`, `<~~`, `~~>>`, `<<~~`
  - [x] SubTask 2.6: 实现双参函数解包操作符：`*~~>`, `<~~*`

- [x] Task 3: 实现 数|函 操作符
  - [x] SubTask 3.1: 实现管道操作符：`|>`, `<|`
  - [x] SubTask 3.2: 实现映射操作符：`|>>`, `<<|`
  - [x] SubTask 3.3: 实现过滤操作符：`|?>`, `<?|`
  - [x] SubTask 3.4: 实现展平映射操作符：`|*>`, `<*|`
  - [x] SubTask 3.5: 实现归约操作符：`|&>`, `<&|`
  - [x] SubTask 3.6: 实现折叠操作符：`|@>`, `<@|`

- [x] Task 4: 编写单元测试
  - [x] SubTask 4.1: 为每个 函|函 操作符编写至少一个正向测试
  - [x] SubTask 4.2: 为每个 数|函 操作符编写至少一个正向测试
  - [x] SubTask 4.3: 编写边界情况测试（空序列、解包参数不足/过多、reduce 空序列异常）

- [x] Task 5: 编写文档与示例
  - [x] SubTask 5.1: 为核心操作符文件添加文档注释
  - [x] SubTask 5.2: 在 README 中提供完整操作符列表与使用示例
  - [x] SubTask 5.3: 记录操作符优先级注意事项

# Task Dependencies

- Task 2 depends on Task 1
- Task 3 depends on Task 1
- Task 4 depends on Task 2 and Task 3
- Task 5 depends on Task 4
