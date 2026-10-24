# -*- coding: utf-8 -*-
"""回归测试：do 方法统一到 VoolsBase（统一特征）。

背景：vools 曾有 65 处**逐字重复**的 `do(self, f=print, pre_f=None, sub_f=None)`，
散落在 cache/core/crypto/data/decorators/encoding/functional/oop/security/
serialize/task/utils 等 30+ 文件。本次统一为：可继承的类一律继承
`vools.core.base.VoolsBase` 并删除本地 `do`，从而「功能全保留 + 兼容」。

**豁免清单（R2）**——这些类不能/不应继承 VoolsBase，保留本地 `do`：
- 元类（bases=type）：ListLikeMeta、EncoderMeta——实例是类本身，注入 dunder 语义错乱
- 枚举（IntFlag）：attr_Enum——枚举成员语义特殊
- 不可变内置子类：VText(str)、VDate(datetime)——mixin 会改变实例布局/构造语义
- 泛型基类：Result(Generic[T, E])——参数化后 MRO 不稳定
- 异常类：VoolsError / CurryExecutionError / ExpressionSecurityError / SafeEvalError
  ——VoolsBase.__str__ 会覆盖异常消息显示，破坏下游报错可读性
- 代理类（__getattr__ 转发内部对象）：Hoder、Box、Magic、_X、_Y、Mixer、CurriedMethod、
  EnhancedDateFormatter——特殊方法走类型查找，注入的 dunder 会绕过代理
- 动态生成类：once.Singleton（`@once` 装饰器按被装饰类动态生成子类）
- 自身：VoolsBase

**不同签名，天然保留**：`Ops.do(x, func)`（vools/functional/__init__.py 与 pipe_ops.py）
是「对任意值做副作用」的独立 API，签名 `(self, x, func)` 与链式 `do(self, f, pre_f, sub_f)` 不同。
"""

import ast
import importlib
import os

import pytest

from vools.core.base import VoolsBase

# ── 已统一：必须继承 VoolsBase 且类内不再有本地 do ──────────────────────────
CONVERTED = [
    # cache
    ("vools/cache/memorize.py", "TimedCache"),
    ("vools/cache/persist.py", "FileLock"),
    # core / 顶层 config
    ("vools/config.py", "ConfigManager"),
    ("vools/core/config.py", "ConfigManager"),
    ("vools/core/dataclass_compat.py", "_MISSING_TYPE"),
    # crypto
    ("vools/crypto/core.py", "CryptoRegistry"),
    ("vools/crypto/core.py", "Encryptor"),
    ("vools/crypto/core.py", "Decryptor"),
    # data
    ("vools/data/itor.py", "Itor"),
    ("vools/data/seq.py", "Seq"),
    ("vools/data/vlist.py", "VList"),
    # datetime
    ("vools/datetime/dates_format.py", "DateProcessor"),
    # decorators
    ("vools/decorators/curry_decorator.py", "T"),
    ("vools/decorators/overcurry.py", "OvercurryManager"),
    ("vools/decorators/selector.py", "Selector"),
    ("vools/decorators/selector.py", "Overloads"),
    # encoding
    ("vools/encoding/core.py", "CodecRegistry"),
    ("vools/encoding/core.py", "Encoder"),
    ("vools/encoding/core.py", "Decoder"),
    # functional
    ("vools/functional/__init__.py", "Pipe"),
    ("vools/functional/box.py", "CallableDescriptor"),
    ("vools/functional/placeholder_impl.py", "SubscriptExecutor"),
    # oop
    ("vools/oop/calltype.py", "TestClass"),
    ("vools/oop/calltype.py", "CallableInstance"),
    ("vools/oop/fusion.py", "ClassFusion"),
    ("vools/oop/mixer.py", "Mixer_"),
    # security
    ("vools/security/safe_eval.py", "SafeExpressionEvaluator"),
    # serialize
    ("vools/serialize/backends/base.py", "BaseBackend"),
    ("vools/serialize/backends/json_backend.py", "JsonBackend"),
    ("vools/serialize/backends/msgpack_backend.py", "MsgpackBackend"),
    ("vools/serialize/backends/pickle_backend.py", "PickleBackend"),
    ("vools/serialize/callable/__init__.py", "CallableHandler"),
    ("vools/serialize/callable/decorator_handler.py", "DecoratorHandler"),
    ("vools/serialize/callable/functional_handler.py", "FunctionalHandler"),
    ("vools/serialize/core.py", "Serializer"),
    # task
    ("vools/task/core/queue.py", "TaskQueue"),
    ("vools/task/core/storage.py", "TaskStorage"),
    ("vools/task/core/worker.py", "Worker"),
    ("vools/task/core/worker.py", "WorkerPool"),
    ("vools/task/core/worker.py", "ThreadPool"),
    ("vools/task/decorators/task_decorator.py", "TaskDecorator"),
    ("vools/task/rules/dag.py", "DagScheduler"),
    ("vools/task/rules/engine.py", "RuleEngine"),
    ("vools/task/rules/rule.py", "Rule"),
    ("vools/task/rules/rule.py", "RuleSet"),
]

