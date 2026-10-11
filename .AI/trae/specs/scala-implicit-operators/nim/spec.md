# Nim 双元操作符实现 Spec

## Why

参考 `docs/scala-implicit-operators/需求文档.md` 定义的 30 个双元操作符，在 Nim 中利用其**强大的操作符重载能力**与**宏系统**实现等价的函数组合与数据管道能力。Nim 允许几乎任意字符组合作为自定义操作符，并且 vools 已有 `bridge/nim` 模块，便于后续集成。

## What Changes

- 在 `docs/scala-implicit-operators/nim/` 目录创建独立 Nim 项目
- 实现 30 个中缀双元操作符（15 对正向/反向），尽量保持与 Scala 文档相同的操作符形态
- 提供与 Scala 文档语义一致的类型签名与行为
- 编写完整的使用案例、边界说明注释
- 编写并运行测试用例，确保所有操作符行为正确

## Impact

- 新增目录：`docs/scala-implicit-operators/nim/src/` 与 `tests/`
- 新增文件：核心操作符实现、测试文件、构建脚本（`*.nimble`）
- 不影响现有 vools 项目代码（独立项目，后续可选并入 `vools/bridge/nim`）

## ADDED Requirements

### Requirement: 项目结构与构建

The system SHALL provide a self-contained Nim project under `docs/scala-implicit-operators/nim/`.

#### Scenario: Build and test
- **WHEN** a developer runs `nimble test` in the project directory
- **THEN** the project compiles with Nim and all tests pass

### Requirement: 函|函 操作符

The system SHALL implement 18 function-to-function binary operators using Nim operator overloading.

Nim 支持自定义操作符，因此可直接使用或尽量接近 Scala 文档中的符号。建议命名映射：

| Scala | Nim |
|-------|-----|
| `o>` | `o>` |
| `<o` | `<o` |
| `o>>` | `o>>` |
| `<<o` | `<<o` |
| `*o>` | `*o>` |
| `<o*` | `<o*` |
| `~>` | `~>` |
| `<~` | `<~` |
| `~>>` | `~>>` |
| `<<~` | `<<~` |
| `*~>` | `*~>` |
| `<~*` | `<~*` |
| `~~>` | `~~>` |
| `<~~` | `<~~` |
| `*~~>` | `*~~>` |
| `<~~*` | `<~~*` |
| `~~>>` | `~~>>` |
| `<<~~` | `<<~~` |

**注意**：Nim 操作符优先级由首字符决定。以 `<` 开头的操作符（如 `<o`）为比较类操作符，以 `*` 开头的操作符优先级较高。需通过 `proc` 定义并可能借助 `{.inline.}` 或模板实现，确保组合行为符合预期。

#### Scenario: Compose zero-arg to single-arg
- **GIVEN** `f: () -> A` and `g: A -> B`
- **WHEN** using `f o> g` or `g <o f`
- **THEN** it returns `() -> B` that applies `g` to `f()`

#### Scenario: Compose zero-arg to two-arg
- **GIVEN** `f: () -> A` and `g: (A, B) -> C`
- **WHEN** using `f o>> g` or `g <<o f`
- **THEN** it returns `(B) -> C` that applies `g(f(), b)`

#### Scenario: Unpack zero-arg result
- **GIVEN** `f: () -> seq[A]` or `() -> openArray[A]` and `g` requiring at least one `A`
- **WHEN** using `f *o> g` or `g <o* f`
- **THEN** it unpacks `f()` and partially applies `g`; remaining params form a new function

#### Scenario: Compose single-arg to single-arg
- **GIVEN** `f: D -> A` and `g: A -> B`
- **WHEN** using `f ~> g` or `g <~ f`
- **THEN** it returns `D -> B` equivalent to `g ∘ f`

#### Scenario: Compose single-arg to two-arg
- **GIVEN** `f: D -> A` and `g: (A, B) -> C`
- **WHEN** using `f ~>> g` or `g <<~ f`
- **THEN** it returns `(D, B) -> C`

#### Scenario: Unpack single-arg result
- **GIVEN** `f: D -> seq[A]` and `g` requiring at least one `A`
- **WHEN** using `f *~> g` or `g <~* f`
- **THEN** it unpacks `f(d)` and partially applies `g`; remaining params form a new function

#### Scenario: Compose two-arg to single-arg
- **GIVEN** `f: (D, F) -> A` and `g: A -> B`
- **WHEN** using `f ~~> g` or `g <~~ f`
- **THEN** it returns `(D, F) -> B`

#### Scenario: Unpack two-arg result
- **GIVEN** `f: (D, F) -> seq[A]` and `g` requiring at least one `A`
- **WHEN** using `f *~~> g` or `g <~~* f`
- **THEN** it unpacks `f(d, f)` and partially applies `g`; remaining params form a new function

#### Scenario: Compose two-arg to two-arg
- **GIVEN** `f: (D, F) -> A` and `g: (A, B) -> C`
- **WHEN** using `f ~~>> g` or `g <<~~ f`
- **THEN** it returns `(D, F, B) -> C`

### Requirement: 数|函 操作符

The system SHALL implement 12 value-to-function binary operators.

Nim 可直接使用以下操作符：

| Scala | Nim |
|-------|-----|
| `\|>` | `\|>` |
| `<\|` | `<\|` |
| `\|>>` | `\|>>` |
| `<<\|` | `<<\|` |
| `\|?>` | `\|?>` |
| `<?\|` | `<?\|` |
| `\|*>` | `\|*>` |
| `<*\|` | `<*\|` |
| `\|&>` | `\|&>` |
| `<&\|` | `<&\|` |
| `\|@>` | `\|@>` |
| `<@\|` | `<@\|` |

#### Scenario: Pipe value to function
- **GIVEN** a value `a: A` and `f: A -> B`
- **WHEN** using `a |> f` or `f <| a`
- **THEN** it returns `f(a)`

#### Scenario: Map over iterable
- **GIVEN** a `seq[A]` or `openArray[A]` and `f: A -> B`
- **WHEN** using `xs |>> f` or `f <<| xs`
- **THEN** it returns a sequence of `B` equivalent to `xs.map(f)`

#### Scenario: Filter iterable
- **GIVEN** a `seq[A]` and predicate `f: A -> bool`
- **WHEN** using `xs |?> f` or `f <?| xs`
- **THEN** it returns a filtered sequence

#### Scenario: Flat-map over iterable
- **GIVEN** a `seq[seq[A]]` and `f: A -> B`
- **WHEN** using `xs |*> f` or `f <*| xs`
- **THEN** it flattens then maps, returning `seq[B]`

#### Scenario: Reduce iterable
- **GIVEN** a `seq[A]` and `op: (A, A) -> A`
- **WHEN** using `xs |&> op` or `op <&| xs`
- **THEN** it returns the reduced value, equivalent to `xs.foldl(op)` without init

#### Scenario: Fold iterable
- **GIVEN** a `seq[A]` and curried `folder: G -> ((G, A) -> G)`
- **WHEN** using `xs |@> folder` or `folder <@| xs`
- **THEN** it returns a function `G -> G` that folds the sequence

### Requirement: 代码质量

The system SHALL provide well-documented code with usage boundaries and examples.

#### Scenario: Readability
- **WHEN** a developer reads the source code
- **THEN** each operator has documentation comments explaining its signature, semantics, and edge cases

#### Scenario: Test coverage
- **WHEN** running tests
- **THEN** every operator has at least one positive test case, and edge cases are documented

## MODIFIED Requirements

None.

## REMOVED Requirements

None.
