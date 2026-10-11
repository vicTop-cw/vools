# Kotlin 双元操作符实现 Spec

## Why

参考 `docs/scala-implicit-operators/需求文档.md` 定义的 30 个双元操作符，在 Kotlin 中利用**扩展函数（extension functions）**与**中缀函数（infix functions）**实现等价的函数组合与数据管道能力。Kotlin 的类型系统、高阶函数与 `Iterable` 抽象使其成为移植该设计的最佳目标语言之一。

## What Changes

- 在 `docs/scala-implicit-operators/kotlin/` 目录创建独立 Kotlin 项目
- 实现 30 个中缀双元操作符（15 对正向/反向）
- 提供与 Scala 文档语义一致的类型签名与行为
- 编写完整的使用案例、边界说明注释
- 编写并运行测试用例，确保所有操作符行为正确

## Impact

- 新增目录：`docs/scala-implicit-operators/kotlin/src/main/kotlin/` 与 `src/test/kotlin/`
- 新增文件：核心操作符实现、测试文件、构建脚本（Gradle Kotlin DSL 或 Maven）
- 不影响现有 vools 项目代码（独立项目，后续可选并入 `vools/bridge/kotlin`）

## ADDED Requirements

### Requirement: 项目结构与构建

The system SHALL provide a self-contained Kotlin project under `docs/scala-implicit-operators/kotlin/`.

#### Scenario: Build and test
- **WHEN** a developer runs the test command in the project directory
- **THEN** the project compiles with Kotlin/JVM and all tests pass

### Requirement: 函|函 操作符

The system SHALL implement 18 function-to-function binary operators using Kotlin infix extension functions on function types.

#### Scenario: Compose zero-arg to single-arg
- **GIVEN** `f: () -> A` and `g: (A) -> B`
- **WHEN** using `f o g` or `g o f` (Kotlin 不支持 `>` 作为操作符，需等价命名)
- **THEN** it returns `() -> B` that applies `g` to `f()`

**注**：Kotlin 中可自定义的操作符字符受限，建议采用以下命名映射：

| Scala | Kotlin |
|-------|--------|
| `o>` | `o` |
| `<o` | `co` (compose from) |
| `o>>` | `oo` |
| `<<o` | `coo` |
| `*o>` | `so` (spread compose) |
| `<o*` | `cos` |
| `~>` | `then` |
| `<~` | `cthen` |
| `~>>` | `then2` |
| `<<~` | `cthen2` |
| `*~>` | `sthen` |
| `<~*` | `csthen` |
| `~~>` | `then3` |
| `<~~` | `cthen3` |
| `*~~>` | `sthen3` |
| `<~~*` | `csthen3` |
| `~~>>` | `then23` |
| `<<~~` | `cthen23` |

也可保留 `infix fun <A, B> (() -> A).o(other: (A) -> B)` 形式，但需避免与 Kotlin 保留操作符冲突。

#### Scenario: Compose zero-arg to two-arg
- **GIVEN** `f: () -> A` and `g: (A, B) -> C`
- **WHEN** using `f oo g` or `g coo f`
- **THEN** it returns `(B) -> C` that applies `g(f(), b)`

#### Scenario: Unpack zero-arg result
- **GIVEN** `f: () -> Iterable<A>` and `g` requiring at least one `A`
- **WHEN** using `f so g` or `g cos f`
- **THEN** it unpacks `f()` and partially applies `g`; remaining params form a new function

#### Scenario: Compose single-arg to single-arg
- **GIVEN** `f: (D) -> A` and `g: (A) -> B`
- **WHEN** using `f then g` or `g cthen f`
- **THEN** it returns `(D) -> B` equivalent to `g ∘ f`

#### Scenario: Compose single-arg to two-arg
- **GIVEN** `f: (D) -> A` and `g: (A, B) -> C`
- **WHEN** using `f then2 g` or `g cthen2 f`
- **THEN** it returns `(D, B) -> C`

#### Scenario: Unpack single-arg result
- **GIVEN** `f: (D) -> Iterable<A>` and `g` requiring at least one `A`
- **WHEN** using `f sthen g` or `g csthen f`
- **THEN** it unpacks `f(d)` and partially applies `g`; remaining params form a new function

#### Scenario: Compose two-arg to single-arg
- **GIVEN** `f: (D, F) -> A` and `g: (A) -> B`
- **WHEN** using `f then3 g` or `g cthen3 f`
- **THEN** it returns `(D, F) -> B`

#### Scenario: Unpack two-arg result
- **GIVEN** `f: (D, F) -> Iterable<A>` and `g` requiring at least one `A`
- **WHEN** using `f sthen3 g` or `g csthen3 f`
- **THEN** it unpacks `f(d, f)` and partially applies `g`; remaining params form a new function

#### Scenario: Compose two-arg to two-arg
- **GIVEN** `f: (D, F) -> A` and `g: (A, B) -> C`
- **WHEN** using `f then23 g` or `g cthen23 f`
- **THEN** it returns `(D, F, B) -> C`

### Requirement: 数|函 操作符

The system SHALL implement 12 value-to-function binary operators.

#### Scenario: Pipe value to function
- **GIVEN** a value `a: A` and `f: (A) -> B`
- **WHEN** using `a pipe f` or `f cpipe a`
- **THEN** it returns `f(a)`

**命名映射**：

| Scala | Kotlin |
|-------|--------|
| `\|>` | `pipe` |
| `<\|` | `cpipe` |
| `\|>>` | `mapBy` |
| `<<\|` | `cmapBy` |
| `\|?>` | `filterBy` |
| `<?\|` | `cfilterBy` |
| `\|*>` | `flatMapBy` |
| `<*\|` | `cflatMapBy` |
| `\|&>` | `reduceBy` |
| `<&\|` | `creduceBy` |
| `\|@>` | `foldBy` |
| `<@\|` | `cfoldBy` |

#### Scenario: Map over iterable
- **GIVEN** an `Iterable<A>` and `f: (A) -> B`
- **WHEN** using `xs mapBy f` or `f cmapBy xs`
- **THEN** it returns an `Iterable<B>` equivalent to `xs.map(f)`

#### Scenario: Filter iterable
- **GIVEN** an `Iterable<A>` and predicate `f: (A) -> Boolean`
- **WHEN** using `xs filterBy f` or `f cfilterBy xs`
- **THEN** it returns a filtered `Iterable<A>`

#### Scenario: Flat-map over iterable
- **GIVEN** an `Iterable<Iterable<A>>` and `f: (A) -> B`
- **WHEN** using `xs flatMapBy f` or `f cflatMapBy xs`
- **THEN** it flattens then maps, returning `Iterable<B>`

#### Scenario: Reduce iterable
- **GIVEN** an `Iterable<A>` and `op: (A, A) -> A`
- **WHEN** using `xs reduceBy op` or `op creduceBy xs`
- **THEN** it returns the reduced value, equivalent to `xs.reduce(op)`

#### Scenario: Fold iterable
- **GIVEN** an `Iterable<A>` and curried `folder: (G) -> ((G, A) -> G)`
- **WHEN** using `xs foldBy folder` or `folder cfoldBy xs`
- **THEN** it returns a function `(G) -> G` that folds the iterable

### Requirement: 代码质量

The system SHALL provide well-documented code with usage boundaries and examples.

#### Scenario: Readability
- **WHEN** a developer reads the source code
- **THEN** each operator has KDoc comments explaining its signature, semantics, and edge cases

#### Scenario: Test coverage
- **WHEN** running tests
- **THEN** every operator has at least one positive test case, and edge cases are documented

## MODIFIED Requirements

None.

## REMOVED Requirements

None.
