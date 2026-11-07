# vools-actus 基建 T0 验收报告

> 命名空间：vools-actus-infra ｜ 任务树：T0（parent）→ T0.1~T0.5
> 生成：2026-11-07 ｜ 验收人：main

## 一、任务树状态

| 任务 | 状态 | assignee | 验收要点 | 交付 commit |
|---|---|---|---|---|
| T0.1 | 已完成 | main | actus/tests -m not slow 全绿 | 2abf8102 |
| T0.2 | 已完成 | main | 剪贴板真实读写用例通过 | a7de6d3 |
| T0.3 | 已完成 | main | 配置+动作示例，交互无链路控制代码 | 908fbd17 |
| T0.4 | 已完成 | main | git stash 干净、现场清理 | （纯清理，无 commit） |
| T0.5 | 已完成 | main | 本报告真实落盘 | 本次提交 |

T0 根任务 cleanup_mode=deferred，全部子任务完成后按需做最终收口（task_cleanup）。

## 二、产出清单（commit 自底向上）

1. `2abf8102` test(vools): T0.1 回归全绿
   - 197 个 test_*.py 分 N1/N2a/N2b/N3/N4a/N4b 六批全绿（含此前未跑过的 79 个文件）
   - 修复：子进程 PYTHONPATH 注入、种子签名重签、Tk 单实例
   - pyproject 排除 manual_gui + 补齐依赖声明；conftest 隔离运行时目录

2. `a7de6d3` feat(actus): T0.2 vools.reactive 剪贴板能力落地 actus
   - 新增 actus/vools/actus/clipboard.py（clip_read/clip_write/clip_clear/clip_watch/ClipWatcher，配置+动作式封装，依赖 vools.reactive rx 命名空间）
   - __init__._LAZY 与 __all__ 注册懒加载导出
   - tests/conftest.py 增补 rx/ 根 sys.path 注入
   - 新增 actus/tests/test_clipboard_integration.py 8 个真实剪贴板读写用例
   - 相关导出契约测试 97 个全绿

3. `908fbd17` feat(rhop): T0.3 配置驱动交互示例
   - rhop/examples/README.md：A/B/C 三角拓扑、配置形态、interact() 三模式总览
   - roundtrip_demo.py：单机闭环 A->B->A 全链路
   - two_proc_send.py / two_proc_recv.py：双进程 A/B 端交互
   - 三种形态真实运行全绿；rhop 核心测试（test_actions/test_interact/test_session）43 passed
   - p0..pN 跳板链与 ROLE=p0..p3 配置无残留（仅废弃声明与禁止性测试）

4. T0.4 仓库现场清理（无独立 commit）
   - 删除 32 个未跟踪中间产物（.zombie_*、*.log、OUTFILE、probe_sem2.py、merge_cov.py 等）
   - 确认 stash@{0}/stash@{1} 修复均已合入 main（qax.py _check_1based、cmd.py _quote_arg、merge 36ae68a）后安全 drop，git stash list 干净

## 三、测试状态

- T0.1：actus/tests 197 个文件全绿（-m not slow）
- T0.2：剪贴板集成用例 8 个 + 导出契约 97 个全绿
- T0.3：rhop 核心 43 passed；示例三形态（execute / roundtrip / 双进程）实跑全绿

## 四、剩余风险与交接

1. **nul**（仓库根 0 字节保留名文件）：Windows 保留设备名限制，delete/git clean/rename 均无法处理，需用户主界面手动删除。
2. **并行 R10H 在途产物**：工作树存在并行任务（R10H 平台枚举/索引指纹）的在途修改与未跟踪产物（OUTFILE_*、_r10h_*、actus/vools/actus/keys/ 等），非 T0 基建范围，未处理以免干扰；后续任务前需与其协调或等其合入。
3. **分支同步**：main ahead of origin/main（本轮新增 3 个 commit），按需 push。
4. **T0 根收口**：子任务全部完成后，如无需再拆，可对 T0 执行 task_cleanup / verify 完成根任务。
