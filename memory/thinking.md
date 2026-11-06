# 思考流水（Thinking）

## [bugfind] 2026-10-28 12:00 | rhop-pg 列映射 / 迁移 / 并发 三条取证
- 目标：只读寻虫，产出可复核的待修队列（不改代码）。
- 契约等价性静态对照（PG vs SQLite）：schema 列序 == TASK_COLUMNS 31 列（一致）；方法签名齐全；首轮 2 处 DIVERGE 是**我判据的转义问题**（源码是 `%%s` 我拿 `%s` 匹配），修正后归零——先疑判据再疑代码。
- 并发语义：`claim_next` 用带状态守卫的 `UPDATE ... RETURNING`，不会重复领取；但缺 `FOR UPDATE SKIP LOCKED`（争抢时阻塞而非跳过）。
- 三条结论：
  | 编号 | 级别 | 问题 | 取证方式 |
  |---|---|---|---|
  | BUG-361 | high | `SELECT *` + `zip(TASK_COLUMNS,row)` 依赖物理列序，旧库静默错位 | 最小复现：worker_id/owner 同型对调 → 读回互换、无异常 |
  | BUG-362 | medium | 无 schema 版本/迁移（仅 CREATE TABLE IF NOT EXISTS） | `user_version|ALTER TABLE` 零命中，describe() 无版本 |
  | BUG-363 | low | 未用 SKIP LOCKED，无 PG 并发用例 | `FOR UPDATE|SKIP LOCKED` 零命中；test_pg_store 40 条皆单进程 |
- 教训：静态对等只能证明结构一致；`SELECT *` 这类位置耦合必须用「旧物理列序」的假行才能逼出。

## [fix_and_merge] 2026-10-28 12:05 | BUG-361 修复 + BUG-359 收口
- 复杂度自评：c=1（单文件、根因明确、验证手段现成）。
- BUG-361：pg_store.py 引入 `_SELECT_COLS = ", ".join(TASK_COLUMNS)`，8 处语句改显式列（6 处 SELECT + 1 处 RETURNING + list_tasks 动态拼接）。
- 新增 rhop/tests/test_pg_store_explicit_columns.py 7 用例：假 DB-API 层按「旧物理列序」返回行 → get_task/list_tasks/claim_next 均不错位；控制组证明旧写法确实互换；静态守卫禁止 SELECT */RETURNING *；schema 列序自校。
- 变异验证（证明测试有牙）：把 get_task 改回 SELECT * → 红在 `worker-1 != alice`；恢复 → 7/7 绿。
- BUG-359：文档计数回写（582 passed / 622 collected / pg 40 条），audit 新增 10c 段校验「文档头状态行 vs §16」，变异（状态行 999）→ mismatch 1，恢复 → 0。
- 验收：全量 `pytest tests -q` → 582 passed / 40 skipped；`audit_api_doc.py 582` → checks 61 / mismatch 0 / exit 0。
- 未做（需真实 PG，本机无 DSN）：BUG-362 schema 版本门、BUG-363 SKIP LOCKED + 并发用例；已入账留待下一轮。

## [fix_and_merge] 2026-10-28 12:42 | BUG-362 修复（补列迁移 + schema 版本标记）
- 复杂度自评：c=1（单文件 + 单测试文件，根因明确，验证手段=假 DB-API 语句级断言）。
- 修法：31 列定义收敛为 `_COLUMN_DDL` 单一来源 → `schema_sql()` 由它生成、`migration_sql()` 逐列幂等 `ADD COLUMN IF NOT EXISTS`；身份列（SERIAL 主键 / UNIQUE 逻辑主键）跳过，`NOT NULL` 无 DEFAULT 者补 `DEFAULT ''`；再补 `_SCHEMA_VERSION=1` + `<table>_schema_meta` 元数据表（三句全幂等、版本只前向），`describe()` 回显版本与表名。
- 等价性证据：`schema_sql()` 与 HEAD **去空白后逐字节一致（1306=1306）**——重构没有改任何 DDL 语义，这一点比"读起来一样"强得多。
- 测试有牙：12 用例 + 7 组变异（跳过全部补列 / 白名单多一列 / 去掉 DEFAULT / 去掉 IF NOT EXISTS / 不写版本 / 版本可回退 / 无幂等守卫）全部被抓。其中「白名单多一列」第一版**逃检**了——因为期望值从被测模块的 `_MIGRATION_SKIP` 读，变异同时改了两边；改成测试侧硬编码后即被抓。教训：变异测试必须让探针与被测代码不同源。
- 顺带修 BUG-364：clipboard 两条真机冒烟只判断「后端可探测」，不判断「操作可用」；本机 PowerShell `Set-Clipboard` 实测抛 ExternalException，导致全量红灯。加能力探针后 skip（协议层仍由假 backend 覆盖）。
- 验收：全量 `592 passed / 42 skipped / 0 failed`；`audit_api_doc.py 592` → mismatch 0 / exit 0（§16、逐文件、状态行三处一致）；docs/task-queue.md 计数与新增测试行同步回写。
- 未做：真实 PG 上执行这些 DDL（本机无 DSN）——语句级验证 + 语句顺序断言；BUG-363（SKIP LOCKED）仍待 PG 环境。


## [bugfind] 2026-10-28 12:53 | Round 8：常驻容错 / 崩溃回收上限 / 续期参数校验
- 复杂度自评：c=2（跨 queue/store/daemon 三个模块 + 并发语义，验证手段是自建探针 + 最小复现，而非单点断言）。
- 取证方法：写 `rhop/tools/probe_round8_concurrency.py`（5 个探针，临时目录建库、不触碰仓库数据）。先盲探全量状态机与生命周期入口，再对可疑点构造可判定实验；关键一步是把「运维动作」直接搬进 handler 内部执行，才逼出「执行期间 requeue」这条真实路径——纯静态阅读只看到 `set_state` 无 expect_version，看不出它会被 force 改写打穿。
- 结论（3 条入账）：BUG-365 收尾无所有权门控 + `run_resident` 无异常隔离（high，一次 requeue 打死常驻消费者）；BUG-366 崩溃回收绕过 max_retries（medium，毒任务无限重跑）；BUG-367 `renew_interval_sec` 无校验且静默 clamp（low）。
- 关键对照实验：执行期间 `cancel`（置标志）→ 优雅落 CANCELLED，不抛错；执行期间 `requeue`（force 改状态）→ StoreError 逃逸。差别只在「收尾是否认持有者」，这比读 BUG-329 的注释更有说服力。
- 教训：①`run_resident` 这种长驻循环是「异常放大器」——单点 StoreError 的爆炸半径不是一次任务失败，而是整侧停摆，审代码时应把「循环体内是否有 try/except」当成高优先级信号；②force=True 的运维 API 与执行器收尾写回天然冲突，任何「force 可改状态」的设计都必须配套「收尾认持有者/版本」；③探针里曾把 `handler` 当成 `{"name": ...}` 传导致解析失败，正确姿势是 `register_handler(name, fn)` + 任务 dict 里 `"handler": "<name>"`（`INSTRUCTION_KEYS` 决定它进 payload）。
- 未做：BUG-365/366/367 均未修（本轮是 bugfind 只读模式）；PG store 的同类语义（set_state 是否同样的非法流转校验、回收计数）未验证——本机无 DSN。
