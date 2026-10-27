"""
VText 文本类
继承自 str，提供链式文本处理方法
"""

__all__ = ['VText', '_VQ_ENC_KEY_DEFAULT']

import fnmatch
import os
import re
import zlib
import base64
import hashlib
from itertools import takewhile
from typing import Any, Optional, Union, Tuple, Dict, List, Callable

from ..decorators import rself
from ..datetime.dates_format import EnhancedDateFormatter
from ..serialize.context import get_protocol
from .vlist import VList

# vicText 加密模块默认密钥（仅兜底用；生产务必用环境变量 VQ_ENC_KEY 独立存放）
_VQ_ENC_KEY_DEFAULT = b"sparksql_exe_2026_share_key_0123456789ab"

# BUG-206: _run 的 exec/eval 使用受限命名空间，挡掉 __import__/open/getattr/
# exec/eval/compile 等 builtins 的**直接**调用。
#
# BUG-362 更正：受限 builtins **不是沙箱** —— `().__class__.__base__.__subclasses__()`
# 仍可沿 MRO 拿到任意已加载类（实测 400+ 个，含 Popen）。因此：
#   * `eval` 路径在求值前追加 AST 守卫（拒绝下划线属性/名称、format 逃逸、import）；
#   * `exec` 路径**无法等价加固**（语句执行），属"显式执行代码"，调用方必须自行
#     保证输入可信——不要在 _run("exec") 上处理不可信文本。
_RUN_SAFE_BUILTINS = {
    'True': True, 'False': False, 'None': None,
    'abs': abs, 'len': len, 'min': min, 'max': max, 'sum': sum, 'round': round,
    'int': int, 'float': float, 'str': str, 'bool': bool,
    'list': list, 'tuple': tuple, 'dict': dict, 'set': set, 'frozenset': frozenset,
    'range': range, 'enumerate': enumerate, 'zip': zip,
    'map': map, 'filter': filter, 'any': any, 'all': all,
    'sorted': sorted, 'reversed': reversed, 'print': print,
}
_RUN_SAFE_NAMESPACE = {'__builtins__': _RUN_SAFE_BUILTINS}


def _validate_run_expression(text: str) -> None:
    """BUG-362: `_run('eval')` 求值前的 AST 校验（复用共享守卫）。"""
    from ..security.expr_guard import ExpressionGuardError, validate_expression
    try:
        validate_expression(text)
    except ExpressionGuardError as exc:
        raise ValueError(f"VText._run 拒绝执行该表达式：{exc}") from None


