# do 方法统一到 VoolsBase —— 司令作战手册（v2 终版）

> 目标：让 44 个类继承 `vools.core.base.VoolsBase`，删除本地 `do` 方法，
> 功能全保留、零回归。20 个特殊类保留本地 `do`（见 R2）。

## 统一改造动作（每个可改造类）
1. 类定义加基类：`class X:` → `class X(VoolsBase):`
   已有基类 → 追加到末尾：`class X(OldBase, VoolsBase):`
2. 删除类里本地 `do` 方法块（从 `def do(...)` 到方法结束）
3. 文件头补导入（若未导入）：
   - `vools/<pkg>/<mod>.py` → `from ..core.base import VoolsBase`
   - `vools/<pkg>/<sub>/<mod>.py` → `from ...core.base import VoolsBase`
   - `vools/config.py` → `from .core.base import VoolsBase`
4. 不改动其他任何代码

## R2 保留清单（20 个，不改继承、保留本地 do）
| 类 | 文件 | 原因 |
|---|---|---|
| VoolsBase | vools/core/base.py | 自身 |
| Singleton | vools/cache/once.py | 动态生成类（once 装饰器） |
| VoolsError | vools/core/exceptions.py | Exception 子类 |
| CurryExecutionError | vools/decorators/curry_core.py | Exception 子类 |
| ExpressionSecurityError | vools/security/expression_handler.py | Exception 子类 |
| SafeEvalError | vools/security/safe_eval.py | Exception 子类 |
| ListLikeMeta | vools/data/vlist.py | 元类（bases=type） |
| EncoderMeta | vools/encoding/core.py | 元类（bases=type） |
| attr_Enum | vools/oop/mixer.py | 枚举（IntFlag） |
| VText | vools/data/vtext.py | 不可变内置子类（str） |
| VDate | vools/datetime/vdate_class.py | 不可变内置子类（datetime） |
| Result | vools/functional/result.py | Generic[T, E] |
| Hoder | vools/utils/hoder.py | 代理类（__getattr__ 代理） |
| Box | vools/functional/box.py | 代理类 |
| Magic | vools/functional/placeholder.py | 代理类 |
| _X | vools/functional/placeholder_impl.py | 代理类 |
| _Y | vools/functional/placeholder_impl.py | 代理类 |
| Mixer | vools/oop/mixer.py | 代理类 |
| CurriedMethod | vools/decorators/curry_decorator.py | 代理类 |
| EnhancedDateFormatter | vools/datetime/dates_format.py | 代理类 |

## R2 原则
- 枚举/元类/内置不可变子类/Generic：多继承不安全（用户明确豁免）
- Exception 子类：VoolsBase.__str__ 会覆盖异常消息显示，破坏下游
- 代理类（`__getattr__`）：VoolsBase 注入的 dunder 绕过 `__getattr__`，破坏代理语义

## 各下属任务
| 下属 | 文件夹 | 可改造类 |
|---|---|---|
| A | vools/cache/ vools/core/ vools/config.py vools/crypto/ vools/security/ | TimedCache, FileLock, ConfigManager(core/config), ConfigManager(vools/config), _MISSING_TYPE, CryptoRegistry, Encryptor, Decryptor, SafeExpressionEvaluator |
| B | vools/data/ vools/datetime/ vools/decorators/ vools/oop/ vools/functional/ | Itor, Seq, VList, DateProcessor, T, OvercurryManager, Selector, Overloads, CodecRegistry, Encoder, Decoder, Pipe, CallableDescriptor, SubscriptExecutor, TestClass, CallableInstance, ClassFusion, Mixer_ |
| C | vools/serialize/ | BaseBackend, JsonBackend, MsgpackBackend, PickleBackend, CallableHandler, DecoratorHandler, FunctionalHandler, Serializer |
| D | vools/task/ | TaskQueue, TaskStorage, Worker, WorkerPool, ThreadPool, TaskDecorator, DagScheduler, RuleEngine, Rule, RuleSet |

## 验证（每个下属必须做）
1. 每个改造类：`python -c "from <mod> import <Cls>; assert Cls.do.__qualname__=='VoolsBase.do'"`
2. 行为：`x.do()` 返回 self；`x.do(lambda s: s)` 返回 self
3. 跑相关 pytest 子集（`pytest tests -k <关键词>` 或整目录）
4. 确认 `git diff` 只包含：继承行 + do 删除 + import

## 禁止
- 不改 `do` 的语义、签名、返回值
- 不删除保留清单的 do
- 不添加额外功能、不重构其他代码
- 不提交（由司令统一提交）