# ── 豁免：必须保留本地 do，且不继承 VoolsBase ────────────────────────────────
EXEMPT = [
    ("vools/cache/once.py", "Singleton"),
    ("vools/core/base.py", "VoolsBase"),
    ("vools/core/exceptions.py", "VoolsError"),
    ("vools/data/vlist.py", "ListLikeMeta"),
    ("vools/data/vtext.py", "VText"),
    ("vools/datetime/dates_format.py", "EnhancedDateFormatter"),
    ("vools/datetime/vdate_class.py", "VDate"),
    ("vools/decorators/curry_core.py", "CurryExecutionError"),
    ("vools/decorators/curry_decorator.py", "CurriedMethod"),
    ("vools/encoding/core.py", "EncoderMeta"),
    ("vools/functional/box.py", "Box"),
    ("vools/functional/placeholder.py", "Magic"),
    ("vools/functional/placeholder_impl.py", "_X"),
    ("vools/functional/placeholder_impl.py", "_Y"),
    ("vools/functional/result.py", "Result"),
    ("vools/oop/mixer.py", "Mixer"),
    ("vools/oop/mixer.py", "attr_Enum"),
    ("vools/security/expression_handler.py", "ExpressionSecurityError"),
    ("vools/security/safe_eval.py", "SafeEvalError"),
    ("vools/utils/hoder.py", "Hoder"),
]

# ── 不同签名（对任意值做副作用），不属于链式 do，天然保留 ───────────────────
DIFFERENT_SIGNATURE = [
    ("vools/functional/__init__.py", "Ops"),
    ("vools/functional/pipe_ops.py", "Ops"),
]

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _class_node(rel_path, cls_name):
    """返回文件内指定类名对应的 AST ClassDef（支持嵌套类与函数内局部类）。"""
    full = os.path.join(REPO_ROOT, rel_path)
    assert os.path.exists(full), f"文件不存在: {rel_path}"
    tree = ast.parse(open(full, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            return node
    raise AssertionError(f"{rel_path} 中找不到类 {cls_name}")


def _is_voolsbase_base(node):
    return any(ast.unparse(b) == "VoolsBase" for b in node.bases)


def _inherits_voolsbase(rel_path, cls_name, _depth=0):
    """类直接或经同文件父类间接继承 VoolsBase。

    Overloads(Selector) 通过 Selector(VoolsBase) 间接获得 do，同样满足契约。
    """
    if _depth > 8:
        return False
    node = _class_node(rel_path, cls_name)
    if _is_voolsbase_base(node):
        return True
    for base in node.bases:
        base_name = ast.unparse(base)
        # 去掉下标/参数化，如 Generic[T, E] -> Generic
        base_name = base_name.split("[")[0].strip()
        if base_name == "VoolsBase":
            return True
        try:
            if _inherits_voolsbase(rel_path, base_name, _depth + 1):
                return True
        except AssertionError:
            # 父类不在同文件（外部模块），无法静态判定，交给运行时用例覆盖
            continue
    return False


def _local_do(node):
    return [f for f in node.body if isinstance(f, ast.FunctionDef) and f.name == "do"]


@pytest.mark.parametrize("rel_path,cls_name", CONVERTED)
def test_converted_class_inherits_voolsbase(rel_path, cls_name):
    assert _inherits_voolsbase(rel_path, cls_name), (
        f"{rel_path}::{cls_name} 应（直接或经父类）继承 VoolsBase")


@pytest.mark.parametrize("rel_path,cls_name", CONVERTED)
def test_converted_class_has_no_local_do(rel_path, cls_name):
    node = _class_node(rel_path, cls_name)
    assert not _local_do(node), (
        f"{rel_path}::{cls_name} 不应再有本地 do（应继承 VoolsBase.do）")


@pytest.mark.parametrize("rel_path,cls_name", EXEMPT)
def test_exempt_class_keeps_local_do(rel_path, cls_name):
    node = _class_node(rel_path, cls_name)
    assert _local_do(node), f"{rel_path}::{cls_name} 属豁免类，应保留本地 do"


@pytest.mark.parametrize("rel_path,cls_name", EXEMPT)
def test_exempt_class_does_not_inherit_voolsbase(rel_path, cls_name):
    node = _class_node(rel_path, cls_name)
    assert not _is_voolsbase_base(node), (
        f"{rel_path}::{cls_name} 属豁免类，不应继承 VoolsBase"
        "（会改变枚举/元类/异常/代理/内置子类的下游语义）")


@pytest.mark.parametrize("rel_path,cls_name", DIFFERENT_SIGNATURE)
def test_different_signature_do_kept(rel_path, cls_name):
    node = _class_node(rel_path, cls_name)
    names = [f.name for f in node.body if isinstance(f, ast.FunctionDef)]
    assert "do" in names, f"{rel_path}::{cls_name}.do(x, func) 是独立 API，应保留"


def test_converted_do_resolves_to_voolsbase():
    """抽检运行时可实例化的类：do 来自 VoolsBase 且链式返回 self。"""
    from vools.task.core.queue import TaskQueue
    from vools.serialize.core import Serializer
    from vools.cache.memorize import TimedCache

    for cls in (TaskQueue, Serializer, TimedCache):
        assert cls.do.__qualname__ == "VoolsBase.do", (
            f"{cls.__name__}.do 应解析到 VoolsBase.do，实际 {cls.do.__qualname__}")
        inst = cls()
        assert inst.do() is inst
        assert inst.do(lambda s: s) is inst


def test_voolsbase_do_signature_unchanged():
    """VoolsBase.do 的签名/默认值必须保持兼容。"""
    import inspect

    sig = inspect.signature(VoolsBase.do)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["self", "f", "pre_f", "sub_f"]
    assert params[1].default is print
    assert params[2].default is None
    assert params[3].default is None
