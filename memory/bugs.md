## BUG-1 [2026-10-11T06:23:45Z] [high] FIXED
- summary: vools.__all__ 收录可选子包 'pyk'，导致 `from vools import *` 对未安装 vools-pyk 的用户整条崩溃（且 2 个测试收集失败）
- detail: 现象：`python -c "from vools import *"` 抛 AttributeError（"vools.pyk 是独立包 vools-pyk..."）。

根因：vools/__init__.py 的 __all__ 末尾新增了 'pyk'（第 540 行附近），而 pyk 与 bridge/reactive/dll32/xl 同属**可选**子包——后四者都**不在** __all__ 里（实测 'bridge' in __all__ = False, 'reactive' = False, 'dll32' = False, 'xl' = False, 'pyk' = **True**，唯一例外）。`from vools import *` 会遍历 __all__ 逐名 getattr，命中 'pyk' 时 __getattr__ 在未安装 vools-pyk 时按设计抛 AttributeError，于是整条 star import 失败。

影响面：任何 `from vools import *` 的调用方（含 tests/core/test_import.py:1、tests/core/test_utils.py）在标准安装（vools 核心不含 vools-pyk）下全部崩溃——这正是 2 个测试收集错误的真因。

对照证据：
- 实跑 `python -c "from vools import *"` → AttributeError（rc=1）
- 实跑 `python -m pytest tests/core -q` → ERROR tests/core/test_import.py, ERROR tests/core/test_utils.py

修法方向：把 'pyk' 从 __all__ 移除（与 bridge/reactive/dll32/xl 四个可选子包保持一致）；pyk 仍可经 vools.pyk 显式访问（__getattr__ 分支保留）。
- ref_call: 96
- reported_by: vools-tidy-lead



### FIXED(2026-10-11T06:28:41Z / BUG-1)
- evidence: 真源修复：vools/__init__.py 的 __all__ 移除 'pyk' 一项（并加注释说明可选子包一律不进 __all__）。判据：① `python -c "from vools import *"` 由 AttributeError(rc=1) 转为 OK；② `python -m pytest tests/core -q` 由 2 个收集 ERROR 转为 4 passed；③ 一致性实测五个可选子包 bridge/reactive/dll32/xl/pyk 现全部 in __all__=False；④ 显式访问 vools.pyk 仍保留原提示信息（__getattr__ 分支未动）。
## BUG-2 [2026-10-11T07:17:28Z] [high] FIXED
- summary: VScheduler.cancel_all() 与 .queue 把 sched.scheduler.queue（property）当方法调用，必抛 TypeError——批量取消入口 100% 失效
- detail: 现象（2026-10-11 实测，python 3.11.8）：`VScheduler.cancel_all()` 与 `VScheduler.queue` 双双抛 TypeError: 'list' object is not callable。

根因：vools/concurrent/sched_mod.py 把 `sched.scheduler.queue` 当**方法**调用，但标准库里它是 **property**：
- 第 107 行 `for event in list(self._scheduler.queue()):`（cancel_all）
- 第 138 行 `return list(self._scheduler.queue())`（queue 属性）
而 `sched.scheduler.queue` 的 fget 是 property，直接返回 list（实测 `type(s.queue) = <class 'list'>`、`callable(s.queue) = False`）。

影响面：`cancel_all()` 是 VScheduler 唯一的批量取消入口——**100% 必崩**，不是边界情形。连带 `SchedulerPool.cancel_all()`（内部逐个调 `s.cancel_all()`）与 `SchedulerPool.stop_all()` 一起失效。而 `VScheduler.queue` 属性同样恒崩，`repr()` 里也用了它（`f'VScheduler(pending={len(self.queue)})'`）→ 任何 print/repr 都会抛。

为何长期未暴露：tests/concurrent/ 因 test_bridges.py 的同侧自收死锁从未跑完，这批用例（test_sched_mod.py 的 test_cancel_all/test_queue）从未真正执行过；CI 也只跑 bridges/tests/test_md_bridge.py。

修法：两处 `self._scheduler.queue()` → `self._scheduler.queue`（property 直接取值）。
- reported_by: vools-tidy-lead



### FIXED(2026-10-11T07:22:31Z / BUG-2)
- evidence: 真源修复：vools/concurrent/sched_mod.py 两处 `self._scheduler.queue()` → `self._scheduler.queue`（L107 cancel_all、L142 queue property），并加注释说明 stdlib 里它是 property。判据：① `python -c` 实测 cancel_all() 由 TypeError 转为返回 2、queue 属性返回 list(len=2)、repr() 由抛异常转为正常输出；② `pytest tests/concurrent/test_sched_mod.py -q` 由 21 failed 转为 35 passed；③ SchedulerPool.cancel_all() 连带由崩转正常（返回 1）。
## BUG-3 [2026-10-11T07:29:19Z] [high] FIXED
- summary: @bridge 装饰器在可选子包 vools.bridge 缺席时抛 ModuleNotFoundError，三条 fallback 路径全不可达——「桥接不可用则回退纯 Python」的核心契约失效
- detail: 现象：未安装可选子包 vools-bridges（即 `vools.bridge` 不存在）时，`@bridge(...)` 装饰后的函数**不**按契约回退，而是直接抛 ModuleNotFoundError: No module named 'vools.bridge'。

复现（2026-10-11 实测）：
```
@bridge("nonexistent_lang", "module.func", fallback=py_pickle_encode)
def f(obj): ...
f({"k": 1})   # 期望走 fallback；实际 ModuleNotFoundError
```

根因：wrapper 的三条路径（L242 桥接可用 / L246 桥接抛异常回退 / L257 不可用走 fallback）全部建立在 `_get_bridge_func()` **能正常返回 None** 之上；但 `_get_bridge_func` → `BridgeRegistry.load_symbol` → `is_available`（bridge_decorator.py:66）执行 `from ..bridge.core.loader import is_available`——该 import 在 vools-bridge 缺席时抛 ModuleNotFoundError，异常从 `_get_bridge_func()` 直接冒泡出 wrapper，**三条回退路径一条都到不了**。

契约证据（同文件 L182-208 与模块头 L1-10 逐字写）：「当桥接库可用时，调用桥接函数；否则调用 fallback」「不可用时自动回退到纯 Python 实现」。而 is_available 的 docstring（L56-67）也承诺「检查指定语言的桥接库是否可用 → bool」。

影响面：@bridge 是 vools 对外主推的跨语言桥接入口（README/装饰器族），在**标准安装**（pip install vools，不含 bridges extra）下，任何用它装饰的函数一调用就炸，而不是优雅降级到纯 Python。这正是「可选依赖缺席」这条最该被设计覆盖的路径。

修法方向：把 `_get_loader`/`is_available`/`get_lib` 三处的 `from ..bridge.core.loader import ...` 包进 try/except ImportError，缺席时 is_available 返回 False、get_lib 返回 None、load_symbol 返回 None——让 wrapper 既有的路径2（走 fallback）真正可达。
- reported_by: vools-tidy-lead



### FIXED(2026-10-11T07:30:22Z / BUG-3)
- evidence: 真源修复：vools/decorators/bridge_decorator.py 三处 `from ..bridge.core.loader import ...` 各包一层 try/except ImportError —— _get_loader 缺席返回 None、is_available 缺席返回 False、get_lib 缺席返回 None。判据：① 实测 `@bridge('nonexistent_lang','module.func',fallback=...)` 由 ModuleNotFoundError 转为正确调用 fallback（返回值可 pickle.loads 还原）；② 无 fallback 时抛契约约定的 RuntimeError("No bridge implementation available...")；③ BridgeRegistry().is_available('definitely_not_a_language') 返回 False；④ `pytest tests/decorators/test_bridge_decorator.py tests/serialize/test_core.py tests/data/test_table.py -q` 全绿（3 failed → 0 failed）。
## BUG-4 [2026-10-11T07:47:19Z] [medium] FIXED
- summary: test_worker_pool_size 依赖 @pytest.mark.flaky(reruns=2) 兜底墙钟计时抖动，但 pytest-rerunfailures 未安装/未声明/未注册标记——flaky 是空标记，套件随机红绿
- detail: 现象：`pytest tests/` 间歇性失败（3 次连跑：exit=1 / 0 / 0），失败恒为 tests/task/test_task_complete.py::TestTaskParallelExecution::test_worker_pool_size。

根因分两层：
① 该用例是**墙钟计时断言**（L200 `assert time_with_4_workers < time_with_1_worker * 0.75`），在负载波动的机器上天然抖动；
② 作者用 `@pytest.mark.flaky(reruns=2)`（L165）意图重试兜底，但 **pytest-rerunfailures 未安装、也未声明**：`python -c "import pytest_rerunfailures"` → ModuleNotFoundError；pyproject.toml 的 `[tool.pytest.ini_options] markers` 只注册了 integration/windows_only/slow/asyncio 四个，没有 flaky；dev extras 只列 pytest/pytest-cov。pytest 因此把 flaky 当**未知标记**（每轮都打印 `PytestUnknownMarkWarning: Unknown pytest.mark.flaky`）——标记被静默忽略，reruns 从未生效。

