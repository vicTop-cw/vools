# Scala 隐式双元操作符实现 Spec

## Why

需求文档 `docs/scala-implicit-operators/需求文档.md` 定义了一组 30 个 Scala 隐式双元操作符，用于函数组合与数据管道处理。需要在 `docs/scala-implicit-operators` 目录下以独立 Scala 2 项目形式实现这些操作符，并保证测试通过。

## What Changes

- 在 `docs/scala-implicit-operators/` 目录创建独立 Scala 2 项目
- 实现 30 个隐式双元操作符（15 对正向/反向）
- 编写完整的使用案例和边界说明注释
- 编写并运行测试用例，确保所有操作符行为正确

## Impact

- 新增目录：`docs/scala-implicit-operators/src/main/scala/` 与 `src/test/scala/`
- 新增文件：核心操作符实现、测试文件、构建脚本
- 不影响现有 vools 项目代码（独立项目，后续可选并入 `vools/bridge/scala`）

## ADDED Requirements

### Requirement: 项目结构与构建

The system SHALL provide a self-contained Scala 2 project under `docs/scala-implicit-operators/`.

#### Scenario: Build and test
- **WHEN** a developer runs the test command in the project directory
- **THEN** the project compiles with Scala 2 and all tests pass

### Requirement: 函|函 操作符

The system SHALL implement 18 function-to-function binary operators.

#### Scenario: Compose zero-arg to single-arg
- **GIVEN** `f: () => A` and `g: A => B`
- **WHEN** using `f o> g` or `g <o f`
- **THEN** it returns `() => B` that applies `g` to `f()`

#### Scenario: Compose zero-arg to two-arg
- **GIVEN** `f: () => A` and `g: (A, B) => C`
- **WHEN** using `f o>> g` or `g <<o f`
- **THEN** it returns `B => C` that applies `g(f(), b)`

#### Scenario: Unpack zero-arg result
- **GIVEN** `f: () => Seq[A]` and `g` requiring at least one `A`
- **WHEN** using `f *o> g` or `g <o* f`
- **THEN** it unpacks `f()` and partially applies `g`; remaining params form a new function

#### Scenario: Compose single-arg to single-arg
- **GIVEN** `f: D => A` and `g: A => B`
- **WHEN** using `f ~> g` or `g <~ f`
- **THEN** it returns `D => B` equivalent to `g compose f`

#### Scenario: Compose single-arg to two-arg
- **GIVEN** `f: D => A` and `g: (A, B) => C`
- **WHEN** using `f ~>> g` or `g <<~ f`
- **THEN** it returns `(D, B) => C`

#### Scenario: Unpack single-arg result
- **GIVEN** `f: D => Seq[A]` and `g` requiring at least one `A`
- **WHEN** using `f *~> g` or `g <~* f`
- **THEN** it unpacks `f(d)` and partially applies `g`; remaining params form a new function

#### Scenario: Compose two-arg to single-arg
- **GIVEN** `f: (D, F) => A` and `g: A => B`
- **WHEN** using `f ~~> g` or `g <~~ f`
- **THEN** it returns `(D, F) => B`

#### Scenario: Unpack two-arg result
- **GIVEN** `f: (D, F) => Seq[A]` and `g` requiring at least one `A`
- **WHEN** using `f *~~> g` or `g <~~* f`
- **THEN** it unpacks `f(d, f)` and partially applies `g`; remaining params form a new function

#### Scenario: Compose two-arg to two-arg
- **GIVEN** `f: (D, F) => A` and `g: (A, B) => C`
- **WHEN** using `f ~~>> g` or `g <<~~ f`
- **THEN** it returns `(D, F, B) => C`

### Requirement: 数|函 操作符

The system SHALL implement 12 value-to-function binary operators.

#### Scenario: Pipe value to function
- **GIVEN** a value `a: A` and `f: A => B`
- **WHEN** using `a |> f` or `f <| a`
- **THEN** it returns `f(a)`

#### Scenario: Map over iterable
- **GIVEN** an `Iterable[A]` and `f: A => B`
- **WHEN** using `xs |>> f` or `f <<| xs`
- **THEN** it returns an `Iterable[B]` equivalent to `xs.map(f)`

#### Scenario: Filter iterable
- **GIVEN** an `Iterable[A]` and predicate `f: A => Boolean`
- **WHEN** using `xs |?> f` or `f <?| xs`
- **THEN** it returns a filtered `Iterable[A]`

#### Scenario: Flat-map over iterable
- **GIVEN** an `Iterable[Iterable[A]]` and `f: A => B`
- **WHEN** using `xs |*> f` or `f <*| xs`
- **THEN** it flattens then maps, returning `Iterable[B]`

#### Scenario: Reduce iterable
- **GIVEN** an `Iterable[A]` and `op: (A, A) => A`
- **WHEN** using `xs |&> op` or `op <&| xs`
- **THEN** it returns the reduced value, equivalent to `xs.reduce(op)`

#### Scenario: Fold iterable
- **GIVEN** an `Iterable[A]` and curried `folder: G => (G, A) => G`
- **WHEN** using `xs |@> folder` or `folder <@| xs`
- **THEN** it returns a function `G => G` that folds the iterable

### Requirement: 代码质量

The system SHALL provide well-documented code with usage boundaries and examples.

#### Scenario: Readability
- **WHEN** a developer reads the source code
- **THEN** each operator has comments explaining its signature, semantics, and edge cases

#### Scenario: Test coverage
- **WHEN** running tests
- **THEN** every operator has at least one positive test case, and edge cases are documented

## MODIFIED Requirements

None.

## REMOVED Requirements

None.
