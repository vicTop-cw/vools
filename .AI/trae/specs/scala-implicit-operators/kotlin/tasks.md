# Kotlin 双元操作符实现 Tasks

- [x] Task 1: 创建独立 Kotlin 项目结构
  - [x] SubTask 1.1: 在 `docs/scala-implicit-operators/kotlin/` 创建 Gradle Kotlin DSL 项目
  - [x] SubTask 1.2: 配置 Kotlin/JVM 插件和 JUnit 5 测试依赖
  - [x] SubTask 1.3: 验证 `./gradlew test` 可空跑通过

- [x] Task 2: 实现 函|函 操作符
  - [x] SubTask 2.1: 实现无参函数组合操作符：`o`, `co`, `oo`, `coo`
  - [x] SubTask 2.2: 实现无参函数解包操作符：`so`, `cos`
  - [x] SubTask 2.3: 实现单参函数组合操作符：`then`, `cthen`, `then2`, `cthen2`
  - [x] SubTask 2.4: 实现单参函数解包操作符：`sthen`, `csthen`
  - [x] SubTask 2.5: 实现双参函数组合操作符：`then3`, `cthen3`, `then23`, `cthen23`
  - [x] SubTask 2.6: 实现双参函数解包操作符：`sthen3`, `csthen3`

- [x] Task 3: 实现 数|函 操作符
  - [x] SubTask 3.1: 实现管道操作符：`pipe`, `cpipe`
  - [x] SubTask 3.2: 实现映射操作符：`mapBy`, `cmapBy`
  - [x] SubTask 3.3: 实现过滤操作符：`filterBy`, `cfilterBy`
  - [x] SubTask 3.4: 实现展平映射操作符：`flatMapBy`, `cflatMapBy`
  - [x] SubTask 3.5: 实现归约操作符：`reduceBy`, `creduceBy`
  - [x] SubTask 3.6: 实现折叠操作符：`foldBy`, `cfoldBy`

- [x] Task 4: 编写单元测试
  - [x] SubTask 4.1: 为每个 函|函 操作符编写至少一个正向测试
  - [x] SubTask 4.2: 为每个 数|函 操作符编写至少一个正向测试
  - [x] SubTask 4.3: 编写边界情况测试（空集合、参数不足/过多、柯里化 fold 等）

- [x] Task 5: 编写文档与示例
  - [x] SubTask 5.1: 为核心操作符文件添加 KDoc 注释
  - [x] SubTask 5.2: 在 README 中提供完整操作符列表与使用示例
  - [x] SubTask 5.3: 记录 Kotlin 与 Scala 操作符命名映射表

# Task Dependencies

- Task 2 depends on Task 1
- Task 3 depends on Task 1
- Task 4 depends on Task 2 and Task 3
- Task 5 depends on Task 4