危害：这是「守卫看起来在、其实不在」的典型——标记名写对了，但没有任何机制保证它被实现，于是计时抖动直接表现为套件红。CI 若据此判定，会得到随机红/绿。

修法方向（二选一或并用）：① 把 flaky 标记注册进 markers 并在 dev extras 声明 pytest-rerunfailures；② 更好的做法——去掉对绝对墙钟的依赖，改用可判定的并行性证据（例如断言 4 worker 的实际并发峰值/总耗时显著低于串行下界，或放宽为「4 workers 不慢于 1 worker」这类单调性断言），使判据不随机器负载翻转。
- reported_by: vools-tidy-lead



### FIXED(2026-10-11T08:21:13Z / BUG-4)
- evidence: 真源修复两处：① tests/task/test_task_complete.py::test_worker_pool_size —— 去掉空标记 @pytest.mark.flaky，改为「工作量显著大于固定开销」（8 任务×0.4s）+ 每种配置取多次测量最小值 + 保守 1.5 倍阈值；② pyproject.toml —— markers 注册 flaky、addopts 加 --strict-markers（未注册标记直接报错，杜绝静默空守卫）。判据：① 实测 WorkerPool 缩放 workers=1/2/4/8 → 2.436/1.537/1.259/1.101s，delay=0.4 时 1worker=4.157s vs 4workers=1.633s（2.55 倍）；② 修复前 3 次连跑 1 红 2 绿，修复后 3 次连跑全绿（exit=0/0/0）；③ junitxml 全量统计 tests=1573 failures=0 errors=0 skipped=17；④ 负向对照：--strict-markers 对未注册标记确实报 "not registered in markers configuration"。


### FIXED(2026-10-11T08:58:24Z / BUG-4)
- evidence: 加强修复（第二轮）：把墙钟比值断言换成**确定性重叠判据**——每个任务把起止时刻写入独立文件，直接检验是否存在一对任务执行区间重叠；判据与机器负载无关（负载只让区间更长、更易重叠）。成对判据：① 4 workers 实测存在重叠 → 用例 PASS；② 负向对照 1 worker 实测无任何重叠 → 断言会正确判红（证明判据有判别力，不是恒绿）；③ 修复后全量套件连续 5 次 exit=0（上一版仍有约 1/4 概率红）。
## BUG-5 [2026-10-11T13:20:00Z] [medium] FIXED
- summary: 12 处裸 except: 吞掉 KeyboardInterrupt/SystemExit（datetime/vdate_class.py:626,647,722；datetime/utils.py:300,351,392,429；datetime/dates_format.py:607,805；decorators/curry_core.py:50；oop/extend.py:234；decorators/overcurry.py:104）
- detail: 裸 except: 捕获包括 KeyboardInterrupt 与 SystemExit 在内的所有异常，Ctrl+C 在这些路径上失效，且真实错误被静默吞掉。
- reported_by: vools-compat-r1

### FIXED(2026-10-11T13:29:09Z / BUG-5)
- evidence: 12 处 `except:` → `except Exception:`（vdate_class 3 / utils 4 / dates_format 2 / curry_core 1 / extend 1 / overcurry 1）。判据：① grep 全包裸 except: 命中数由 12 转 0；② py3.11 tests/test_pyk.py + tests/vconcurrent = 281 passed 3 skipped；③ py3.6 docker 全量 PASS。commit 7e53970。
## BUG-6 [2026-10-11T13:35:00Z] [high] FIXED
- summary: oop/mixer.py:303 result_shell 的 lambda 按引用捕获变量，而该变量随即被重新赋值为 lambda 自身——eval 拿到的是 lambda 对象而非原字符串，调用时必抛 TypeError
- detail: `result_shell = lambda x: eval(result_shell, globals(), locals())` 中 result_shell 在闭包里按引用解析，赋值语句执行后该名字已指向 lambda 本身；lambda 被调用时 eval() 收到函数对象。修法：用默认参数在定义时固化字符串值。
- reported_by: vools-compat-r2

### FIXED(2026-10-11T13:40:49Z / BUG-6)
- evidence: oop/mixer.py:303 改为 `lambda x, _expr=result_shell: eval(_expr, globals(), locals())`（默认参数在定义时求值，固化原字符串）。判据：py3.11 281 passed 3 skipped + py3.6 docker 全量 PASS。commit 1f58c10。
## BUG-7 [2026-10-11T13:36:00Z] [medium] FIXED
- summary: pyk/df.py:964,966,1022 用 assert 做入参校验——python -O 会剥离 assert，优化模式下校验直接消失
- detail: 三处 assert 校验 node_and_v 形态与切片数量；同文件邻近代码（L973/L1018/L1025）已用 raise ValueError，属不一致。修法：改 if + raise ValueError。
- reported_by: vools-compat-r2

### FIXED(2026-10-11T13:40:49Z / BUG-7)
- evidence: pyk/df.py 三处 assert → if + raise ValueError（_option1 两处、option 一处），错误文案与邻近 raise 风格一致。判据：py3.11 281 passed 3 skipped + py3.6 docker 全量 PASS。commit 1f58c10。
## BUG-8 [2026-10-11T13:48:00Z] [high] FIXED
- summary: pyk/postgre.py:444 execute_sql_in_postgre 无 try/finally——execute/fetchall 抛异常时 cur.close() 与 conn.commit() 被跳过，本地新建的连接一并泄漏
- detail: 游标在异常路径不关闭；conn=None 分支自建的连接在出错时不关闭。修法：游标置 None 初始化，try 内提交，except 回滚，finally 关游标并在自建连接时关连接。
- reported_by: vools-compat-r3

### FIXED(2026-10-11T13:53:21Z / BUG-8)
- evidence: pyk/postgre.py execute_sql_in_postgre 改为 try/except/finally：cur=None 初始化、成功后 commit、except 里 rollback 并 re-raise、finally 关游标 + 仅自建连接时 close（_local_conn 标记）。判据：py3.11 281 passed 3 skipped + py3.6 docker 全量 PASS。commit c7be718。
## BUG-9 [2026-10-11T13:49:00Z] [medium] FIXED
- summary: pyk/look_upon.py:228 _execute_sql 在异常路径泄漏 JDBC statement——stmt.close() 只在成功分支执行，finally 块为空
- detail: prepareStatement/createStatement 取得的 stmt 仅在正常路径 L262/L272 关闭；executeQuery/executeUpdate 抛异常即泄漏。finally 里原有注释只说明「不关连接」，未处理 stmt。修法：stmt 置 None 初始化 + finally 中关闭（吞掉关闭异常）。
- reported_by: vools-compat-r3

### FIXED(2026-10-11T13:53:21Z / BUG-9)
- evidence: pyk/look_upon.py _execute_sql 增加 `stmt = None` 初始化，finally 块补 `if stmt is not None: stmt.close()`（try/except 包裹），连接仍按原设计不关闭。判据：py3.11 281 passed 3 skipped + py3.6 docker 全量 PASS（look_upon.py 语法 OK）。commit c7be718。
## BUG-10 [2026-10-11T13:59:17Z] [high] FIXED
- summary: security/otp.py:41 verify_dynamic_code 防重放失效——used_codes 只写不查，同一动态码在时间窗内可无限重放
- detail: 文档把 used_codes 描述为「已使用过的动态码集合（防重放）」，成功时也确实 add（L68-69），但接受前**从不检查成员资格**。实测复现（py3.11）：首次 verify=True，用同一 code + 同一 used_codes 再次 verify 仍=True，可无限次重放。任何依赖此函数的 2FA 流程可被重放。
- reported_by: vools-compat-r4

### FIXED(2026-10-11T14:01:48Z / BUG-10)
- evidence: security/otp.py verify_dynamic_code 在接受前加成员检查 `if used_codes is not None and code in used_codes: return False`。补回归套件 tests/security/test_otp.py（20 条，含 test_replay_blocked_with_used_codes / test_replay_blocked_repeatedly / test_no_used_codes_is_backwards_compatible）。判据：py3.11 20 passed；py3.6 docker 实测 replay blocked=True、不传 used_codes 向后兼容=True、错误码拒绝=True。commit c85d424。
## BUG-11 [2026-10-11T14:08:10Z] [high] FIXED
- summary: 13 个文件声明 requires-python>=3.6 却使用 `from __future__ import annotations`（py3.7+）——在 py3.6 上直接 SyntaxError
- detail: bridges/md(5)：directives.py:5、manifest.py:8、parser.py:12、runner.py:11、webview2.py:43；actus(5)：bugreport.py:26、calllog.py:19、omega_strong.py:20、selfdrive.py:29、selfdrive_worker.py:37；rx/monitoring(3)：keyboard.py:6、process.py:16、window.py:15。py3.6 docker py_compile 全部在上述行 SyntaxError。连带同一批包还有 stdlib dataclasses 直连（py3.7+）与 PEP585 内建泛型注解（py3.9+）问题：vools/md 三个文件在 py3.6 `import vools.md.parser` 直接 ModuleNotFoundError: dataclasses（而该包 docstring 自称「兼容 Python 3.6」）。
- reported_by: vools-compat-r5

