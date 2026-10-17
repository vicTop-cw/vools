# vools 项目清整（2026-10-11）

## 结构现状（清整后）
- 核心：`vools/`（18 个子包）+ 5 个独立子包 `bridges/ rx/ dll32/ xl/ actus/`（`pyk/` 已并入 `vools/pyk/`）
- AI 辅助工具统一在 **`.AI/`**（trae/workbuddy/atomcode/codeartsdoer/run，139 files，tracked）
- 测试：`tests/`（1593 用例）+ `tests_concurrent/`
- 文档：`docs/ changelog/ README.md README_FOR_AI.md USER_GUIDE.md CHANGELOG.md`
- 工具：`dev_tools/`（合规检查）+ `dev-tools/`（nim-core 源 + 脚本）

## 已删除（非 vools / 临时物）
`voxc/`(106MB) `vox-plugin/` `Temp/`(441MB) `_migrate/ output/ build/ dist/ gen_assets
.mdbuild/ .pytest_cache/ *.egg-info/` + 全部 `__pycache__`。体积 1600MB → 1044MB。

## 本轮修复的 4 条真缺陷（提交 7725226）
1. **可选子包不得进 `__all__`**：`from vools import *` 会逐名 getattr，可选子包缺席时
   `__getattr__` 抛 AttributeError ⇒ 整条 star import 崩。bridge/reactive/dll32/xl/pyk
   五个可选子包一律不进 `__all__`，用显式 `vools.xxx` 访问。
2. **`sched.scheduler.queue` 是 property**，不能写成 `queue()`。
3. **`@bridge` 的 fallback 契约**：对可选子包 vools.bridge 的 import 必须包 try/except，
   否则「不可用则回退纯 Python」的三条路径全不可达。
4. **守卫必须可证明有效**：`@pytest.mark.flaky` 若未注册 pytest-rerunfailures 就是空标记；
   已注册该标记 + 开启 `--strict-markers`。计时类断言改用确定性判据（区间重叠），
   不用墙钟比值。

## 环境注意
- MCP `fist-mbt` 的 server cwd 是 `E:/IDEProjects/AI/FIST-Mbt`，其 `project_dir`
  只接受**相对路径且拒 `..`**；要操作本仓需走 junction `_proj_vools`。
- `run_check` 的 `workdir` 对相对 `project_dir` 传 `.` 会被拒（守卫自身文档说可以传，
  但段长比较把它挡了）——传 `_proj_vools` 这类具体相对目录。
- 客户端 `timeout_ms=30000`，跑全量测试请用本地 shell 而非 run_check。
- 仓库有**并发写入者**（本会话期间另有进程提交 e2acda1/e3e430c 等并改了 pyk/otp.py），
  提交时用精确 pathspec，避免把别人的改动裹进自己的提交。