def _strip_sql_comments(text: str) -> str:
    r"""BUG-358: 字面量感知的 SQL 注释剥离。

    原实现用正则 `--.*?$|/\*.*?\*/` 直接全局删除——**字符串/标识符字面量内**
    的 `--`、`/* */` 也会被当成注释删掉，整条 SQL 被截断：

        SELECT '--x' AS c;          ->  SELECT '            （后半句丢失）
        SELECT '/*y*/' AS c;        ->  SELECT '' AS c;

    这里按字符扫描，跳过单引号/双引号/反引号内的内容（含 '' 与 "" 转义），
    只移除引号外的 `-- 行注释` 与 `/* 块注释 */`。
    """
    out = []
    i = 0
    n = len(text)
    quote = None
    while i < n:
        ch = text[i]
        if quote is not None:
            out.append(ch)
            if ch == quote:
                if i + 1 < n and text[i + 1] == quote:
                    out.append(text[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ("'", '"', '`'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == '-' and i + 1 < n and text[i + 1] == '-':
            j = text.find('\n', i)
            if j == -1:
                break
            i = j
            continue
        if ch == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            if j == -1:
                break
            i = j + 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


@rself
class VText(str):
    """链式文本类，继承自 str"""

    # BUG-220: regexp_substr 文档承诺「无匹配时 None」（Optional[str]），但
    # @rself 的链式兜底会把 None 转成 self(整条原文)、str 转成 VText——
    # `is None` 未命中判断永假，调用方在错误数据上静默继续链式计算。
    # 走 _rself_exclude 官方逃生门（BUG-200 先例：VDate.date()），令其
    # 与底层 vools/utils/tools.regexp_substr 契约一致：命中返回原生 str、
    # 未命中返回 None。
    _rself_exclude = ('regexp_substr',)

    def __new__(cls, text: str = "", *args: Any, **kwargs: Any) -> 'VText':
        """创建新的 VText 实例。

        Args:
            text: 初始文本内容
            *args: 传递给父类的额外位置参数
            **kwargs: 传递给父类的额外关键字参数

        Returns:
            新的 VText 实例
        """
        return super().__new__(cls, text)

    def __init__(self, text: str = "", *args: Any, **kwargs: Any) -> None:
        """初始化 VText 实例。

        Args:
            text: 初始文本内容
            *args: 预留位置参数
            **kwargs: 预留关键字参数
        """
        pass

    @property
    def text(self) -> 'VText':
        """返回自身文本。

        legacy vicText.text 兼容：新 vools 里 VText 继承 str，字符串内容即文本，
        此处补一个 .text 属性让 `get_content(path).text` 这类旧写法继续可用。
        """
        return self

    def do(
        self,
        f: Callable[..., Any] = print,
        pre_f: Optional[Callable[['VText'], 'VText']] = None,
        sub_f: Optional[Callable[[Any], None]] = None
    ) -> 'VText':
        """执行副作用操作，返回自身以支持链式调用。

        Args:
            f: 要执行的函数（默认 print）
            pre_f: 在 f 执行前执行的预处理函数
            sub_f: 在 f 执行后执行的后处理函数（无返回值要求）

        Returns:
            self，自身引用以支持链式调用
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self

    @staticmethod
    def _safe_path(file_path: str, base_dir: Optional[str] = None) -> str:
        """安全路径解析，防止路径遍历攻击。

        Args:
            file_path: 文件路径（可以是 file:// URI 格式）
            base_dir: 基础目录，默认为当前工作目录

        Returns:
            规范化后的绝对路径

        Raises:
            ValueError: 当路径试图访问 base_dir 之外的文件时抛出
        """
        if base_dir is None:
            base_dir = os.getcwd()

        base_dir = os.path.abspath(base_dir)

        if file_path.startswith(r'file://'):
            file_path = file_path[7:]

        # 显式绝对路径直通：调用方明确给出绝对路径时，
        # 不应被 cwd 限制。base_dir 检查仅约束相对路径（防 ../ 遍历）。
        if os.path.isabs(file_path):
            return os.path.normpath(file_path)

        abs_path = os.path.abspath(os.path.join(base_dir, file_path))
        normalized = os.path.normpath(abs_path)

        try:
            common = os.path.commonpath([normalized, base_dir])
            if common != base_dir and common != normalized:
                raise ValueError(f"不允许访问指定路径之外的文件: {file_path}")
        except ValueError:
            # 不同盘符（Windows）或 commonpath 解析失败
            raise ValueError(f"不允许访问指定路径之外的文件: {file_path}")

        return normalized

    def write(self, file_path: str = "output.sql", mode: str = 'w') -> None:
        """将文本内容写入文件。

        Args:
            file_path: 文件路径（支持 file:// URI 格式）
            mode: 写入模式，默认 'w'（覆盖写入），可设为 'a'（追加写入）

        Raises:
            ValueError: 当路径试图访问指定目录之外时抛出
            OSError: 当目录创建或文件写入失败时抛出
        """
        safe_path = self._safe_path(file_path)

        parent_dir = os.path.dirname(safe_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(safe_path, mode, encoding="utf-8") as f:
            f.write(str(self))

    def regexp_split(self, pattern: str, flags: int = 0, rep: str = '★') -> 'VText':
        """使用正则表达式分割文本并替换。

        Args:
            pattern: 正则表达式模式
            flags: 正则表达式标志位（默认 0）
            rep: 替换字符串（默认 '★'），用于标记分割位置

        Returns:
            分割替换后的 VText
        """
        from ..utils.tools import regexp_split as _regexp_split
        return _regexp_split(pattern=pattern, source_string=str(self), flags=flags, rep=rep)

    @staticmethod
    def get_content_fromfile(file_path: str = "input.sql", to_text: bool = True) -> Union[str, List[str]]:
        """从文件读取内容。

        Args:
            file_path: 文件路径（支持 file:// URI 格式）
            to_text: 为 True 时返回字符串，为 False 时返回行列表

        Returns:
            文件内容（字符串或行列表）

        Raises:
            ValueError: 当路径试图访问指定目录之外时抛出
            OSError: 当文件读取失败时抛出
        """
        safe_path = VText._safe_path(file_path)

        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read() if to_text else f.readlines()

    def formatEx(self, **kwargs: Any) -> str:
        """使用 EnhancedDateFormatter 格式化文本。

        支持日期时间格式化等扩展格式选项。

        Args:
            **kwargs: 格式化参数，传递给 EnhancedDateFormatter

        Returns:
            格式化后的字符串
        """
        formatter = EnhancedDateFormatter(str(self)).set(**kwargs)
        return formatter.format()

    # ─── legacy vicText 通用文本能力（对齐 vools.py 大文件） ───

    def trim(self, chars: Optional[str] = None, left: bool = True, right: bool = True) -> 'VText':
        """按侧裁剪空白/指定字符（legacy ``vicText.trim``）。

        Args:
            chars: 要裁剪的字符集合；None 表示空白
            left: 是否裁剪左侧
            right: 是否裁剪右侧

        Returns:
            裁剪后的 VText
        """
        from ..utils.tools import trim as _trim
        return self.__class__(_trim(str(self), chars, left, right))

    def regexp_findall(self, pattern: str, flags: int = 0) -> List[str]:
        """正则查找全部匹配（legacy ``vicText.regexp_findall``）。

        Args:
            pattern: 正则表达式
            flags: 正则标志位

        Returns:
            匹配列表
        """
        from ..utils.tools import regexp_findall as _f
        return _f(pattern, str(self), flags)

    def regexp_replace(self, pattern: str, replacement: str, flags: int = 0, count: int = 0) -> 'VText':
        """正则替换（legacy ``vicText.regexp_replace``）。

        Args:
            pattern: 正则表达式
            replacement: 替换文本
            flags: 正则标志位
            count: 最大替换次数，0 表示全部

        Returns:
            替换后的 VText
        """
        from ..utils.tools import regexp_replace as _f
        return self.__class__(_f(pattern, str(self), replacement, flags, count))

    def regexp_like(self, pattern: str, flags: int = 0, complete_matching: bool = True) -> bool:
        """正则匹配判定（legacy ``vicText.regexp_like``）。

        Args:
            pattern: 正则表达式
            flags: 正则标志位
            complete_matching: True 时要求整串匹配

        Returns:
            是否匹配
        """
        from ..utils.tools import regexp_like as _f
        return _f(pattern, str(self), flags, complete_matching)

    def regexp_substr(self, pattern: str, flags: int = 0, occurrence: int = 0) -> Optional[str]:
        """取第 occurrence 个匹配子串（legacy ``vicText.regexp_substr``）。

        Args:
            pattern: 正则表达式
            flags: 正则标志位
            occurrence: 第几个匹配（0 起）

        Returns:
            匹配子串（原生 str），无匹配时 None。
            BUG-220: 本方法在 ``_rself_exclude`` 中声明——不走 @rself 的
            None→self 链式兜底，保证「无匹配=None」契约真实可判。

        Example:
            >>> VText("abc123").regexp_substr(r'\\d+')
            '123'
            >>> VText("abc123").regexp_substr(r'xyz') is None
            True
        """
        from ..utils.tools import regexp_substr as _f
        return _f(pattern, str(self), flags, occurrence)

    def regexp_count(self, pattern: str, flags: int = 0) -> int:
        """统计匹配次数（legacy ``vicText.regexp_count``）。"""
        from ..utils.tools import regexp_count as _f
        return _f(pattern, str(self), flags)

    def regexp_instr(self, pattern: str, flags: int = 0, occurrence: int = 0) -> int:
        """返回第 occurrence 个匹配的位置（legacy ``vicText.regexp_instr``）。"""
        from ..utils.tools import regexp_instr as _f
        return _f(pattern, str(self), flags, occurrence)

    def splitEx(self, separator: str, rep: str = '★') -> List[str]:
        """扩展分割：保留分隔符信息（legacy ``vicText.splitEx``）。

        Args:
            separator: 分隔符
            rep: 分隔符占位字符

        Returns:
            分割后的列表
        """
        from ..utils.tools import split as _split
        temp = _split(str(self), separator, rep)
        return [] if temp is None else temp

    def like(self, pattern: str, ignorecase: bool = True) -> bool:
        """通配符匹配，支持 ``*`` / ``?``（legacy ``vicText.like``）。

        Args:
            pattern: 通配符模式
            ignorecase: 是否忽略大小写

        Returns:
            是否匹配

        Notes:
            这里用 ``fnmatch.fnmatchcase`` 而非 ``fnmatch.fnmatch``：后者在
            Windows 上会经 ``os.path.normcase`` 强制忽略大小写，导致
            ``ignorecase=False`` 在 Windows 上形同虚设（legacy 即有此问题）。
            统一大小写后走 fnmatchcase，使 ignorecase 在所有平台都真正生效。
        """
        # BUG-342: pattern 零校验——like(None)/like(123) 抛裸
        # "AttributeError: 'NoneType' object has no attribute 'lower'"
        if not isinstance(pattern, str):
            raise TypeError(
                f"like() 的 pattern 必须是字符串（支持 * / ? 通配符），收到 "
                f"{type(pattern).__name__}: {pattern!r}")
        txt = str(self)
        if ignorecase:
            txt, pattern = txt.lower(), pattern.lower()
        return fnmatch.fnmatchcase(txt, pattern)

    def build(self, dct: Optional[Dict[Any, Any]] = None, lst: Optional[List[Any]] = None,
              sep: str = "\n ,", check_key: str = "item", max_iter_num: int = 999,
              prefix: str = "", suffix: str = "") -> 'VText':
        """把 dict/list 递归拼进模板文本（legacy ``vicText.build``）。

        Args:
            dct: 字典数据
            lst: 列表数据
            sep: 连接分隔符
            check_key: 递归查找的键名
            max_iter_num: 最大递归层数
            prefix: 结果前缀
            suffix: 结果后缀

        Returns:
            构建出的 VText
        """
        from ..utils.tools import build_text as _build_text
        txt = prefix + _build_text(str(self), dct, lst, sep, check_key, max_iter_num) + suffix
        return self.__class__(txt)

    def discard_comments(self) -> 'VText':
        """去掉 SQL 注释并丢弃空行（legacy ``vicText.discard_comments``）。

        Returns:
            去注释后的 VText
        """
        ss = _strip_sql_comments(str(self))
        result = [line for line in ss.split('\n') if line.strip()]
        return self.__class__("\n".join(result))

    def move_trailing_commas(self, discard_comment: bool = True) -> 'VText':
        """把行尾逗号移到下一行行首（legacy ``vicText.move_trailing_commas``）。

        Args:
            discard_comment: 是否先丢弃注释

        Returns:
            处理后的 VText
        """
        txt = self.discard_comments() if discard_comment else self.__class__(str(self))
        arr = str(txt).split('\n')
        patt1 = re.compile(r',\s*\t*(--.*)?$')
        patt3 = re.compile(r'^\s*\t*(--.*)?$')
        patt11 = re.compile(r',\s*\t*(--.*?$|/\*.*?\*/)', re.MULTILINE | re.DOTALL)
        patt411 = re.compile(r'(.*),(\s*\t*(--.*?$|/\*.*?\*/))', re.MULTILINE | re.DOTALL)
        patt4 = re.compile(r'(.*),(\s*\t*(--.*)?)$')

        result = []
        p = False
        for line in arr:
            if patt3.search(line):
                result.append(line)
            else:
                if p:
                    s = "".join(takewhile(lambda x: x in [' ', '\t'], line)) + ","
                    line = s + line.lstrip()
                    p = False
                if patt1.search(line):
                    result.append(re.sub(patt4, r'\1\2', line))
                    p = True
                elif patt11.search(line):
                    result.append(re.sub(patt411, r'\1\2', line))
                    p = True
                else:
                    result.append(line)
        else:
            if p:
                result.append(",")
        return self.__class__('\n'.join(result))

    # ─── legacy vicText._run / run / result ───

    def _run(self, func: Any = None) -> Any:
        """执行文本内容（legacy ``vicText._run``）。

        Args:
            func: 可调用对象，或 "exec" / "eval" / "spark.sql" 字符串；
                默认 None（不执行）。原默认 exec 会无参触发任意代码执行（BUG-206）。

        Returns:
            执行结果；空文本返回 None；func 未指定时 raise ValueError
        """
        text = str(self)
        if text.strip() == "":
            return None
        if func is None:
            raise ValueError(
                "func 未指定：请显式传入可调用对象或 'exec'/'eval'/'spark.sql'"
                "（vools.data.vtext 不再允许无参 _run() 执行任意代码）"
            )
        if callable(func):
            # BUG-206: exec 必须用受限命名空间，杜绝 __import__/open 等任意代码执行
            if func is exec:
                return exec(text, _RUN_SAFE_NAMESPACE)
            if func is eval:
                # BUG-362: 受限 builtins 挡不住 MRO 逃逸，表达式先过 AST 守卫
                _validate_run_expression(text)
                return eval(text, _RUN_SAFE_NAMESPACE)
            return func(text)
        if isinstance(func, str):
            lowered = func.lower()
            if lowered == "exec":
                return exec(text, _RUN_SAFE_NAMESPACE)
            if lowered == "eval":
                # BUG-362: 同 func is eval —— AST 守卫后再求值
                _validate_run_expression(text)
                return eval(text, _RUN_SAFE_NAMESPACE)
            if lowered == "spark.sql":
                # BUG-170: 原 `from .core import get_spark` 指向不存在的 vools.data.core。
                # spark 能力挂在 vools 顶层 my_spark()；环境未提供 SparkSession 时抛清晰 RuntimeError。
                try:
                    from .. import my_spark
                    spk = my_spark()
                except (ImportError, ModuleNotFoundError) as e:
                    raise RuntimeError(
                        f"spark.sql 需要 Spark 环境（vools.pyk 未提供），当前不可用: {e}"
                    ) from e
                if spk is None:
                    raise RuntimeError(
                        "spark.sql 需要 SparkSession，请先通过 vools.my_spark(spark_session) 注入"
                    )
                return spk.sql(text)
            from ..utils.tools import generate_lambda as _vf
            return _vf(func)(text)
        return None

    def run(self, func: Any = print) -> Any:
        """执行并把结果记到 ``.result``（legacy ``vicText.run``）。

        Args:
            func: 同 :meth:`_run`

        Returns:
            结果为空时返回自身；结果为字符串时返回 VText；否则返回原结果
        """
        result = self._run(func)
        self._result = result
        if result is None:
            return self
        if isinstance(result, str):
            return self.__class__(result)
        return result

    @property
    def result(self) -> Any:
        """最近一次 :meth:`run` 的结果（legacy ``vicText.result``）。"""
        return getattr(self, '_result', None)

    @result.setter
    def result(self, value: Any) -> None:
        raise ValueError("result属性只能被run函数执行设置！！！")

    # ─── 序列化支持 ───

    def __getnewargs__(self) -> Tuple[str]:
        """返回序列化时用于重建实例的参数。

        Returns:
            包含字符串值的元组
        """
        return (str(self),)

    def __getstate__(self) -> Dict[str, str]:
        """获取序列化状态。

        Returns:
            包含字符串值的字典
        """
        return {}

    def __setstate__(self, state: Dict[str, str]) -> None:
        """设置序列化状态。

        Args:
            state: 序列化状态字典
        """
        pass

    def strip_margin(self, **kwargs: Any) -> 'VText':
        """对每行进行掐头处理，移除边距标记。

        处理规则：
            1. 行以 ``\\s*|`` 开头 → 移除前缀，保留后面内容
            2. 行以 ``\\s*#|`` 开头 → 整行丢弃（注释）
            3. 行以 ``\\s*\\$|`` 开头 → 移除前缀，并且对后面内容使用 ``formatEx(**kwargs)`` 多次格式化
            4. 行以 ``\\s*\\$\\d+|`` 开头 → 同规则3，且 ``\\d+`` 表示前面添加 n 个空格缩进
            5. 不以上述开头 → 保持原样

        Args:
            **kwargs: 格式化参数，传递给 ``formatEx`` 用于变量替换

        Returns:
            VText: 处理后的新 VText 实例
        """
        lines = str(self).splitlines()
        result_lines = []
        pattern_dollar_indent = re.compile(r'^\s*\$(\d+)\|')
        pattern_dollar_pipe = re.compile(r'^\s*\$\|')
        pattern_hash_pipe = re.compile(r'^\s*#\|')
        pattern_pipe = re.compile(r'^\s*\|')

        # 对 $| 或 $\d+| 后的内容执行多次 formatEx 直到收敛
        def _format_until_stable(text: str) -> str:
            # BUG-301: 原 `while True` 无迭代上限——变量互相引用时
            # （a="{b}"、b="{a}"）formatEx 每轮在两种文本间振荡、永不相等，
            # 进程永久挂死且无任何错误提示。加迭代上限并显式报错。
            prev = self.__class__(text)
            for _ in range(100):
                current = prev.formatEx(**kwargs)
                if current == prev:
                    return prev
                prev = current
            raise ValueError(
                f"strip_margin: 格式化在 100 轮内未收敛，可能存在变量循环引用"
                f"（检查传入的 kwargs 是否互相引用）。起始文本: {text[:80]!r}"
            )

        for line in lines:
            m = pattern_dollar_indent.match(line)
            if m:
                # 规则4: $\d+| 开头，掐头 + n 空格缩进 + 多次 formatEx
                indent = int(m.group(1))
                stripped = line[m.end():]
                formatted = _format_until_stable(stripped)
                result_lines.append(' ' * indent + formatted)
            elif pattern_dollar_pipe.match(line):
                # 规则3: \$| 开头，掐头 + 多次 formatEx
                stripped = pattern_dollar_pipe.sub('', line)
                result_lines.append(_format_until_stable(stripped))
            elif pattern_hash_pipe.match(line):
                # 规则2: #| 开头，整行丢弃
                continue
            elif pattern_pipe.match(line):
                # 规则1: | 开头，仅掐头
                stripped = pattern_pipe.sub('', line)
                result_lines.append(stripped)
            else:
                # 规则5: 不匹配，原样返回
                result_lines.append(line)

        return '\n'.join(result_lines) # 返回新的实例，有 rself 兜底

    # ============================================================
    # toZipB64 / unZipB64 : 文本 ↔ zip压缩 → base64 (payload 压缩通道)
    # 设计:
    #   编码结果带前缀标记, 便于区分压缩/未压缩, 避免解压失败误判旧数据
    #   "Z:" + base64(zlib(data))   压缩
    #   "R:" + base64(data)         未压缩(压缩膨胀时兜底)
    #   无前缀                       旧明文/旧压缩 (unZipB64 兼容回退)
    # 均返回 VText, 保持链式风格 (rself 自动包装)
    # ============================================================
    @staticmethod
    def _b64enc(data: bytes, urlsafe: bool) -> str:
        """bytes → base64 str"""
        fn = base64.urlsafe_b64encode if urlsafe else base64.b64encode
        return fn(data).decode("ascii")

    @staticmethod
    def _b64dec(s: str, urlsafe: bool) -> bytes:
        """base64 str → bytes, 宽容解析。
        注意: base64.urlsafe_b64decode(s) 只接受 s 参数, 不接受 validate;
        必须用 base64.b64decode(s, altchars=b'-_', validate=False) 兼容两者。
        """
        raw = s.encode("ascii")
        if urlsafe:
            return base64.b64decode(raw, altchars=b"-_", validate=False)
        return base64.b64decode(raw, validate=False)

    @staticmethod
    def _zlib_decompress(data: bytes, max_length: int) -> bytes:
        """zlib 解压，带 max_length 防解压炸弹。
        注意: 模块级 zlib.decompress() 不支持 max_length，
        必须用 decompressobj().decompress(data, max_length)。
        """
        dobj = zlib.decompressobj()
        raw = dobj.decompress(data, max_length)
        if not dobj.eof:
            raise ValueError("解压数据超过 max_length 限制")
        raw += dobj.flush()
        return raw

    def toZipB64(self, text: Optional[Union[str, 'VText']] = None, level: int = 9,
                 urlsafe: bool = False, force: bool = False) -> 'VText':
        """文本 → zip压缩 → base64。返回 VText。

        参数:
          text     : 待压缩文本; None 则用自身
          level    : zlib 压缩级别 1-9, 默认 9 (最高压缩, 稍慢)
          urlsafe  : True 用 URL-safe base64 (含 -/_)
          force    : True 强制压缩, 不做膨胀判断
        返回:
          VText, 形如 "Z:AAA..." 或 "R:BBB..."
        """
        # BUG-342: level 零校验——level=99 抛 zlib 的
        # "error: Bad compression level"（无参数名）；level='x' 抛裸 TypeError。
        if isinstance(level, bool) or not isinstance(level, int):
            raise TypeError(
                f"toZipB64() 的 level 必须是 1..9 的整数，收到 "
                f"{type(level).__name__}: {level!r}")
        if not 1 <= level <= 9:
            raise ValueError(f"toZipB64() 的 level 必须在 1..9，收到 {level!r}")
        src = text if text is not None else str(self)
        if src is None:
            src = ""
        if isinstance(src, bytes):
            src = src.decode("utf-8")
        src = str(src)
        raw = src.encode("utf-8")
        z = zlib.compress(raw, level)
        z_b64 = self._b64enc(z, urlsafe)
        if not force and len(z_b64) >= len(src):
            # 压缩膨胀，兜底: 直接 base64 原文
            r_b64 = self._b64enc(raw, urlsafe)
            return self.__class__("R:" + r_b64)
        return self.__class__("Z:" + z_b64)

    def unZipB64(self, b64: Optional[str] = None, urlsafe: bool = False,
                 max_length: int = 50 * 1024 * 1024) -> 'VText':
        """base64 → zip解压 → 原文。返回 VText。

        参数:
          b64        : 待解码串; None 则用自身
          urlsafe    : True 用 URL-safe base64
          max_length : zlib 解压上限, 防解压炸弹, 默认 50MB
        返回:
          VText 原文。兼容 Z:/R:/无前缀 (旧数据), 解压失败回退原文/空串。
        """
        s = str(b64) if b64 is not None else str(self)
        if s == "":
            return self.__class__("")
        if s.startswith("Z:"):
            data_b64 = s[2:]
            compressed = True
        elif s.startswith("R:"):
            data_b64 = s[2:]
            compressed = False
        else:
            # 无前缀: 旧数据，先尝试 base64, 再尝试 zip
            data_b64 = s
            compressed = True
        try:
            raw = self._b64dec(data_b64, urlsafe)
        except Exception:
            return self.__class__("")
        if not compressed:
            return self.__class__(raw.decode("utf-8", errors="replace"))
        try:
            data = self._zlib_decompress(raw, max_length)
            return self.__class__(data.decode("utf-8"))
        except Exception:
            try:
                return self.__class__(raw.decode("utf-8", errors="replace"))
            except Exception:
                return self.__class__("")

    # ============================================================
    # encrypt / decrypt : 文本加密/解密 (密码密文化通道)
    # 设计:
    #   结果带前缀标记, 便于运行时区分算法:
    #   "E:" + base64(xor(data,key))          XOR 可逆流密码 (stdlib, 默认)
    #   "F:" + fernet(base64(data))            Fernet AES128-CBC+HMAC (cryptography 可用时)
    #   "A:" + base64(aes_gcm(base64(data)))   AES-GCM (cryptography 可用时)
    # 返回 VText, 保持链式风格; 与 toZipB64/unZipB64 同层级, 可组合使用。
    # 注意: XOR 是"混淆"而非"加密", 只用于防止明文被肉眼/日志直读。
    #       真正需要强加密时, 传入 way="fernet" / "aes" 并要求 cryptography 已安装。
    # ============================================================
    @staticmethod
    def _resolve_key(key: Optional[Union[bytes, str]] = None) -> bytes:
        """密钥解析优先级: 显式 key > 环境变量 VQ_ENC_KEY > 内建默认。
        默认密钥仅作兜底, 生产环境务必用 VQ_ENC_KEY 独立存放。
        """
        if key is not None and key != "":
            k = key
        else:
            k = os.environ.get("VQ_ENC_KEY", "")
            if not k:
                k = _VQ_ENC_KEY_DEFAULT
        if isinstance(k, str):
            k = k.encode("utf-8")
        return k

    @staticmethod
    def _xor_crypt(data: bytes, key: bytes) -> bytes:
        """XOR 可逆流密码: data[i] ^ key[i % len(key)]。"""
        if not key:
            raise ValueError("XOR 加密密钥为空")
        kl = len(key)
        return bytes(b ^ key[i % kl] for i, b in enumerate(data))

    def encrypt(self, way: Optional[str] = None,
                key: Optional[Union[bytes, str]] = None) -> 'VText':
        """明文 → 密文串 (带前缀)。返回 VText。

        参数:
          way : None/"xor"(默认) | "fernet" | "aes"
          key : 加密密钥 bytes 或 str; None 用环境变量 VQ_ENC_KEY, 再退到内建默认。
        返回:
          VText, 形如 "E:AAA..." / "F:AAA..." / "A:AAA..."
        """
        src = str(self)
        if src == "":
            return self.__class__("E:")
        raw = src.encode("utf-8")
        way = (way or "xor").lower().strip()
        if way in ("fernet", "aes"):
            return self._encrypt_with_crypto(raw, way, key)
        if way != "xor":
            raise ValueError(f"未知加密方式: {way!r}")
        k = self._resolve_key(key)
        enc = self._xor_crypt(raw, k)
        b64 = self._b64enc(enc, urlsafe=False)
        return self.__class__("E:" + b64)

    def _encrypt_with_crypto(self, raw: bytes, way: str,
                             key: Optional[Union[bytes, str]] = None) -> 'VText':
        """使用 cryptography 库的 encrypt 实现。返回 VText("F:...") 或 VText("A:...")。"""
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.backends import default_backend
        except ImportError as e:
            raise RuntimeError(f"way={way!r} 需要 cryptography 库且已安装, 当前不可用: {e}")

        k = self._resolve_key(key)
        # 密钥派生: PBKDF2 保证任何长度输入都能派生出符合算法要求的密钥
        salt = hashlib.sha256(k).digest()[:16]
        if way == "fernet":
            from cryptography.fernet import Fernet
            fk = base64.urlsafe_b64encode(
                PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                           iterations=200_000, backend=default_backend()).derive(k)
            )
            f = Fernet(fk)
            tok = f.encrypt(raw)
            return self.__class__("F:" + self._b64enc(tok, urlsafe=True))
        if way == "aes":
            dk = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                            iterations=200_000, backend=default_backend()).derive(k)
            nonce = salt[:12]
            cipher = Cipher(algorithms.AES(dk), modes.GCM(nonce), backend=default_backend())
            enc = cipher.encryptor()
            ct = enc.update(raw) + enc.finalize()
            payload = nonce + enc.tag + ct
            return self.__class__("A:" + self._b64enc(payload, urlsafe=True))
        raise ValueError(f"未知加密方式: {way!r}")

    def decrypt(self, way: Optional[str] = None,
                key: Optional[Union[bytes, str]] = None) -> 'VText':
        """密文串 (带前缀) → 明文。返回 VText。

        参数:
          way : None 自动探测前缀 | "xor"/"fernet"/"aes" 强制指定
          key : 解密密钥; None 用 VQ_ENC_KEY 或内建默认
        返回:
          VText 明文; 解密失败回退原文/空串。
        """
        s = str(self).strip()
        if s == "" or s == "E:":
            return self.__class__("")
        way_in = (way or "").lower().strip()
        # BUG-394: 原实现把 `way` 直接和前缀探测混用——密文带前缀（F:/A:/E:）时
        # 前缀优先，**非法 way（如 'des'）被静默忽略**，解出来的结果看起来"成功"。
        # 这里提前校验 way 的取值；解密失败仍按文档回退（但发出可见告警）。
        if way_in and way_in not in ('xor', 'fernet', 'aes'):
            raise ValueError(
                f"未知解密方式: {way!r}；支持 None（自动探测前缀）/ 'xor' / "
                f"'fernet' / 'aes'")
        _had_prefix = True
        if s.startswith("F:"):
            s = s[2:]
            way_eff = "fernet"
        elif s.startswith("A:"):
            s = s[2:]
            way_eff = "aes"
        elif s.startswith("E:"):
            s = s[2:]
            way_eff = "xor"
        else:
            _had_prefix = False
            way_eff = way_in or "xor"
        k = self._resolve_key(key)
        try:
            if way_eff == "fernet":
                return self._decrypt_with_crypto(s, "fernet", k)
            if way_eff == "aes":
                return self._decrypt_with_crypto(s, "aes", k)
            if way_eff != "xor":
                raise ValueError(f"未知解密方式: {way_eff!r}")
            raw = self._b64dec(s, urlsafe=False)
            dec = self._xor_crypt(raw, k)
            return self.__class__(dec.decode("utf-8"))
        except Exception as _exc:
            # BUG-394: 文档写"解密失败回退原文/空串"，但原实现**一律静默返回空串**
            # ——错误密钥/损坏密文与"本来就不是密文"无法区分。现按前缀区分：
            #   * 带前缀（确为密文）→ 回退空串 + RuntimeWarning（可见）；
            #   * 无前缀（本来就不是密文）→ 回退**原文**（文档的另一种回退）。
            if _had_prefix:
                import warnings as _w
                _w.warn(
                    f"VText.decrypt 解密失败（way={way_eff!r}），已回退为空串："
                    f"{type(_exc).__name__}: {_exc}",
                    RuntimeWarning, stacklevel=2)
                return self.__class__("")
            return self.__class__(str(self))

    def _decrypt_with_crypto(self, b64s: str, way: str, key: bytes) -> 'VText':
        """cryptography 解密实现。"""
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.backends import default_backend
        except ImportError as e:
            raise RuntimeError(f"way={way!r} 需要 cryptography 库且已安装, 当前不可用: {e}")

        salt = hashlib.sha256(key).digest()[:16]
        if way == "fernet":
            from cryptography.fernet import Fernet
            fk = base64.urlsafe_b64encode(
                PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                           iterations=200_000, backend=default_backend()).derive(key)
            )
            f = Fernet(fk)
            raw = f.decrypt(self._b64dec(b64s, urlsafe=True))
            return self.__class__(raw.decode("utf-8"))
        if way == "aes":
            dk = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                            iterations=200_000, backend=default_backend()).derive(key)
            payload = self._b64dec(b64s, urlsafe=True)
            nonce = payload[:12]
            tag = payload[12:28]
            ct = payload[28:]
            cipher = Cipher(algorithms.AES(dk), modes.GCM(nonce, tag), backend=default_backend())
            dec = cipher.decryptor()
            raw = dec.update(ct) + dec.finalize()
            return self.__class__(raw.decode("utf-8"))
        raise ValueError(f"未知解密方式: {way!r}")


    def replace_run_date(self, run_date=None):
        """把 SQL 里的 {run_date}, {run_date-1}, {run_date_std+1} 等占位符替换为实际日期。

        兼容 legacy vicText.replace_run_date 的关键用法：
        ``vicText(sql).replace_run_date(ds)``
        返回 VText 字符串（不带 .text 属性，直接 str() 即可）。

        支持的占位符（正则匹配）：
          - {run_date}           → run_date (默认 YYYYMMDD，legacy vicSql 语义)
          - {run_date-N}         → run_date 减 N 天 (同样默认 YYYYMMDD)
          - {run_date+N}         → run_date 加 N 天 (同样默认 YYYYMMDD)
          - {run_date_std}       → run_date 标准化（yyyy-MM-dd）
          - {run_date_std±N}     → 同上加减

        BUG-130: 旧 docstring 声称 {run_date} 默认 yyyy-MM-dd，与实现 (`std=False` → YYYYMMDD) 不符。
        """
        if "{run_date" not in self:
            return self.__class__(self)
        if run_date is None:
            # BUG-170: 原 `from .core import get_run_ds` 指向不存在的 vools.data.core。
            # 未传 run_date 时用当天 YYYYMMDD 兜底，行为与 legacy vicSql 一致。
            import datetime as _dt_now
            run_date = _dt_now.datetime.now().strftime("%Y%m%d")
        # run_date 可能是 VDate / date / str，统一成 yyyy-MM-dd
        # BUG-342: 原实现直接切片——传 'bogus' 会抛
        # "ValueError: invalid literal for int() with base 10: 'bogu'"
        # （被截断的 4 字符，完全看不出是日期参数错了）。
        import datetime as _dt_rd
        if isinstance(run_date, (_dt_rd.date, _dt_rd.datetime)):
            rd = run_date.strftime("%Y-%m-%d")
        else:
            _raw = str(run_date).strip()
            if len(_raw) == 8 and _raw.isdigit():
                rd = "{}-{}-{}".format(_raw[0:4], _raw[4:6], _raw[6:8])
            elif len(_raw) == 10 and _raw[4] == "-" and _raw[7] == "-":
                rd = _raw
            else:
                raise ValueError(
                    f"replace_run_date() 的 run_date 需要 YYYYMMDD / YYYY-MM-DD "
                    f"字符串或 date/datetime，收到 {run_date!r}")
            try:
                _dt_rd.date(int(rd[0:4]), int(rd[5:7]), int(rd[8:10]))
            except ValueError as exc:
                raise ValueError(
                    f"replace_run_date() 的 run_date 不是合法日期：{run_date!r}（{exc}）"
                ) from exc

        import re as _re
        import datetime as _dt

        def _offset(days, std=True):
            d = _dt.date(int(rd[0:4]), int(rd[5:7]), int(rd[8:10])) + _dt.timedelta(days=days)
            if std:
                return d.strftime("%Y-%m-%d")
            return d.strftime("%Y%m%d")

        pattern = _re.compile(r"\{run_date(_std)?([\+|\-][0-9]+)?\}")

        def _repl(m):
            # legacy vicSql 语义：
            #   {run_date}        → 默认 YYYYMMDD
            #   {run_date_std}    → yyyy-MM-dd
            std = bool(m.group(1))
            off = int(m.group(2)) if m.group(2) else 0
            return _offset(off, std=std)

        return self.__class__(pattern.sub(_repl, str(self)))

    # ─── legacy vicText 字符串方法对齐 ───
    # 说明：str 已有同名方法但返回普通 str，这里显式包装回 VText 以便链式调用；
    # 与 legacy ``return vicText(super().xxx())`` 语义保持一致。

    def __repr__(self) -> str:
        """legacy ``vicText.__repr__`` → ``VText(...)``。"""
        return "VText({})".format(str(self))

    def __str__(self) -> str:
        """返回纯 str 内容（legacy ``vicText.__str__``）。"""
        return str.__str__(self)

    def __setitem__(self, key: Any, value: Any) -> None:
        """legacy ``vicText.__setitem__``：str 不可变，与 legacy 一样抛 TypeError。"""
        return super().__setitem__(key, value)

    def __delitem__(self, key: Any) -> None:
        """legacy ``vicText.__delitem__``：str 不可变，与 legacy 一样抛 TypeError。"""
        return super().__delitem__(key)

    def upper(self) -> 'VText':
        """转大写（legacy ``vicText.upper``）。"""
        return self.__class__(str(self).upper())

    def lower(self) -> 'VText':
        """转小写（legacy ``vicText.lower``）。"""
        return self.__class__(str(self).lower())

    def title(self) -> 'VText':
        """标题化（legacy ``vicText.title``）。"""
        return self.__class__(str(self).title())

    def capitalize(self) -> 'VText':
        """首字母大写（legacy ``vicText.capitalize``）。"""
        return self.__class__(str(self).capitalize())

    def swapcase(self) -> 'VText':
        """大小写互换（legacy ``vicText.swapcase``）。"""
        return self.__class__(str(self).swapcase())

    def replace(self, old: str, new: str, count: Optional[int] = None) -> 'VText':
        """替换子串（legacy ``vicText.replace``）。"""
        if count is None:
            return self.__class__(str(self).replace(old, new))
        return self.__class__(str(self).replace(old, new, count))

    def split(self, sep: Optional[str] = None, maxsplit: int = -1) -> List[str]:
        """按分隔符分割（legacy ``vicText.split``）。"""
        if sep is None:
            return str(self).split()
        return str(self).split(sep, maxsplit)

    def rsplit(self, sep: Optional[str] = None, maxsplit: int = -1) -> List[str]:
        """从右分割（legacy ``vicText.rsplit``）。"""
        if sep is None:
            return str(self).rsplit()
        return str(self).rsplit(sep, maxsplit)

    def splitlines(self, keepends: bool = False) -> 'VList':
        """按行分割（legacy ``vicText.splitlines`` → vicList）。"""
        from ..data.vlist import VList
        return VList(str(self).splitlines(keepends))

    def partition(self, sep: str) -> 'VList':
        """三分割（legacy ``vicText.partition`` → vicList）。"""
        from ..data.vlist import VList
        return VList([self.__class__(s) for s in str(self).partition(sep)])

    def rpartition(self, sep: str) -> 'VList':
        """三分割从右（legacy ``vicText.rpartition`` → vicList）。"""
        from ..data.vlist import VList
        return VList([self.__class__(s) for s in str(self).rpartition(sep)])

    def strip(self, chars: Optional[str] = None) -> 'VText':
        """去首尾空白/字符（legacy ``vicText.strip``）。"""
        if chars is None:
            return self.__class__(str(self).strip())
        return self.__class__(str(self).strip(chars))

    def lstrip(self, chars: Optional[str] = None) -> 'VText':
        """去左侧空白/字符（legacy ``vicText.lstrip``）。"""
        if chars is None:
            return self.__class__(str(self).lstrip())
        return self.__class__(str(self).lstrip(chars))

    def rstrip(self, chars: Optional[str] = None) -> 'VText':
        """去右侧空白/字符（legacy ``vicText.rstrip``）。"""
        if chars is None:
            return self.__class__(str(self).rstrip())
        return self.__class__(str(self).rstrip(chars))

    def zfill(self, width: int) -> 'VText':
        """左补零到指定宽度（legacy ``vicText.zfill``）。"""
        return self.__class__(str(self).zfill(width))

    def center(self, width: int, fillchar: Optional[str] = None) -> 'VText':
        """居中（legacy ``vicText.center``）。"""
        if fillchar is None:
            return self.__class__(str(self).center(width))
        return self.__class__(str(self).center(width, fillchar))

    def ljust(self, width: int, fillchar: Optional[str] = None) -> 'VText':
        """左对齐（legacy ``vicText.ljust``）。"""
        if fillchar is None:
            return self.__class__(str(self).ljust(width))
        return self.__class__(str(self).ljust(width, fillchar))

    def rjust(self, width: int, fillchar: Optional[str] = None) -> 'VText':
        """右对齐（legacy ``vicText.rjust``）。"""
        if fillchar is None:
            return self.__class__(str(self).rjust(width))
        return self.__class__(str(self).rjust(width, fillchar))

    def expandtabs(self, tabsize: int = 8) -> 'VText':
        """扩展 Tab（legacy ``vicText.expandtabs``）。"""
        return self.__class__(str(self).expandtabs(tabsize))

    def translate(self, table: Any) -> 'VText':
        """翻译字符（legacy ``vicText.translate``）。"""
        return self.__class__(str(self).translate(table))

    def join(self, iterable: Any) -> 'VText':
        """以自身为分隔符连接序列（legacy ``vicText.join``）。"""
        return self.__class__(str(self).join(iterable))

    def format(self, *args: Any, **kwargs: Any) -> 'VText':
        """字符串格式化（legacy ``vicText.format``）。"""
        return self.__class__(str(self).format(*args, **kwargs))

    # ─── legacy vicText 运算符/迭代覆写 ───
    # 说明：str 自带这些魔法方法但返回普通 str，而 @rself 明确不包装魔法方法，
    # 因此不覆写就会在 `VText("a") + "b"` 这类链式用法上丢失 VText 类型。
    # 注意：不实现 __setitem__/__delitem__ —— str 不可变，legacy 里那两处
    # 调用 super().__setitem__ 必然抛 TypeError，属死代码。

    def __add__(self, other: Any) -> 'VText':
        """字符串拼接，返回 VText（legacy ``vicText.__add__``）。"""
        if isinstance(other, str):
            txt = other
        else:
            raise TypeError('argument `other` is invalided type ')
        return self.__class__(str(self) + txt)

    def __radd__(self, other: Any) -> 'VText':
        """右向拼接，返回 VText（legacy ``vicText.__radd__``）。"""
        if isinstance(other, str):
            txt = other
        else:
            raise TypeError('argument `other` is invalided type ')
        return self.__class__(txt + str(self))

    def __sub__(self, other: Any) -> 'VText':
        """删除匹配的子串（legacy ``vicText.__sub__`` 等价于正则替换为空）。"""
        return self.__class__(self.regexp_replace(str(other), ''))

    def __mul__(self, n: int) -> 'VText':
        return self.__class__(str(self) * n)

    def __rmul__(self, n: int) -> 'VText':
        return self.__class__(n * str(self))

    def __mod__(self, other: Any) -> 'VText':
        return self.__class__(str(self) % other)

    def __rmod__(self, other: Any) -> 'VText':
        return self.__class__(other % str(self))

    def __getitem__(self, key: Any) -> 'VText':
        return self.__class__(str.__getitem__(self, key))

    def __iter__(self):
        return (self.__class__(s) for s in str.__iter__(self))

    def __reversed__(self):
        return (self.__class__(s) for s in reversed(str(self)))

    def __call__(self, func: Callable[..., Any] = print, *args: Any, **kwargs: Any) -> Any:
        """把自身当参数调用 func（legacy ``vicText.__call__``）。"""
        return func(self, *args, **kwargs)