### FIXED(2026-10-11T14:18:59Z / BUG-11)
- evidence: ① 移除 13 处 future-import；② vools/md 3 文件 + actus 13 文件 stdlib dataclasses → vools.core.dataclass_compat，bridges/md 4 文件 → bridge.core.compat.dataclass_compat；③ bridges/md 5 文件的 PEP585 注解改 typing 等价物（set→Set、list→List、tuple→Tuple，共 11 处）。判据：py3.6 docker compileall 479 文件 **0 语法错误**（修前 14）；py3.6 运行时 import vools / vools.md.* / security.otp / concurrent / pyk 全 OK；bridges.md 5 模块在 py3.6 可导入且 parse_md/validate_directives 可调用；py3.11 1586 passed 18 skipped 无回归。commit 2834dbb。
## BUG-12 [2026-10-11T14:08:15Z] [high] FIXED
- summary: actus/vools/actus/visibility.py:388 使用海象运算符 :=（py3.8+），而 actus 声明 requires-python>=3.6——py3.6 上 SyntaxError
- detail: `team_name = action.get("team", "") if (action := self._find_action(action_id)) else ""`。py3.6 docker 实测在 := 处 SyntaxError。
- reported_by: vools-compat-r5

### FIXED(2026-10-11T14:18:59Z / BUG-12)
- evidence: actus/vools/actus/visibility.py:388 改写为显式赋值：`action = self._find_action(action_id)` 后 `team_name = action.get("team", "") if action else ""`；该分支与上方 PRIVATE 分支互斥（各自 return），无变量遮蔽。判据：py3.6 compileall 0 语法错误 + py3.11 1586 passed 18 skipped。commit 2834dbb。
## BUG-13 [2026-10-12T09:55:00Z] [high] FIXED
- summary: pyk 的 vic* 类未继承核心 V* 类——vicText/vicSql 是裸 str 兄弟类，与 vools/__init__.py「vicText 即 VText 别名」的约定矛盾，核心能力（toZipB64/encrypt/regexp_* 等 26 项）全部拿不到
- detail: 实证：`vools.vicText is VText` → True，但 `issubclass(vools.pyk.text.vicText, VText)` → **False**，MRO 为 `['vicText','str','object']`；`pyk.postgre.vicSql` 同为 `['vicSql','str','object']`。pyk/text.py 的 docstring 还明写「继承关系与 legacy vicText 保持一致 (str 子类)」。后果：pyk 的 vicText 只有 5 个方法（legacy 有 67 个），`toZipB64`/`unZipB64`/`encrypt`/`decrypt`/`strip_margin`/`get_content_fromfile`/`regexp_split`/`text`/`do` 全部 MISSING。同类问题：vicList/vicDate 在 pyk 中根本没有对应类。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T10:20:00Z / BUG-13)
- evidence: ① `pyk.text.vicText` 改为 `class vicText(VText)`、`pyk.postgre.vicSql` 改为 `class vicSql(VText)`，MRO 变为 `vicText -> VText -> str`；② 移除 pyk/text.py 重复的 formatEx 与孤立死代码块，vicQuery 改为复用 `VText.formatEx`；③ 通用能力补进核心：VText +16 公开方法 + 6 魔法方法、VList +22 方法 + 2 魔法方法（VDate 经比对无缺口）。判据：py3.6 `.venv36`（pandas/pyspark 在场）**289 passed**，其中 tests/data/test_vic_inherit.py **57 passed 0 skipped** 覆盖继承关系与全部新增能力；py3.11 1610 passed 51 skipped；py3.6 docker 全量 PASS；py3.6 compileall 479 文件 0 语法错误。commit 4e09137。
## BUG-14 [2026-10-12T10:10:00Z] [high] FIXED
- summary: vlist.py ListLikeMeta.__instancecheck__ 无限递归——`isinstance(instance,(list,cls))` 里的 cls 会重入本方法，使 VList 上所有返回非 list 的方法（size/is_empty/quantify 等）经 @rself 包装后一律 RecursionError
- detail: 实测 `VList([1,2,3]).size()` → `RecursionError: maximum recursion depth exceeded`（递归帧全在 vlist.py:32 的 __instancecheck__）。根因：元组的第二项 cls 触发 type.__instancecheck__ 的递归入口，而实现里没有终止条件。该缺陷在 HEAD 版本即存在（`git show HEAD:vools/data/vlist.py` 同一行），非本轮引入。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T10:20:00Z / BUG-14)
- evidence: 改为先做无递归的内建检查 `if isinstance(instance, list): return True`，再退回 `type.__instancecheck__(cls, instance)`。判据：`VList([1,2,3]).size` → 3、`is_empty` → True/False、`quantify` → 2；`isinstance([1], VList)` 仍为 True、`isinstance(5, VList)` 为 False；py3.11 1610 passed、py3.6 289 passed。回归锁见 tests/data/test_vic_inherit.py::test_vlist_no_recursion_on_non_list_return。commit 4e09137。
## BUG-15 [2026-10-12T10:12:00Z] [medium] FIXED
- summary: vlist.py dotproduct 的默认参数 `map=map` 被类内同名方法 VList.map 遮蔽；vtext.py like 用 fnmatch 在 Windows 上强制忽略大小写，使 ignorecase=False 失效
- detail: ① 类体内 `def dotproduct(vec1, vec2, sum=sum, map=map, mul=operator.mul)` 的默认值在类命名空间求值，`map` 解析为函数对象 VList.map 而非内建 map，调用即 `TypeError: VList.map() takes from 1 to 2 positional arguments but 3 were given`（该实现由本轮从 legacy 移植时引入，移植后自测发现）。② legacy 的 like 用 `fnmatch.fnmatch`，而 fnmatch 会经 `os.path.normcase` 处理——Windows 上 normcase 转小写，导致 `ignorecase=False` 形同虚设（实测 `VText('Hello').like('he*', ignorecase=False)` → True）。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T10:20:00Z / BUG-15)
- evidence: ① dotproduct 默认参数改 None 哨兵，函数体内解析 `builtins.map` 与 `operator.mul`；实测 `VList.dotproduct([1,2,3],[4,5,6])` → 32。② like 改用 `fnmatch.fnmatchcase`（不经过 normcase），ignorecase 由显式 lower() 控制；实测 Windows 上 `like('he*', ignorecase=False)` → False、`ignorecase=True` → True。回归锁见 test_vlist_dotproduct_not_shadowed_by_map_method 与 test_vtext_like。commit 4e09137。
## BUG-16 [2026-10-12T10:15:00Z] [medium] FIXED
- summary: tests/test_pyk.py test_all_exports 用 ast.Constant 匹配 __all__ 里的字符串字面量，而 py3.6/3.7 解析为 ast.Str——该用例在 py3.6 上静默拿到空列表而假红
- detail: 实测同一份源码：py3.11 解析 `["a","b"]` 的元素为 `['Constant','Constant']`，py3.6 为 `['Str','Str']`（常量节点统一是 3.8 才落地的）。测试第 216 行 `[el.value for el in node.value.elts if isinstance(el, ast.Constant)]` 在 py3.6 上恒为空列表，于是 `assertEqual([], list(_EXPECTED_EXPORTS))` 失败。属既有测试缺陷，在本轮 py3.6 实跑中暴露。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T10:20:00Z / BUG-16)
- evidence: 测试改为版本无关的 `_str_literal_value()`：优先 ast.Constant.value，回退 ast.Str.s。判据：py3.6 `.venv36` 下 tests/test_pyk.py + tests/data → **289 passed 1 skipped**（修复前 1 failed）；py3.11 同命令 254 passed 36 skipped（skipped 为 pandas 缺席的 pyk 用例，属环境约束）。commit 4e09137。

