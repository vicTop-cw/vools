# Tasks

- [x] Task 1: 创建 Scala 2 独立项目结构
  - [x] SubTask 1.1: 在 `docs/scala-implicit-operators/` 下创建 `src/main/scala/` 和 `src/test/scala/` 目录
  - [x] SubTask 1.2: 创建 `build.sbt`，指定 Scala 2.13.x、无额外依赖
  - [x] SubTask 1.3: 创建 `project/build.properties`，指定 sbt 版本

- [x] Task 2: 实现函|函操作符
  - [x] SubTask 2.1: 实现无参函数组合：`#>` / `<#` / `#>>` / `<<#`
  - [x] SubTask 2.2: 实现无参函数解包组合：`*#>` / `<#*`
  - [x] SubTask 2.3: 实现单参函数组合：`~>` / `<~` / `~>>` / `<<~`
  - [x] SubTask 2.4: 实现单参函数解包组合：`*~>` / `<~*`
  - [x] SubTask 2.5: 实现双参函数组合：`~~>` / `<~~` / `~~>>` / `<<~~`
  - [x] SubTask 2.6: 实现双参函数解包组合：`*~~>` / `<~~*`

- [x] Task 3: 实现数|函操作符
  - [x] SubTask 3.1: 实现管道符：`|>` / `<|`
  - [x] SubTask 3.2: 实现映射：`|>>` / `<<|`
  - [x] SubTask 3.3: 实现过滤：`|?>` / `<?|`
  - [x] SubTask 3.4: 实现展平映射：`|*>` / `<*|`
  - [x] SubTask 3.5: 实现归约：`|&>` / `<&|`
  - [x] SubTask 3.6: 实现折叠：`|@>` / `<@|`

- [x] Task 4: 编写测试用例
  - [x] SubTask 4.1: 为所有函|函操作符编写正向测试
  - [x] SubTask 4.2: 为所有数|函操作符编写正向测试
  - [x] SubTask 4.3: 为解包操作符编写边界测试（参数过多/不足）
  - [x] SubTask 4.4: 为反向操作符编写测试

- [x] Task 5: 验证与文档
  - [x] SubTask 5.1: 运行 `sbt test` 并确保全部通过
  - [x] SubTask 5.2: 在源代码中添加每个操作符的类型签名、语义、边界说明注释
  - [x] SubTask 5.3: 在 `docs/scala-implicit-operators/` 下添加使用说明 README

# Task Dependencies

- Task 2 depends on Task 1
- Task 3 depends on Task 1
- Task 4 depends on Task 2 and Task 3
- Task 5 depends on Task 4

# Notes

- 原需求文档中的部分操作符名称（如 `o>`、`<o`、`o>>`、`<<o`、`*o>`、`<o*`）因 Scala 2 方法命名规则限制无法直接定义，已在实现中重命名为 `#>`、`<#`、`#>>`、`<<#`、`*#>`、`<#*`。
- 解包操作符通过隐式标记（UnpackMarkers）解决类型擦除导致的重载冲突。
