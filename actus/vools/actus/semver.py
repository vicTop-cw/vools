"""Semantic Versioning helpers for actus.

[boundary] 边界审视叶 owner: semver.parse —— 对空输入/非法格式/极值/资源极限逐项处理：
- 空串/None -> ValueError（声明不适用：不静默返回 None）
- 非法格式（非数字段、多余段、前缀异常）-> ValueError
- 极值：超大数字段 -> 直接按 int 比较，不溢出
- 预发布/构建元数据：parse 保留 pre/build 原样，compare 时按 SemVer 规范参与排序

Usage:
    >>> parse("1.2.3-rc.1+build.5").major
    1
    >>> compare("1.0.0-alpha", "1.0.0")
    -1
    >>> bump("1.2.3", "minor")
    '1.3.0'

> 2026-10-13（docs/39 §9 / docs/45 S2）：本模块从 `engine/actuscore/semver.py`
> 上移到 vools 成为单一真源，Actus 侧改为 re-export shim。
> 只依赖标准库，没有反向依赖 Actus，所以能安全上移。
"""

from __future__ import annotations

import re
from typing import NamedTuple

_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class SemVer(NamedTuple):
    """Parsed semantic version.

    >>> SemVer(1, 2, 3, ("rc", "1"), "build.5").pre
    ('rc', '1')
    """

    major: int
    minor: int
    patch: int
    pre: tuple[str, ...]
    build: str | None


def parse(version: str) -> SemVer:
    """Parse a semantic version string into a SemVer NamedTuple.

    >>> parse("1.2.3")
    SemVer(major=1, minor=2, patch=3, pre=(), build=None)
    >>> parse("10.20.30-alpha.1").pre
    ('alpha', '1')
    >>> parse("1.2.3+build.5").build
    'build.5'

    Raises ValueError on invalid input:
    >>> parse("v1.2.3")
    Traceback (most recent call last):
        ...
    ValueError: invalid semver: 'v1.2.3'
    >>> parse(" 1.2.3")  # 空白不做静默容忍
    Traceback (most recent call last):
        ...
    ValueError: invalid semver: ' 1.2.3'
    >>> parse("1.0.0-alpha.01")  # 纯数字 pre 标识符禁止前导零
    Traceback (most recent call last):
        ...
    ValueError: invalid semver: '1.0.0-alpha.01'
    """
    if not isinstance(version, str) or not version or version != version.strip():
        raise ValueError(f"invalid semver: {version!r}")
    m = _SEMVER_RE.match(version)
    if m is None:
        raise ValueError(f"invalid semver: {version!r}")
    major = int(m.group("major"))
    minor = int(m.group("minor"))
    patch = int(m.group("patch"))
    pre = m.group("pre")
    build = m.group("build")
    pre_idents: tuple = tuple(pre.split(".")) if pre else ()
    for ident in pre_idents:
        if ident.isdigit() and len(ident) > 1 and ident.startswith("0"):
            raise ValueError(f"invalid semver: {version!r}")
    return SemVer(major, minor, patch, pre_idents, build)


def compare(a: str, b: str) -> int:
    """Compare two semver strings. Returns -1/0/1 (a < b / a == b / a > b).

    Implements SemVer precedence: major.minor.patch numeric order, then
    pre-release identifiers (numeric identifiers lower than alphanumeric,
    fewer identifiers lower than more). Build metadata ignored for precedence.

    >>> compare("1.0.0", "1.0.1")
    -1
    >>> compare("2.0.0", "1.9.9")
    1
    >>> compare("1.0.0-alpha.1", "1.0.0-alpha.1.2")
    -1
    >>> compare("1.0.0-alpha.a", "1.0.0-alpha.1")
    1
    >>> compare("1.0.0-alpha", "1.0.0-alpha.0")
    -1
    """
    pa, pb = parse(a), parse(b)
    for ca, cb in zip(pa[:3], pb[:3]):
        if ca != cb:
            return -1 if ca < cb else 1
    pre_a, pre_b = pa.pre, pb.pre
    if pre_a == pre_b:
        return 0
    if not pre_a:
        return 1
    if not pre_b:
        return -1
    for ia, ib in zip(pre_a, pre_b):
        if ia == ib:
            continue
        a_num, b_num = ia.isdigit(), ib.isdigit()
        if a_num and b_num:
            return -1 if int(ia) < int(ib) else 1
        if a_num:
            return -1  # numeric identifiers always lower than alphanumeric
        if b_num:
            return 1
        return -1 if ia < ib else 1
    return -1 if len(pre_a) < len(pre_b) else 1


def bump(version: str, part: str = "patch") -> str:
    """Increment a semver version's major/minor/patch component.

    >>> bump("1.2.3", "patch")
    '1.2.4'
    >>> bump("1.2.3", "minor")
    '1.3.0'
    >>> bump("1.2.3", "major")
    '2.0.0'
    >>> bump("1.2.3-rc.1+build.5", "patch")
    '1.2.4'

    Pre-release/build are dropped on bump.
    """
    if part not in ("major", "minor", "patch"):
        raise ValueError(f"unsupported part: {part!r}")
    major, minor, patch, _pre, _build = parse(version)
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


__all__ = ["parse", "compare", "bump", "SemVer"]