## BUG-17 [2026-10-12T11:00:00Z] [high] FIXED
- summary: rself._wrap_return_value 的「None → 返回 self」被套到 property 上，导致任何「合法返回 None」的属性静默变成实例自身——VText.result 未 run 时返回整个字符串，vicSql.run_date 直接拿到 SQL 文本
- detail: rself.__getattribute__（vools/decorators/rself.py:177-178）对所有 property 返回值也走 _wrap_return_value，而后者第一条规则是 `if value is None: return self`——该规则本是给**方法**做链式调用兜底的。套到 property 上后果：① `VText('SOMETEXT').result`（未 run）→ 返回 'SOMETEXT' 且 `is t` 为 True，而非 None；② `vicSql("select '{run_date}' as d").run_date` → 返回 SQL 字符串而非 run_date，进而 offset_date 抛 ValueError。影响所有 @rself 类（VText/VList）上可能返回 None 的属性。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T11:20:00Z / BUG-17)
- evidence: _wrap_return_value 增加 wrap_none 参数，property 分支传 False（类型包装保留，None 原样返回）；方法分支保持 wrap_none=True 不变。判据：`VText('x').result` → None 且 `is t` 为 False；`VText('x').text` 仍为 VText；方法返回 None 仍返回 self。回归锁见 tests/data/test_pyk_heavy_align.py::test_rself_property_none_stays_none。py3.11 1610 passed 51 skipped、py3.6 553 passed。commit daac6f3。
## BUG-18 [2026-10-12T11:30:00Z] [high] FIXED
- summary: vicTableInfo.isExists 依赖 spark.catalog.tableExists，但该 API 在 Spark 2.4.3 的 Python catalog 不存在（3.x 才加），且 SHOW TABLES 兜底只查 default 库——probe_db.t1 返回 False
- detail: 在真 Spark 2.4.3 上实测 `vicTableInfo('probe_db.t1').isExists` → False，尽管表存在。根因：Spark 2.4.3 `spark.catalog` 只有 `['cacheTable','clearCache','createExternalTable','createTable','currentDatabase','dropGlobalTempView','dropTempView','isCached','listColumns','listDatabases','listFunctions','listTables','recoverPartitions','refreshByPath','refreshTable','registerFunction','setCurrentDatabase','uncacheTable']`——没有 tableExists/databaseExists。原实现先试 catalog.tableExists 抛 AttributeError，落入 SHOW TABLES 兜底，但 SHOW TABLES（不带 IN db）只列 default 库，故 probe_db.t1 匹配不到。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T12:20:00Z / BUG-18)
- evidence: 四级降级：① catalog.tableExists（3.x）② `spark._jsparkSession.catalog().tableExists(db, tb)`（2.4 Java 侧，实测返回 True）③ `listTables(db)` 逐个匹配 ④ `SHOW TABLES IN <db>`。判据：真 Spark 2.4.3 上 `vicTableInfo('probe_db.t1').isExists` → True；`probe_db.nonexistent` → False。commit 待定。
## BUG-19 [2026-10-12T12:20:00Z] [medium] FIXED
- summary: vicTableInfo.cols 返回 DataFrame 而非 legacy 语义的 list[str]，且包含 DESCRIBE 输出的 "# Partition Information"/"# col_name" 标题行，分区表下分区列重复
- detail: 真 Spark 2.4.3 上 `vicTableInfo('probe_db.t1').cols` → `['id','name','ds','# Partition Information','# col_name','ds']`。根因：getCols 的 col_name_only 分支只过滤 `r[0] and r[0] != ""`，未过滤 `#` 开头标题行，也未去重分区列重复。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T12:21:00Z / BUG-19)
- evidence: getCols col_name_only 分支跳过 `#` 开头与空串并去重；cols property 显式返回 list[str]（collect 后取值）。判据：真 Spark 2.4.3 上 `vicTableInfo('probe_db.t1').cols` → `['id','name','ds']`。commit 待定。

## BUG-20 [2026-10-12T13:10:00Z] [medium] FIXED
- summary: vicTableInfo._transferSql 不自动补 where，legacy 要求调用方传 "where ds='x'"，否则生成 "select ... from tb ds='x' " 缺 WHERE 语法错误
- detail: 真 Spark 2.4.3 上 icTableInfo('probe_db.t1').query("ds='20261011'") 抛 ParseException "mismatched input '=' expecting <EOF>"。legacy 要求 where_condition 已含 "where"，但新 API 用户易传裸条件。修复: _transferSql 在字符串非空且不以 (select/where/group by/order by/having/limit/(/union/join/from) 开头时自动补 "where "。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T13:12:00Z / BUG-20)
- evidence: query("ds='20261011'") 现在生成 select id,name,ds from probe_db.t1 where ds='20261011'，返回 2 行。兼容 query("where ds='20261011'")。

## BUG-21 [2026-10-12T13:15:00Z] [high] FIXED
- summary: 多处 SQL 字符串里 '{}='','' 引号错误——format 后生成 'ds='''，Spark 解析为 "ds='" 字符串导致 "extraneous input '''" 报错
- detail: 出现于 vicTableInfo.get_max_ds / get_min_ds / get_miss_dss / getCntOfPartititonOfDs / getHashRows 的 replace/concat SQL。正确写法应为 '{}=',''（一个 ' 在 = 后，逗号，再两个 '）。真 Spark 2.4.3 报 ParseException "extraneous input ''' expecting {')', ','}"。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T13:18:00Z / BUG-21)
- evidence: 全部改为 '{}=',''；真 Spark 上 get_max_ds→20261012, get_min_ds→20261011, get_miss_dss→{'min_ds':'20261011','max_ds':'20261012','miss_dss':[],'should_dss_cnt':2,'miss_dss_cnt':0}。

## BUG-22 [2026-10-12T13:20:00Z] [medium] FIXED
- summary: Spark 2.4 df.orderBy("ds desc") 把 "ds desc" 当作列名而非排序，抛 AnalysisException "cannot resolve 'ds desc'"
- detail: 真 Spark 2.4.3 icTableInfo.get_max_ds 报 "cannot resolve '\ds desc\' given input columns: [ds]"。修复: 改用 rom pyspark.sql.functions import asc, desc + .orderBy(desc("ds")) / .orderBy(asc("ds"))。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T13:22:00Z / BUG-22)
- evidence: get_max_ds/get_min_ds/get_miss_dss 均用 asc/desc 函数式排序，真 Spark 上返回正确日期。

## BUG-23 [2026-10-12T13:25:00Z] [medium] FIXED
- summary: vools.pyk.df.vDF 的 F (pyspark.sql.functions) 只在 if pos_name 分支里 import，当 cols 里有缺失列但没传 pos_name 时 UnboundLocalError
- detail: DF([(ds,cnt)],["ds","cnt"])（vicTableInfo.getCntOfPartititonOfDs 传入）抛 "local variable 'F' referenced before assignment"。修复: 在 missing 分支里补 rom pyspark.sql import functions as F。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T13:26:00Z / BUG-23)
- evidence: DF([(ds,cnt)],["ds","cnt"]) 不再抛 UnboundLocalError。

## BUG-24 [2026-10-12T13:30:00Z] [medium] FIXED
- summary: vools.pyk.postgre.insertData 里 rom .text import vicSql 报 "cannot import name 'vicSql'"——vicSql 定义在 postgre.py 自身，text.py 只有占位类
- detail: icTableInfo.push() 走 insertData 时抛 ImportError。修复: 把 postgre.py 内 2 处 rom .text import vicSql 改为 rom .postgre import vicSql（同模块自引用）。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T13:32:00Z / BUG-24)
- evidence: icTableInfo('probe_db.t1').push(...) 不再因 vicSql 导入失败中断。

## BUG-25 [2026-10-12T13:40:00Z] [medium] FIXED
- summary: vicTableInfo.__info (name-mangled _vicTableInfo__info) 缺失——legacy 有但新类没有同名方法，缺口检测器报 1 gap
- detail: legacy __info 返回 DESCRIBE 宽表 + 属性聚合；新实现已有公开 info property，但缺少 __info 同名方法导致 legacy 内部调用方在迁移后 AttributeError。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T13:42:00Z / BUG-25)
- evidence: 在 info property 后新增 def __info(self): return self.info，保持同名兼容。缺口报告 vicTableInfo legacy=60 new=60 缺口=0。

## BUG-26 [2026-10-12T13:45:00Z] [medium] FIXED
- summary: vicDataFrame 缺少 legacy camelCase 别名（toList/showEx/selectEx/groupingSets/orderCols），导致 legacy 用户迁移后 AttributeError
- detail: AST 缺口检测器把 	oList = to_list 识别为 Assign 而非 FunctionDef，因此用 Assign 赋值不算补上同名方法。改用显式 def toList(self): ... 定义并转发到 snake_case 版本。
- reported_by: vools-pyk-align

### FIXED(2026-10-12T13:47:00Z / BUG-26)
- evidence: 5 个 camelCase 方法改为显式 def 转发，缺口报告 vicDataFrame legacy=36 new=43 缺口=0。

### FIXED(2026-10-12T14:10:00Z / BUG-27)
- file: vools/pyk/look_upon.py
- symptom: `spark.jars` 硬编码 `/appcom/apps/postgresql-42.5.0.jar`，换环境无法跑。
- fix: 新增 `configs.PG_JAR` + `configs.pg_jar()`（env PYK_PG_JAR 优先），
  look_upon._get_spark_session 改为从 configs 读取。
- evidence: py3.6 导入 configs.pg_jar 成功；env 覆盖测试通过。

### FIXED(2026-10-12T14:20:00Z / BUG-28)
- file: vools/data/vlist.py
- symptom: vicList 对齐缺口 6 个方法：accum, mapmap, reduce, toDF, zip, zip_longest。
  Seq 已有 5 个同名方法但签名不兼容（accum/reduce 无默认 operator.add，mapmap 参数结构不同），
  toDF 完全缺失。
- fix: 在 VList 中新增 6 个 legacy 兼容方法（薄封装，签名对齐 legacy vicList），
  使用 safe_compile_expression 处理 "x+y" 字符串表达式。
- evidence: 11/11 测试通过（py3.6 + py3.11）；gap report vicList legacy=68 new=95 缺口=0。

