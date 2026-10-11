"""
VText 文本类
继承自 str，提供链式文本处理方法
"""

__all__ = ['VText', '_VQ_ENC_KEY_DEFAULT']

import os
import re
import zlib
import base64
import hashlib
from typing import Any, Optional, Union, Tuple, Dict, List, Callable

from ..decorators import rself
from ..datetime.dates_format import EnhancedDateFormatter
from ..serialize.context import get_protocol

# vicText 加密模块默认密钥（仅兜底用；生产务必用环境变量 VQ_ENC_KEY 独立存放）
_VQ_ENC_KEY_DEFAULT = b"sparksql_exe_2026_share_key_0123456789ab"


@rself
class VText(str):
    """链式文本类，继承自 str"""

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

        if not normalized.startswith(base_dir):
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
            prev = self.__class__(text)
            while True:
                current = prev.formatEx(**kwargs)
                if current == prev:
                    break
                prev = current
            return prev

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
        except Exception:
            return self.__class__("")

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
          - {run_date}           → run_date (默认 yyyy-MM-dd)
          - {run_date-N}         → run_date 减 N 天
          - {run_date+N}         → run_date 加 N 天
          - {run_date_std}       → run_date 标准化（yyyy-MM-dd）
          - {run_date_std±N}     → 同上加减
        """
        if "{run_date" not in self:
            return self.__class__(self)
        if run_date is None:
            from .core import get_run_ds
            run_date = get_run_ds()
        # run_date 可能是 VDate 或 str，统一成 yyyy-MM-dd
        rd = str(run_date)
        if len(rd) == 8:
            rd = "{}-{}-{}".format(rd[0:4], rd[4:6], rd[6:8])

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
