# vools.sql.core - SQL 方言核心框架 产品需求文档

## Overview
- **Summary**: 参照 vools.bridge 框架的设计模式，构建 vools.sql 子包的 core 核心模块，提供 SQL 方言抽象、类型映射、连接管理、查询构建和结果处理的统一 API 接口与配置系统，为后续多种 SQL 方言（MySQL、PostgreSQL、SQLite、Oracle、SQL Server 等）的实现奠定基础。
- **Purpose**: 解决多数据库方言差异带来的代码冗余问题，提供统一的 SQL 操作抽象层，使上层业务代码无需关心底层数据库差异，同时保持与 vools 现有架构风格一致。
- **Target Users**: vools 库的使用者，需要跨多种数据库方言编写 SQL 操作代码的开发者。

## Goals
- 建立 SQL 方言核心抽象层，定义统一的 API 接口规范
- 提供类型映射系统，实现 Python 类型与 SQL 类型的双向转换
- 建立方言注册与配置管理机制，支持动态加载和切换方言
- 提供 SQL 构建器抽象接口，支持链式调用构建 SQL 语句
- 定义数据库连接抽象接口，统一连接管理方式
- 定义查询执行与结果处理的抽象接口
- 提供与 bridge 框架一致的装饰器工具和便捷函数

## Non-Goals (Out of Scope)
- 不实现具体数据库驱动的连接和执行逻辑（由各语方言包实现）
- 不提供 ORM 功能（仅 SQL 构建与执行抽象）
- 不实现连接池管理（仅定义接口，具体实现由方言或上层提供）
- 不包含 SQL 语法解析功能（仅构建，不解析）
- 不提供数据迁移、schema 管理等高级功能

## Background & Context
- vools.bridge 框架已建立成熟的多语言方言架构模式，包括 core 抽象层 + 各语言方言实现 + manager 统一管理的三层结构
- vools 现有模块（如 serialize、reactive、task 等）均采用类似的 core/impl 分层设计
- 现有项目中已有 DataQuest NL2SQL 平台等相关 SQL 场景，但缺少通用 SQL 抽象层
- 参考 bridge 框架的设计元素：
  - `core/types.py` - 类型映射系统（CTypeMapper 模式）
  - `core/loader.py` - 加载器抽象（LibraryLoader 模式）
  - `core/decorators.py` - 装饰器工具（@bridge_function 模式）
  - `manager.py` - 统一配置管理器（LanguageConfig / BridgeManager 模式）
  - 延迟加载机制（`__getattr__` 动态导入）

## Functional Requirements
- **FR-1**: 类型映射系统 - 提供 Python 类型与 SQL 类型的双向映射，支持自定义类型注册，各语方言可扩展
- **FR-2**: 方言配置与注册 - 提供类似 BridgeManager 的方言管理器，支持注册方言、查询状态、配置连接参数
- **FR-3**: SQL 构建器抽象 - 定义基础 SQL AST 节点接口和构建器抽象，支持 SELECT/INSERT/UPDATE/DELETE 等 DML 语句构建
- **FR-4**: 连接抽象接口 - 定义数据库连接的抽象基类，统一 connect/close/execute 等接口
- **FR-5**: 结果集抽象 - 定义查询结果的统一表示，支持行迭代、列访问、类型转换等
- **FR-6**: 装饰器工具 - 提供类似 @bridge_function 的装饰器，简化 SQL 函数定义
- **FR-7**: 方言延迟加载 - 采用与 bridge 相同的延迟加载模式，避免导入时依赖具体数据库驱动

## Non-Functional Requirements
- **NFR-1**: 可扩展性 - 新增 SQL 方言只需实现 core 定义的抽象接口，无需修改 core 代码
- **NFR-2**: 兼容性 - 与 vools 现有代码风格、导入方式、命名规范保持一致
- **NFR-3**: 轻量级 - core 模块不依赖任何具体数据库驱动，仅依赖 Python 标准库和 vools 内部工具
- **NFR-4**: 类型安全 - 使用类型注解，支持 mypy 等静态类型检查工具
- **NFR-5**: 可测试性 - 核心抽象支持 Mock，便于上层代码单元测试