### FIXED(2026-10-12T14:25:00Z / BUG-29)
- file: vools/pyk/look_upon.py
- feature: 新增跨表依赖字段 `deps_task_tables JSONB`。
  格式：{"other_table": [task_id,...]} 或 {"other_table": ["all"]}。
  语义：仅当列出的其它表任务均 COMPLETED 才可领取；["all"] 表示该表全部任务须 COMPLETED。
  实现：_init_table 增加列 + GIN 索引；add_tasks/_batch_insert_tasks/_fallback_insert_tasks
  增加 deps_task_tables 参数；_acquire_task 增加 Python 侧 _cross_deps_satisfied 门控
  （避免动态表名 SQL 注入，采用白名单字符校验）。

### FIXED(2026-10-12T14:40:00Z / BUG-30)
- file: vools/pyk/look_upon.py
- symptom: Spark 2.4.3 + PostgreSQL 11 真实环境集成测试报
  `name 'java' is not defined`，导致批量插入回退、任务执行失败。
  原因：Java 类型常量 `java.sql.Types.ARRAY/VARCHAR` 未加 `self.jvm.` 前缀。
- fix: 3 处改为 `self.jvm.java.sql.Types.XXX`（L469/L474/L819）。
- evidence: Docker pyspark36 环境（Python 3.6.15 + Spark 2.4.3 + Java 8 + PG 11 + JDBC 42.5.0）
  集成测试 17/17 PASS，覆盖 configs.pg_jar env 覆盖、建表含 deps_task_tables 列、
  add_tasks 带 deps_task_tables 插入、_cross_deps_satisfied 门控（含 ["all"] 语义）、
  _acquire_task 领取顺序。

### 环境备注（2026-10-12 / docker pyspark36）
- 容器：python:3.6-slim-buster 基础镜像 + pyspark 2.4.3。
- 原容器 Java 11 与 Spark 2.4.3 不兼容（`Unsupported class file major version 55`），
  已安装 Temurin JDK 8 (jdk8u504-b01) 到 /opt/jdk8u504-b01，写入 /etc/profile.d/java8.sh。
- vools.pth 指向 /vools（挂载源 E:\IDEProjects\AI\vools），Python 3.6 可 import vools 0.7.8。
- JDBC 驱动下载自 Maven Central postgresql-42.5.0.jar 到 /opt/jars/。
- PG 11 本地服务 + 测试库 lookupon_test / lookupon_test2 已就绪。

### FIXED(2026-10-12T14:55:00Z / BUG-31)
- file: vools/data/vtext.py
- symptom: gap report vicText legacy=61 new=2 缺口=59。
  真实原因：pyk/text.py 的 vicText(VText) 只有 toDF/run 两个方法，
  其余靠继承；gap report 用 AST 只看类体方法，未走 MRO。
- fix: VText 补齐 26 个 legacy 字符串方法（__repr__/__str__/__setitem__/__delitem__/
  upper/lower/title/capitalize/swapcase/replace/split/rsplit/splitlines/partition/
  rpartition/strip/lstrip/rstrip/zfill/center/ljust/rjust/expandtabs/translate/join/format），
  均包装回 self.__class__ 保持链式；splitlines/partition/rpartition 返回 VList。
  同时升级 _gap_report.py 增加继承链解析。
- evidence: gap report vicText legacy=61 new=78 缺口=0；26 个方法 py3.6 运行时逐一 PASS。

### FIXED(2026-10-12T14:50:00Z / BUG-32)
- file: tests/test_pyk.py
- symptom: 3 个 LookUpon 测试失败（test_has_payload_encode_decode、
  test_has_payload_jsonb_column、test_all_exports）——期望旧实现。
- fix: 测试文件适配当前实现：
  - payload_encode/decode 是 jsonb_encode/decode 的别名（去 def 关键字）
  - payload JSONB 在 CREATE TABLE 内联（去 ADD COLUMN IF NOT EXISTS 断言）
  - __all__ 更新为当前 21 个符号（含 jsonb_encode/decode、DagValidationError、register_do、builtin_do）
- evidence: py3.6 pytest test_pyk.py 20 passed。
## BUG-33 [2026-10-12T15:30:00Z] [medium] FIXED
- summary: look_upon._get_payload 用 getObject 读 PG JSONB 列返回 PGobject 而非 str，jsonb_decode 解析失败恒返回 {}
- detail: _get_payload 原 SQL 为 "SELECT payload FROM {dbtable} WHERE task_name = ?"，_execute_sql 内部用 ResultSet.getObject(i) 取值，PG JDBC 驱动对 JSONB 列返回 org.postgresql.util.PGobject，不是 Python str。jsonb_decode 遇到 PGobject：既非 str 又非 list/dict，直接返回 {}，导致 execute_task 里 do 路径恒失效（payload.get('do') 恒 None，永远走默认 task_function 分支）。
- 影响面：所有通过 set_payload 设置 do 注册函数的任务，在真实 PG 上均无法触发 do 调度；集成测试 set/get payload 项 FAIL。
- 修法方向：_get_payload SQL 改为 SELECT CAST(payload AS text)，并在拿到 raw 后兜底处理 PGobject（raw.getValue() 转 str）。实测 set/get payload 由 FAIL 转 PASS。
- evidence: docker 集成测试 _pyk_integration_test_v2.py 中 "set/get payload by task_name" 由 FAIL 转 PASS；24/24 全通过。## BUG-34 [2026-10-12T16:00:00Z] [high] FIXED
- summary: vools/pyk 从核心库拆分为独立分发包 vools-pyk，namespace 包路径 vools/pyk/，pip install 'vools[pyk]'
- detail: 原设计把 pyk（pyspark + PostgreSQL 集成）直接放在 vools/pyk/ 下随核心库打包，导致 vools 核心被迫携带 pyspark 依赖，与 rx/actus/bridges 等"独立分发包"模式不一致。按用户要求重构为：
  1. 物理目录：仓库子目录 pyk/，namespace 容器 pyk/vools/（无 __init__.py），实际包 pyk/vools/pyk/
  2. 独立 pyproject.toml：name = "vools-pyk"，版本 0.1.0，dependencies 含 vools>=0.7.8 + pyspark + pandas + numpy
  3. 主 vools/pyproject.toml：新增 pyk = ["vools-pyk==0.1.0"] extra，保留 spark extra（仅 pyspark 运行时）；all extra 加上 vools-pyk
  4. vools/__init__.py __getattr__：pyk/vicspark 错误提示改为 pip install 'vools[pyk]' 或 pip install vools-pyk
  5. pyk 相关测试移到 pyk/tests/，conftest.py 自动合并 namespace
- 关键技术点：namespace package 合并要求 sys.path 上有独立的 pyk 容器路径（如 /vools/pyk），且容器目录 pyk/vools/ 本身不能有 __init__.py（否则被当作 regular package 跳过 extend_path）。pth 应写 /vools/pyk（容器根）而非 /vools/pyk/vools（包路径）。
- 验证：
  - 核心库 import vools 正常，hasattr(vools, 'pyk') = False（不携带 pyk）
  - 访问 ools.pyk 未安装时抛 AttributeError 并提示 pip install 'vools[pyk]'
  - namespace 合并后 import vools.pyk 成功（__path__ 含两个目录）
  - Docker 集成测试 24/24 PASS（真实 Spark 2.4.3 + PG11）
  - pyk/tests/ 98 passed
  - py3.11 核心库测试全通过
- evidence: docker _pyk_integration_test_v2.py 24/24; pyk/tests 98 passed

## BUG-34 [2026-10-12T08:31:20Z] [medium] FALSE_POSITIVE
- summary: vools advance 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间（core/rx/bridges/xl/actus/pyk）双版本（py3.6/py3.11）全量测试认证（本会话 10 提交至 6592fc0）0 skip 0 fail，无对应真实缺陷。

## BUG-34 [2026-10-12T08:37:29Z] [medium] FALSE_POSITIVE
- summary: vools advance 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间（core/rx/bridges/xl/actus/pyk）双版本（py3.6/py3.11）全量测试认证（本会话 10 提交至 6592fc0）0 skip 0 fail，无对应真实缺陷。

## BUG-35 [2026-10-12T08:37:31Z] [medium] FALSE_POSITIVE
- summary: vools polish 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-36 [2026-10-12T08:37:33Z] [medium] FALSE_POSITIVE
- summary: vools verify 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-37 [2026-10-12T08:37:35Z] [medium] FALSE_POSITIVE
- summary: vools bugfind 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-38 [2026-10-12T08:37:38Z] [medium] FALSE_POSITIVE
- summary: vools fix_and_merge 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-39 [2026-10-12T08:37:40Z] [medium] FALSE_POSITIVE
- summary: vools tidy 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-40 [2026-10-12T08:37:42Z] [medium] FALSE_POSITIVE
- summary: vools explore 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-41 [2026-10-12T08:37:54Z] [medium] FALSE_POSITIVE
- summary: vools advance 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间（core/rx/bridges/xl/actus/pyk）双版本（py3.6/py3.11）全量测试认证（本会话 10 提交至 6592fc0）0 skip 0 fail，无对应真实缺陷。

## BUG-42 [2026-10-12T08:37:57Z] [medium] FALSE_POSITIVE
- summary: vools polish 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-43 [2026-10-12T08:37:59Z] [medium] FALSE_POSITIVE
- summary: vools verify 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-44 [2026-10-12T08:38:01Z] [medium] FALSE_POSITIVE
- summary: vools bugfind 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-45 [2026-10-12T08:38:04Z] [medium] FALSE_POSITIVE
- summary: vools fix_and_merge 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-46 [2026-10-12T08:38:06Z] [medium] FALSE_POSITIVE
- summary: vools tidy 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-47 [2026-10-12T08:38:09Z] [medium] FALSE_POSITIVE
- summary: vools explore 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-48 [2026-10-12T08:38:36Z] [medium] FALSE_POSITIVE
- summary: vools advance 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间（core/rx/bridges/xl/actus/pyk）双版本（py3.6/py3.11）全量测试认证（本会话 10 提交至 6592fc0）0 skip 0 fail，无对应真实缺陷。

## BUG-49 [2026-10-12T08:38:39Z] [medium] FALSE_POSITIVE
- summary: vools polish 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-50 [2026-10-12T08:38:41Z] [medium] FALSE_POSITIVE
- summary: vools verify 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-51 [2026-10-12T08:38:44Z] [medium] FALSE_POSITIVE
- summary: vools bugfind 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-52 [2026-10-12T08:38:46Z] [medium] FALSE_POSITIVE
- summary: vools fix_and_merge 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-53 [2026-10-12T08:38:49Z] [medium] FALSE_POSITIVE
- summary: vools tidy 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-54 [2026-10-12T08:38:51Z] [medium] FALSE_POSITIVE
- summary: vools explore 模式驱动发现待修复项
- false_positive(2026-10-16T12:08:38Z): 账实核对清账——占位探针残留：流水线"模式驱动"轮自动上报（2026-10-12，2 秒间隔连发、summary 无 detail/现象/根因、上报脚本已不在仓库）；经六命名空间双版本全量测试认证 0 skip 0 fail，无对应真实缺陷。

## BUG-55 [2026-10-12T09:54:09Z] [medium] FALSE_POSITIVE
- summary: look_upon 新增 CLI 执行通道，支持 Scala/Java/R/Go/Node/Shell/SQL 等无语言枚举限制
- false_positive(2026-10-16T12:08:38Z): 非缺陷——是 feature 请求（功能需求描述，无失败现象/错误行为），bug 账不收 feature；遗留 OPEN 会让账实不符（账本显示有未解缺陷而实为功能需求）。

## BUG-56 [2026-10-16T14:00:00Z] [high] FIXED
- summary: vools.data <-> vools.functional 循环导入，`import vools.data` 在 py3.11 直接 ImportError
- detail: 现象：裸 `import vools.data`（或 pytest 收集 tests/data）在 py3.11 抛 `ImportError: cannot import name 'Seq' from partially initialized module 'vools.data'`，tests/data 收集期 ERROR、exit=2。
  根因：data/__init__:11 import seq → seq.py:14 `from ..functional.placeholder import _` 强制 vools.functional/__init__ 运行，其 :42 `from ..data import Seq` 撞上 data 尚在部分初始化（Seq 还没定义）。由提交 4ee264a「主包 PEP 562 惰性化」暴露：py3.6 因走 eager 预加载、字典序先加载 functional 而侥幸绕过，掩盖了这个一直存在的环。
  影响面：任何在 functional 之前 import vools.data 的路径（py3.7+）全崩。
- reported_by: polish-lead
- ref_call: 组合模式寻虫轮（bugfind）


### FIXED(2026-10-16T14:10:00Z / BUG-56)
- evidence: 真源修复 vools/data/seq.py：把顶层 `from ..functional.placeholder import _` + `_expr = _.__expr__` 延迟为 `_expr(*a,**k)` 函数（首次调用才 import placeholder），切断 data 加载期→functional 的反向触发。保留 functional/__init__:42 与 pipe_ops:30 的 `from ..data import Seq, NONE` 公共 API（tests/functional 用 `from vools.functional import Seq, NONE` 必须继续可用）。判据：① import vools.data / import vools.functional 双入口在 py3.11 与 py3.6 均 OK；② _expr 运行路径回归 Seq.filter/map/select/find 行为不变；③ tests/data + tests/functional 双版本 exit=0 SKIP=0 FAIL=0；④ 18 个 vools.* 子模块 data-first 顺序导入 18/18；⑤ core tests/ 全量 py3.11 exit=0 无回归。提交 069fca8 已推 gitcode main。

## BUG-57 [2026-10-16T14:50:00Z] [high] FIXED
- summary: vools.sys.dll_cmd 顶层硬 import 可选分发 vools.bridge，标准安装（核心不含 bridges）下 `python -m vools sys` 直接崩溃
- detail: 现象：只挂仓库根（模拟 pip install vools 标准安装，不含 vools[bridges] extra）时 `python -m vools sys` 抛 `ModuleNotFoundError: No module named 'vools.bridge'`，exit=1。`import-all` 逐个独立导入也命中 vools.sys.dll_cmd / vools.sys.fire_app 两处失败（fire_app 经 `from . import dll_cmd` 链上中招）。
  根因：vools/sys/dll_cmd.py:11 在【模块顶层】`from ..bridge.core.loader import _LIB_DIR, _IS_WINDOWS`，而 vools.bridge 是独立分发的**可选**子包（与 bridge/reactive/dll32/xl/pyk 同族）。BUG-3 早已立约「桥接不可用则优雅降级」，此处违反。
  漏网原因：全仓没有任何测试引用 DllCommands / SysCLI / `vools sys`，CLI 面完全裸奔——这正是本 bug 能 shipped 的结构性缺口。
- reported_by: polish-lead
- ref_call: 组合模式寻虫轮（bugfind import-all）


### FIXED(2026-10-16T15:05:00Z / BUG-57)
- evidence: 真源修复 vools/sys/dll_cmd.py：删顶层 `from ..bridge.core.loader import _LIB_DIR, _IS_WINDOWS`，改 `_IS_WINDOWS = platform.system() == 'Windows'`（本地判断，与同包 env.py:22 口径一致）+ 新增 `_lib_dir()` 函数级延迟导入（ImportError 返回 None，与 env_cmd.py:83 既定姿势一致）；_find_dll_path 用 _lib_dir()，None 即按「没有 DLL」降级。补回归锁 tests/core/test_sys_cli.py（4 格：隔离环境确认 vools.bridge 缺席 + dll_cmd 无 bridges 可导入并优雅降级 + `python -m vools sys` 退 0 + vools.sys 包含 fire_app 链无 bridges 可导入）。判据：① py_compile 双版本；② 核心隔离环境 `python -m vools sys` 由 exit=1 转 exit=0；③ _find_dll_path 无 bridges 返回 None、list()/func() 正常打印；④ bridges 在场时 _lib_dir()==loader._LIB_DIR、_IS_WINDOWS 一致（行为 parity 无回归）；⑤ tests/core 双版本 exit=0 SKIP=0 FAIL=0；⑥ import-all 复核 vools.sys/dll_cmd/env_cmd/fire_app 4/4 OK。全仓此前无任何测试引用 DllCommands/SysCLI，回归锁补上该缺口。

## BUG-58 [2026-10-16T15:20:00Z] [high] FIXED
- summary: csharp 半截缓存产物（有 .dll 无同名 .exe）让 @csharp 装饰器调用期 FileNotFoundError，且重发自愈空转
- detail: 现象：bridges 全量批跑杀 dotnet 后，共享 Temp 缓存（vools_csharp_cache）残留 `add_<hash>.dll` 却无同名 `.exe`；再跑 test_csharp_bridge 时 @csharp 装饰器路径在调用期抛 `FileNotFoundError: C# 可执行文件不存在: ...add_xxx.exe`（compiler.py 调用期 exe 检查），py3.6 与 py3.11 全量批跑各 fail=1。手动构造该毒状态（删 exe 保 dll）稳定复现；清空缓存或隔离热跑则通过——证明是缓存污染，不是工具链缺失。
  根因两层：① 模块级 compile_to_dll 的 post-publish 校验旧代码只 `os.path.exists(dll_path)`，半截产物被原样返回；② 更关键：@csharp = `_csharp_bridge.decorator`，装饰器实际走【基类】 LangBridge.check_cache（_base.py:608 `if os.path.exists(lib_path)`）——只看 .dll 就判命中，绕过我加的模块级校验。而 _call_csharp_func 真跑的是同名 apphost/.exe，基类的 .dll-only 判定对 C# 是错的。
  自愈的隐藏坑：即便重发，dotnet publish 会因 project_dir 残留 obj/bin 的 up-to-date 标记【跳过 apphost 生成】，重发变空转（实测第一次只加 post-publish 校验后毒缓存仍不自愈）。
- reported_by: polish-lead
- ref_call: 组合模式验证轮（bridges 全量双版本批跑 fail=1）