## Constraints
- **技术**: Python 3.6+，兼容 vools 现有技术栈，不引入重依赖
- **业务**: 需与 vools 整体架构风格统一，遵循现有编码规范
- **Dependencies**: 仅依赖 vools.core 和 Python 标准库，core 层不依赖任何数据库驱动包

## Assumptions
- 各语方言实现将遵循 core 定义的抽象接口
- 数据库驱动（如 pymysql、psycopg2 等）由使用方按需安装
- 方言注册机制与 bridge.manager 类似，支持配置持久化
- SQL 构建采用方法链式调用风格

## Acceptance Criteria

### AC-1: 类型映射系统可用
- **Given**: 用户需要在 Python 类型和 SQL 类型之间转换
- **When**: 使用 SqlTypeMapper 进行类型映射和转换
- **Then**: 可以正确映射基本类型（int, float, str, bool, datetime 等），支持自定义类型注册，各方言可扩展自己的类型映射
- **Verification**: `programmatic`
- **Notes**: 参考 bridge/core/types.py 的 CTypeMapper 设计模式

### AC-2: 方言注册与管理
- **Given**: 系统中需要管理多种 SQL 方言
- **When**: 使用 DialectManager 注册、查询、配置方言
- **Then**: 可以注册方言配置、查询方言是否可用、获取方言连接参数、保存/加载配置
- **Verification**: `programmatic`
- **Notes**: 参考 bridge/manager.py 的 BridgeManager / LanguageConfig 设计

### AC-3: SQL 构建器抽象接口
- **Given**: 需要构建 SQL 语句
- **When**: 使用 SQL 构建器抽象接口
- **Then**: 可以通过链式调用构建 SELECT/INSERT/UPDATE/DELETE 语句，方言实现者只需实现具体的 SQL 生成逻辑
- **Verification**: `programmatic`
- **Notes**: 定义抽象基类，具体实现由各方言包提供

### AC-4: 连接抽象接口
- **Given**: 需要统一管理数据库连接
- **When**: 使用 Connection 抽象基类
- **Then**: 各方言实现必须提供 connect/close/execute/commit/rollback 等标准接口
- **Verification**: `programmatic`
- **Notes**: 定义 ABC 抽象基类，参考 PEP 249 DB API 2.0 规范

### AC-5: 结果集抽象
- **Given**: 执行查询后需要处理结果
- **When**: 使用 ResultSet 抽象
- **Then**: 可以统一方式访问查询结果，支持索引访问、迭代、列名访问、类型自动转换
- **Verification**: `programmatic`

### AC-6: 装饰器工具可用
- **Given**: 需要定义 SQL 操作函数
- **When**: 使用 @sql_function 装饰器
- **Then**: 可以自动处理参数类型转换、结果类型转换、方言路由等
- **Verification**: `programmatic`
- **Notes**: 参考 bridge/core/decorators.py 的 bridge_function 设计

### AC-7: 包结构与导入规范
- **Given**: 用户导入 vools.sql 模块
- **When**: 通过 vools.sql 访问各方言
- **Then**: 采用延迟加载机制，导入时不会加载所有方言，访问具体方言时才动态加载，与 bridge 模块风格一致
- **Verification**: `human-judgment`
- **Notes**: 代码结构和导入方式需与 vools.bridge 保持一致风格

### AC-8: 代码风格一致性
- **Given**: 开发者阅读 sql/core 代码
- **When**: 对比 bridge/core 代码
- **Then**: 命名规范、代码组织、文档风格、类设计模式与 bridge 框架保持高度一致
- **Verification**: `human-judgment`

## Open Questions
- [ ] SQL 构建器是采用 AST 节点模式还是直接字符串拼接模式？
- [ ] 是否需要支持事务管理抽象？
- [ ] 连接池是放在 core 层还是方言层实现？
- [ ] 是否需要支持异步数据库连接（asyncio）？
- [ ] 方言配置是否需要与 vools.config 全局配置系统集成？