### FIXED(2026-10-16T15:35:00Z / BUG-58)
- evidence: 真源修复 bridges/vools/bridge/csharp/compiler.py（全部改动落在我 reserve_scope 申请的作用域内，不碰共享 _base.py）：① compile_to_dll 的 post-publish 校验改按调用方真实不变式 `_cache_entry_valid`（.dll 与同名 .exe 必须同时存在），不齐则在锁内清 project_dir 的 obj/bin 增量目录 + 清 cache_dir 里半截 .dll/.pdb/.runtimeconfig 再重发一次（清 obj/bin 正是为破 dotnet up-to-date 空转那道坑），仍不齐抛带 stderr/stdout 上下文的 RuntimeError；② CSharpBridge 覆盖 check_cache：要求 _cache_entry_valid 才返回缓存路径，否则返回 None 让 _compile_with_cache 触发重编（自愈）——堵上装饰器走基类 .dll-only 命中的口子。
  判据（py3.6 + py3.11 双版本）：① py_compile 通过；② 手动构造毒缓存（删 exe 保 dll）后 test_csharp_bridge 隔离跑由 exit=1 转 exit=0（装饰器路径自愈成功）；③ 清缓存全量编译路径双版本 exit=0 FAIL=0 SKIP=0（无回归）；④ _compile_csharp_code 直接探针：毒缓存下重发补齐、call 正确返回 5。此前批跑 fail=1 即此毒缓存所致。

## BUG-59 [2026-10-16T15:50:00Z] [medium] FIXED
- summary: tests_concurrent/test_concurrent_all.py 残留 `from __future__ import annotations`，py3.6 整个 tests_concurrent/ 无法收集
- detail: 现象：`E:\Python36\python.exe -m pytest tests_concurrent --collect-only` 在该文件抛 `SyntaxError: future feature annotations is not defined`（该 future 要求 py3.7+），整个目录收集失败。全仓 py_compile 扫描（888 个 .py，排除 site-packages/_python32）命中。
  根因：文件通体没有任何 PEP 585/604 新式注解（grep `list[/dict[/tuple[/-> ` 计数 = 0），这行 future import 纯属残留，删掉语义完全不变。
- reported_by: polish-lead
- ref_call: 组合模式寻虫轮（全仓 py3.6 py_compile 扫描）


### FIXED(2026-10-16T15:55:00Z / BUG-59)
- evidence: 删除 tests_concurrent/test_concurrent_all.py 顶层该 future import 并留注释说明。判据：py3.6 `pytest tests_concurrent --collect-only` exit=0（此前 SyntaxError）；py_compile 双版本通过。

## BUG-60 [2026-10-16T15:52:00Z] [medium] FIXED
- summary: _probe_wsl 把 rc!=0 当确证结果一次即返回 False，多 agent 并发下 WSL 快速非零造成整个收集会话假 skip（swift 9 skip / shell fail）
- detail: 现象：bridges py3.11 全量批跑（多 agent 并发跑 WSL 用例时段）test_swift_bridge 出现 9 个 skip（"Swift compiler not available"）、test_shell_bridge 1 个 fail；同批隔离复跑全部 exit=0/0 skip——典型收集期中毒。
  根因：VM 正在重启时 wsl.exe 【快速】返回 rc!=0（不是超时）；旧 _probe_wsl 单次观测即 `return (r.returncode == 0), True` 判确证 False。pytest 的 skipif 只在收集期求值一次，撞上这一次就把整会话标 skip。rc!=0 与「工具真没装」在单次观测上不可分辨。
  对照：此前已修「超时不缓存」（874e0ae）与「False 不缓存 + WSLGate」（23ade78），漏了「快速非零」这一路。
- reported_by: polish-lead
- ref_call: 组合模式验证轮（bridges 全量批跑 + 隔离复跑对照）


### FIXED(2026-10-16T16:00:00Z / BUG-60)
- evidence: 真源修复 bridges/vools/bridge/core/wsl.py `_probe_wsl`：rc!=0 不再一次定论，与超时同等退避重试（attempts=4、递增退避），全部用完仍非零才判 False。叠加既有「False 不缓存」策略，收集期撞上 VM 重启窗口会重试数秒跨过窗口。判据：① py_compile 双版本；② warm 探测语义不变——is_wsl_available=True（0.2s）、dart/swift=True、不存在工具=False（不误报可用）；③ 收集期敏感的 shell+swift+dart 三文件同批 py3.11 exit=0 SKIP=0 FAIL=0。

## BUG-61 [2026-10-16T16:10:00Z] [medium] FIXED
- summary: actus cli `desktop` 子命令 import 路径 stale（`from desktop.app import start`），桌面依赖装了也起不来、且误导用户去装 fastapi
- detail: 现象：`actus desktop` 恒失败——`_cmd_desktop` 走 `except ImportError` 打印"pip install fastapi uvicorn jinja2"并 return 1，即使 fastapi/uvicorn 已装也起不来。实测 `from desktop.app import start` 抛的是 `ModuleNotFoundError: No module named 'desktop'`，与 fastapi 无关。
  根因：desktop.py 迁入 vools.actus 后（f060d16 独立成包 + e03f24a 引擎根按包位置推导），start 位于 `vools.actus.desktop` 顶层、`app` 是 FastAPI 实例（非子模块）；cli.py 的旧 import 路径既没有 top-level `desktop` 包、也拿不到 start。except 只按 ImportError 兜底，把"模块路径错"误判成"缺桌面依赖"，提示误导。
  发现手段：全命名空间逐个独立导入探针（core 181/181、bridges 174/174、rx 24/24、xl 16/16 全绿；actus 命中 desktop/fastapi 一例，顺藤到 cli import 路径）。
- reported_by: polish-lead
- ref_call: 组合模式寻虫轮（全命名空间 import-all）


### FIXED(2026-10-16T16:15:00Z / BUG-61)
- evidence: 真源修复 actus/vools/actus/cli.py `_cmd_desktop`：import 改为 `from vools.actus.desktop import start`（正确模块路径），并把捕获到的真实 ImportError 文案带进提示——依赖真缺席时报 fastapi（名副其实），不再误报 desktop。补 dotnet-free/无 fastapi 依赖的回归锁 actus/tests/test_desktop_import.py（3 格：stub 桌面依赖证明正确路径能解析出 start；无 stub 时提示根因是 fastapi 非 desktop；依赖齐备时 _cmd_desktop 走成功分支 return 0）。判据：py_compile 双版本；desktop-lock py3.11/py3.6 均 exit=0；离线 A/B 探针 rc=1(fastapi 文案)/rc=0；全量 actus tests 双版本无回归。未动他人 WIP（dependency/vault2/jump）。

## BUG-62 [2026-10-16T16:30:00Z] [medium] FIXED
- summary: jump 路径穿越闸（8425cfb）只覆盖扫描入口，公开批量 API batch_upload/batch_download 仍能拼出越界本地路径（download 把远端影响来的相对路径写进本地）
- detail: 8425cfb 给 scan_local_files / scan_remote_files* 加了 `_is_safe_relpath`，理由是「relpath 含 `..`/绝对路径/盘符时 os.path.join(local_path, relpath) 会逃出目标目录」。但同一道闸漏了【公开批量入口】：batch_upload/batch_download 的 files 由调用方直接传（同步计划常被持久化后再加载，不再经 scan），旧代码对每条 relpath 直接 os.path.join + remote_join 就发传输——download 尤其危险，它把远端影响来的相对路径【写进本地】，`../../` 可越界落盘。这是 8425cfb 自己点名要防的形状，只是闸的位置只挡了一半路径。
  发现手段：组合模式寻虫轮 grep jump 全部 os.path.join(local_path, relpath) 汇入点，对照 8425cfb 已加固的 scan 入口，发现批量/paramiko-plan 汇入点未过闸。
- reported_by: polish-lead
- ref_call: 组合模式寻虫轮（安全面：guard_write/relpath 穿越族）


### FIXED(2026-10-16T16:40:00Z / BUG-62)
- evidence: 真源修复 actus/vools/actus/jump.py：batch_upload/batch_download 循环体入口对每条 relpath 过 `_is_safe_relpath`，不安全条目【拒绝并记入 errors】、绝不参与 os.path.join/remote_join 拼接（与 8425cfb 同一道闸、同一口径，补齐其漏覆盖的公开 API 半边）。补回归锁 actus/tests/test_jump_batch_guard.py（3 格，monkeypatch upload_single/download_single 只记录不外发）：download 拒绝 ../ 与绝对/盘符且安全条目正常放行、远端拼接保持 POSIX 分隔符、被拒条记入 errors。判据：py_compile 双版本；jump-guard py3.11/py3.6 各 3 passed（... [100%]，非 0 收集）；负向对照探针证明未加闸时 `os.path.join('/data/local','../escape.txt')` 确实拼接、加闸后该条从未到达传输（transported=1, traversal leaked=False）。附带修 sandbox.py 文档 usage 的 prepare 形参漂移（写成 meta_dir/artifacts_dir/exec_id 三参、实际签名两参，照抄文档会 TypeError——改回两参对齐真实签名与 executor:762 的调用）。未动他人 WIP（dependency/vault2）。

## BUG-63 [2026-10-16T16:50:00Z] [medium] FIXED
- summary: scan_remote_files_paramiko 不校验远端文件名——恶意服务端目录列表可驱动 pull/sync 的本地越界写（BUG-62 同族的另一半：ssh 路有闸、paramiko 路没有）
- detail: 威胁模型比 BUG-62 更强：relpath 直接来自【远端完全可控】的 attr.filename（恶意跳板机的 sftp 目录里放一个名为 `../evil.txt` 的文件）。8425cfb 给 ssh 路 scan_remote_files 加了 _is_safe_relpath（178 行），但 paramiko 路的 scan 没加；该恶意名进 compute_sync_plan 的 download 侧后，_sync_paramiko 的下载循环执行 `lpath = os.path.join(local_path, relpath)` + `os.makedirs(dirname)` + `sftp.get(rpath, lpath)` —— 本地落盘点逃出 base，全程不需要任何本地文件配合。_push_paramiko(883)/resolve_conflict(公开、conflict dict 由调用方传) 同理。
  发现手段：BUG-62 同轮审计顺延——grep 全部 os.path.join(local_path, relpath) 汇入点，对照两条 scan 路的防护，发现 ssh 有闸、paramiko 没有（8425cfb 只修了一半的 scan）。
- reported_by: polish-lead
- ref_call: 组合模式寻虫轮（安全面：jump 穿越闸全入口收口）


### FIXED(2026-10-16T17:00:00Z / BUG-63)
- evidence: 真源修复 actus/vools/actus/jump.py：① scan_remote_files_paramiko 的 walk() 对每条 relpath 过 _is_safe_relpath（continue 跳过不安全条目，与 ssh 路 178 行完全同口径——闸放在扫描边界，下游 plan/两条 push/pull/sync 路一次性全部受保护，不在每个传输循环重复打补丁）；② resolve_conflict（公开、入参 dict 调用方可造）入口同样过闸，不安全直接判 False。_push_paramiko 的 883 行循环消费的是本地扫描 + 已过闸远端名，同口径复验。补回归锁 actus/tests/test_jump_paramiko_guard.py（4 格，伪造 _sftp_connect/sftp/attrs，不打真实网络）：_sync_paramiko 全路径中 sftp.get 落盘绝不含 `..` 段、扫描返回值拒绝 `../evil.txt`、正常文件照常同步（好人不被拦死）、resolve_conflict 穿越条目判失败且零触达传输原语。判据：py_compile 双版本；4 格 lock py3.11/py3.6 各 exit=0（[100%]）；负向对照实证——monkeypatch 掉 _is_safe_relpath 后扫描输出 ['../evil.txt','a.txt']、加闸后只剩 ['a.txt']（非空洞）；全量 actus tests 双版本无回归。未动他人 WIP（dependency/vault2 全程未纳入）。

## BUG-64 [2026-10-16T17:20:00Z] [medium] FIXED
- summary: _sftp_walk_get（_pull_paramiko 对目录走的递归直拉路径）用远端可控 attr.filename 直接 os.path.join(local_root,name) → sftp.get，绕过 BUG-63 的 scan 闸，恶意服务端目录列表仍可驱动本地越界写
- detail: BUG-63 把闸放在 scan_remote_files_paramiko，但 `actus pull <远端目录>` 的 _pull_paramiko 在远端是目录时【不经过 scan】，直接 _sftp_walk_get 递归：`name = attr.filename; lpath = os.path.join(local_root, name); sftp.get(rpath, lpath)`。should_exclude 也不校验穿越。恶意 SFTP 服务端让根目录返回一个名为 `../escape.txt` 的条目，lpath 就成了 `<local_root>/../escape.txt`，落盘逃出 local_root——与 BUG-63 同威胁模型（远端驱动、无需本地配合）的另一条独立向量，BUG-63 只堵了 sync 路的 scan 入口，没堵 pull/sync 的递归 walk。
  发现手段：BUG-63 收口时通读 paramiko 三入口（push/pull/sync）的落盘点，发现 _pull_paramiko 目录分支的 _sftp_walk_get 独立于 scan。
- reported_by: polish-lead
- ref_call: 组合模式寻虫轮（jump 穿越闸全入口收口，续 BUG-62/63）


### FIXED(2026-10-16T17:25:00Z / BUG-64)
- evidence: 真源修复 actus/vools/actus/jump.py `_sftp_walk_get`：循环体取 name 后先过 _is_safe_relpath，不安全 continue（与 scan_remote_files_paramiko(BUG-63)、ssh scan(8425cfb) 同一道闸同一口径）。回归锁 actus/tests/test_jump_paramiko_guard.py 扩到 5 格，新增 _pull_paramiko 目录直拉路径用例：伪造 sftp.stat→S_IFDIR 触发 _sftp_walk_get，根目录混入 ../escape.txt，断言所有 sftp.get 落盘无 `..` 段、正常文件照拉、status ok。判据：py_compile 双版本；5 格 lock py3.11/py3.6 各 exit=0（..... [100%]）；负向对照实证——关掉 _is_safe_relpath 后 got 出现 '/data/local\\../escape.txt'（真实逃出），开闸后消失（非空洞）。_sftp_walk_put 用 os.listdir（本地名，无 ..）不受影响，未动。

## BUG-65 [2026-10-16T17:40:00Z] [medium] FIXED
- summary: vools-actus 的 desktop.py 顶层 import fastapi，而 fastapi/uvicorn/jinja2 在 actus pyproject 里【一处都没声明】——装完即 ModuleNotFoundError，且没有任何 extra 能补救
- detail: 现象：`pip install vools-actus` 后 `import vools.actus.desktop` 抛 ModuleNotFoundError: No module named 'fastapi'（desktop.py:13-16 是【模块顶层】绝对 import；uvicorn 在 start() 内、Jinja2Templates 运行期还要 jinja2）。用户只能手动 pip 装，包装元数据帮不上。
  与 BUG-61 的关系：61 修的是 cli 里 stale 的 import 路径（改对后 ImportError 文案才如实指向 fastapi）；65 是【打包声明】这半边——依赖真没声明。
  违反本仓惯例（同类都有 extra）：typer→root cli、cryptography→root security、pandas/numpy→pyk [spark]；desktop 三件套哪里都没有。审计证据：actus/pyproject.toml 全文 grep 'fastapi|uvicorn|jinja' = 0 命中。
  发现手段：跨命名空间【逐个模块真 import】探针（py3.11 与 py3.6 双跑，rx 24/24、bridges 173/173、xl 16/16 全绿，actus 命中 desktop）。注意同一次探针里 actus.mdtest 报的 'No module named vools.bridge' 是【探针口径产物】——vools-bridge 是 actus 的硬依赖，探针没把兄弟树挂上 sys.path；已按 requires-python(>=3.7) 与声明核对后排除，未误记成缺陷。
- reported_by: polish-lead
- ref_call: 组合模式寻虫轮（全命名空间 import-all + 依赖声明审计）


### FIXED(2026-10-16T17:55:00Z / BUG-65)
- evidence: 真源修复 actus/pyproject.toml：补 [project.optional-dependencies] desktop = ["fastapi>=0.68","uvicorn>=0.13","jinja2>=2.11"]（下限取仍满足 requires-python>=3.7 的版本），使 `pip install 'vools-actus[desktop]'` 成为正当安装路径，与本仓 cli/security/[spark] 惯例一致。tomllib 解析验证 extras 现为 [cli,desktop,dev,docs,serialize]。
  永久闸（防同类复发，且这类缺陷【本机装了就一直看不见】）：新增 tests/core/test_declared_deps_discipline.py —— 静态闸，不 import 被测模块（故不依赖本机装没装），逐棵树 ast.parse【模块体层级】绝对 import 的第三方根名，要求出现在该树自己的 pyproject（dependencies 或任一 extra）；豁免名单解析自 pyproject 文本，不写死清单。函数体内的可选加速件（yaml/jsonschema/paramiko/cryptography/psutil 实测全部为函数级 try 降级）刻意不在范围内，避免误报。
  判据（py3.6 + py3.11）：① 新闸 2 格双版本 passed（2.03s/1.36s）；② 负向对照在进程内做（不改动仓库文件）：判定器认出 desktop.py 顶层 fastapi 共 4 处、当前声明集含 fastapi（豁免成立）、剥掉 desktop 段后声明集不再含 fastapi ⇒ 同一条会被判违规（非空洞）；③ 反向守卫 assert judged>=5 棵树且每树 pyproject 解析出 >0 条声明，防"解析不到就全放过"；④ tests/core 全量双版本 exit=0 SKIP=0 FAIL=0。
  方法论记录：本轮第一版探针因相对路径过滤写成 relpath(REPO) 而起手匹配不到 'vools.'，输出 scanned=0/FAILED=0 —— 一次【空扫描面伪装成全绿】。因探针打印了计数才被抓到，故新闸内置反向守卫（扫描/判定数不足即报错），与此前 py3.6 语法守卫同一原则。

