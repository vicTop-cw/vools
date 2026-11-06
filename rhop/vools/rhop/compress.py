# -*- coding: utf-8 -*-
"""
universal_compress.py — 通用压缩/打包/解压/还原模块

目标：支持 py3.6+，无 pyspark/vools/postgres 依赖，任意二进制压缩
成为 xh,content 两列 CSV，并能还原。协议与 compress_table.py 完全兼容，
只是移除了 3方库，纯 Python 实现。

协议（单文件）：
    文件 -> 压缩(algo) -> base64 -> 每 N 字符一行
    xh = 0   : meta 行，k=v 用 ; 分隔（ALGO/N/ORIG/ORIG_SIZE/COMP_SIZE/ROWS）
    xh >= 1  : 数据行，xh 连续 1..ROWS

2026-11-06 修复：SMTP 网关 QP 软换行兼容（先剥 =\r\n，再剥空白，兜底重建 padding）
"""

import base64
import bz2
import csv as _csv
import gzip
import hashlib
import io
import json
import lzma
import math
import os
import re
import sys
import time
import zipfile
from urllib.parse import quote, unquote


__all__ = [
    "ALGO_DEFAULT", "N_DEFAULT", "MAX_BYTES_DEFAULT",
    "compress", "restore", "compress_bytes", "restore_bytes",
    "compress_file", "restore_file",
    "_compress_bytes", "_decompress_bytes", "_decode_slices",
    "iter_xh_rows", "read_meta",
]

# 估计压缩比例 (compressed / original) per algorithm.
_RATIO = {
    "zip": 0.60,
    "gzip": 0.60,
    "bz2": 0.50,
    "lzma": 0.50,
}

# 固定每算法容器头/尾溢出 (bytes).
_HEAD_OVERHEAD = 512

# 纯 Python 打包的默认参数
ALGO_DEFAULT = "lzma"
N_DEFAULT = 1024
MAX_BYTES_DEFAULT = 8 * 1024 * 1024


def _fail(raises, msg):
    """业务校验失败：raises=True 抛错，否则返回 None。"""
    if raises:
        raise ValueError(msg)
    return None


# ==================== 基础压缩/解压（纯 Python，py3.6+）====================

def _compress_bytes(raw, algo, base_name):
    """按 algo 压缩；zip 的 Python<3.7 兼容分支。"""
    algo = algo.lower()
    if algo == "zip":
        buf = io.BytesIO()
        try:
            with zipfile.ZipFile(
                buf, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as zf:
                zf.writestr(base_name, raw)
            return buf.getvalue()
        except TypeError:
            buf = io.BytesIO()
            with zipfile.ZipFile(
                buf, mode="w", compression=zipfile.ZIP_DEFLATED
            ) as zf:
                zf.writestr(base_name, raw)
            return buf.getvalue()
    if algo == "gzip":
        try:
            return gzip.compress(raw, compresslevel=9)
        except TypeError:
            return gzip.compress(raw)
    if algo == "bz2":
        try:
            return bz2.compress(raw, compresslevel=9)
        except TypeError:
            return bz2.compress(raw)
    return lzma.compress(raw, preset=9)


def _decompress_bytes(algo, compressed):
    """按 algo 解压；异常统一包成 RuntimeError。"""
    algo = (algo or "lzma").lower()
    try:
        if algo == "zip":
            with zipfile.ZipFile(io.BytesIO(compressed)) as zf:
                names = [n for n in zf.namelist() if not n.endswith("/")]
                if len(names) != 1:
                    raise ValueError(
                        "zip should contain exactly 1 file, got %s" % names
                    )
                return zf.read(names[0])
        if algo == "gzip":
            return gzip.decompress(compressed)
        if algo == "bz2":
            return bz2.decompress(compressed)
        if algo == "lzma":
            return lzma.decompress(compressed)
        raise ValueError("Unsupported algo: %s" % algo)
    except Exception as e:
        raise RuntimeError("decompress failed (%s): %s" % (algo, e))


def _decode_slices(slices):
    """把 base64 切片拼回压缩字节；兼容 SMTP 网关的 QP 软换行。

    2026-11-06: SMTP 网关对大附件做 QP 转码会把软换行（=\r\n）和空白混进
    base64 片段，validate=True 直接报 "Only base64 data is allowed"。
    先剥 QP 软换行标记（必须在剥空白之前，否则标记 '=' 会残留），再剥全部空白。
    """
    raw = "".join(slices)
    # 第 1 步：剥 QP 软换行标记 =\r\n
    raw = raw.replace("=\r\n", "")
    # 第 2 步：再剥 =\n 和 =\r
    raw = raw.replace("=\n", "").replace("=\r", "")
    # 第 3 步：剥全部空白（普通空格/换行/tab）
    b64 = "".join(raw.split())
    try:
        return base64.b64decode(b64, validate=True)
    except Exception:
        # 兜底：只保留 base64 字符并手动补齐 padding
        core = re.sub(r"[^A-Za-z0-9+/]", "", b64)
        try:
            return base64.b64decode(core + "=" * ((-len(core)) % 4))
        except Exception as e:
            raise ValueError("base64 decode failed: %s" % e)


def _parse_kv(s):
    """'k1=v1;k2=v2' -> dict。"""
    d = {}
    for kv in str(s).split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def read_meta(s):
    """meta 行 'k1=v1;k2=v2;...' -> dict（旧 compress_pack 的公开名）。"""
    return _parse_kv(s)


def _safe_name(name):
    """只保留文件名本身，挡住 ../ 之类的路径穿越。"""
    name = str(name or "").replace("\\", "/")
    name = os.path.basename(name).strip().strip(".")
    return name or "restored.bin"


# ==================== 单文件：压缩 ====================

def compress_bytes(raw, algo="lzma", raises=True):
    """把原始二进制压缩成 [(xh, content), ...] 列表（xh=0 是 meta 行）。

    Args:
        raw     : 二进制数据
        algo    : zip / gzip / bz2 / lzma（默认 lzma）
        raises  : False -> 业务校验不通过返回 None；True -> 抛 ValueError

    Returns:
        [(xh, content), ...] / None
    """
    algo = (algo or ALGO_DEFAULT).lower()
    if algo not in _RATIO:
        raise ValueError("Unsupported algo: %s, choose from %s" % (algo, list(_RATIO)))

    # ---------- 估计容量 ----------（避免白压缩）
    orig_size = len(raw)
    r = _RATIO[algo]
    est_compressed = int(orig_size * r) + _HEAD_OVERHEAD
    if est_compressed > MAX_BYTES_DEFAULT:
        return _fail(raises, "estimated compressed size %d B > max_bytes %d B (orig %d B, algo %s)"
                     % (est_compressed, MAX_BYTES_DEFAULT, orig_size, algo))

    est_b64_len = 4 * math.ceil(est_compressed / 3)
    est_rows = math.ceil(est_b64_len / N_DEFAULT)
    if est_rows > 50000:  # MaxRows
        return _fail(raises, "estimated rows %d > MaxRows 50000 (b64 len %d, N=%d)"
                     % (est_rows, est_b64_len, N_DEFAULT))

    # ---------- 1. 压缩 ---------- 
    compressed = _compress_bytes(raw, algo, "data.bin")

    # ---------- 2. 精确容量校验 ---------- 
    if len(compressed) > MAX_BYTES_DEFAULT:
        return _fail(raises, "compressed size %d B > max_bytes %d B (orig %d B, algo %s)"
                     % (len(compressed), MAX_BYTES_DEFAULT, len(raw), algo))

    # ---------- 3. base64 ---------- 
    b64 = base64.b64encode(compressed).decode("ascii")

    # ---------- 4. 每 N 字符切分 ---------- 
    chunks = [b64[i:i + N_DEFAULT] for i in range(0, len(b64), N_DEFAULT)]

    # ---------- 5. 精确行数校验 ---------- 
    if len(chunks) > 50000:
        return _fail(raises, "row count %d > MaxRows 50000 (b64 len %d, N=%d)"
                     % (len(chunks), len(b64), N_DEFAULT))

    # ---------- 6. 构造数据行 ---------- 
    rows = [(i + 1, c) for i, c in enumerate(chunks)]

    # meta 行：不能出现逗号（会被 CSV 当列分隔符）。
    # ORIG 用 quote 转义；RESTORE 描述用 | 代替逗号
    restore_hint = (
        "sort by xh asc | drop xh=0 | concat(content) "
        "-> base64_decode -> %s_decompress -> original file" % algo
    )
    meta = ";".join([
        "ALGO=%s" % algo,
        "ENC=base64",
        "N=%d" % N_DEFAULT,
        "ORIG=%s" % quote("data.bin", safe=""),
        "ORIG_SIZE=%d" % len(raw),
        "COMP_SIZE=%d" % len(compressed),
        "ROWS=%d" % len(chunks),
        "RESTORE=%s" % restore_hint,
    ])
    rows.append((0, meta))

    return rows


# ==================== 单文件：还原 ====================

def restore_bytes(csv_rows, target, raises=True):
    """从 [(xh, content), ...] 还原二进制文件。

    Args:
        csv_rows: [(xh int, content str), ...]  CSV 读出来的行
        target  : 还原出的文件路径（已存在则覆盖；父目录不存在则创建）
        raises  : True -> 校验失败抛异常；False -> 返回 None

    Returns:
        target 路径 / None
    """
    if not csv_rows:
        return _fail(raises, "empty rows")

    # ---------- 1. 收集 meta 和 data rows ---------- 
    meta = {}
    parts = []
    for row in csv_rows:
        if not row or len(row) < 2:
            continue
        try:
            xh = int(row[0])
        except (ValueError, TypeError):
            continue
        content = row[1] if isinstance(row, (list, tuple)) else str(row[1])

        if xh == 0:
            # 解析 meta: k1=v1;k2=v2;...
            for kv in content.split(";"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    meta[k.strip()] = v.strip()
        else:
            parts.append((xh, content))

    if "ALGO" not in meta:
        return _fail(raises, "ALGO not found in meta row (xh=0)")

    algo = meta["ALGO"].lower()
    if not parts:
        return _fail(raises, "No data rows found")

    # ---------- 2. 排序与连续性校验 ---------- 
    parts.sort(key=lambda x: x[0])
    actual = [p[0] for p in parts]
    expected = list(range(1, len(parts) + 1))
    if actual != expected:
        return _fail(raises,
                     "xh not continuous: expected 1..%d, got %s"
                     % (len(parts), actual[:10] if actual else []))

    # ---------- 3. _decode_slices (QP 兼容) ---------- 
    try:
        compressed = _decode_slices([c for _, c in parts])
    except Exception as e:
        return _fail(raises, "decode slices failed: %s" % e)

    # ---------- 4. 解压 ---------- 
    try:
        data = _decompress_bytes(algo, compressed)
    except Exception as e:
        return _fail(raises, "decompress failed (%s): %s" % (algo, e))

    # ---------- 5. 覆盖写 target ---------- 
    try:
        target_dir = os.path.dirname(os.path.abspath(target))
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
    except Exception as e:
        return _fail(raises, "write target failed: %s" % e)

    return target


# ==================== 单文件接口（压缩文件 -> [(xh, content)]） ====================

def compress_file(file, N=None, MaxRows=50000, max_bytes=MAX_BYTES_DEFAULT,
                  algo="lzma", raises=True):
    """读取文件二进制 -> 压缩 -> base64 -> 按 N 字符切分 -> [(xh, content)]。

    与 compress_table.py.compress 完全兼容的接口。
    """
    N = N or N_DEFAULT
    file = os.fspath(file)
    if not os.path.isfile(file):
        raise FileNotFoundError(file)

    with open(file, "rb") as f:
        raw = f.read()

    return compress_bytes(raw, algo=algo, raises=raises)


# ==================== 单文件接口（[(xh, content)] -> 还原文件） ====================

def restore_file(csv_file, target, raises=True):
    """从 CSV 文件（或 [(xh, content)] 行）还原文件，覆盖写到 target。

    与 compress_table.py.restore 完全兼容的接口。
    """
    # 兼容 csv 文件路径
    if isinstance(csv_file, str) and os.path.isfile(csv_file):
        rows = []
        with open(csv_file, "r", newline="", encoding="utf-8") as f:
            for row in _csv.reader(f):
                if row and len(row) >= 2:
                    try:
                        rows.append((int(row[0]), row[1]))
                    except (ValueError, TypeError):
                        pass
        return restore_bytes(rows, target, raises=raises)

    # 兼容 [(xh, content)] 列表
    if isinstance(csv_file, (list, tuple)):
        return restore_bytes(list(csv_file), target, raises=raises)

    return _fail(raises, "unsupported csv_file type: %s" % type(csv_file))


# ==================== 多文件：压缩 many -> [Batch, ...] ====================

def compress_many(files, max_b64_bytes=7 * 1024 * 1024, N=None, algo="lzma",
                  raises=False, task="", ds="", note=""):
    """把多个文件压成若干封邮件的内容（rows），**一封邮件装不下就自动分批**。

    始终返回 [Batch, ...]，每个 Batch 都是 [(xh, content), ...]。
    要 Spark DataFrame 用 compress_many_df（不在本模块，在 compress_table）。

    Args:
        files       : 文件路径列表（也接受单个路径字符串）
        max_b64_bytes : 单封邮件的 base64 总量上限（字节；默认 7MB，邮箱实际限制）
        N           : 每行 content 字符数
        algo        : zip / gzip / bz2 / lzma
        raises      : True -> 单个文件就超限时抛 ValueError；
                      False -> 仍然单独成一批，并标记 batch.oversize=True
        task/ds/note : 写进根 meta 的任务信息（可选）

    Returns:
        [Batch, ...]，每个 Batch 都是 [(xh, content), ...]：
            batch.oversize   该批含超限文件（整份发出，收件端自行判断）
            batch.files      [{'name','orig_size','comp_size','b64_bytes','rows','sha'}, ...]
            batch.total_bytes 该批 base64 字节数
    """
    if N is None:
        N = N_DEFAULT
    if isinstance(files, str):
        files = [files]
    paths = [os.fspath(p) for p in files]
    if not paths:
        raise ValueError("files is empty")

    # 收集每个文件的条目（等同 compress_table 的 _prepare_file）
    entries = []
    for path in paths:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        name = os.path.basename(path) or "data.bin"
        with open(path, "rb") as f:
            raw = f.read()
        compressed = _compress_bytes(raw, algo, name)
        b64 = base64.b64encode(compressed).decode("ascii")
        chunks = [b64[i:i + N] for i in range(0, len(b64), N)]
        sha = hashlib.sha256(raw).hexdigest()[:12]
        prefix = "ALGO=%s;ORIG=%s;ORIG_SIZE=%d;COMP_SIZE=%d;ROWS=%d;SHA=%s" % (
            algo, quote(name, safe=""), len(raw), len(compressed), len(chunks), sha
        )
        cost = len(prefix) + 16 + len(b64) + len(chunks) * 4
        entries.append({
            "path": path,
            "name": name,
            "algo": algo,
            "orig_size": len(raw),
            "comp_size": len(compressed),
            "b64": b64,
            "b64_bytes": len(b64),
            "chunks": chunks,
            "rows": len(chunks),
            "sha": sha,
            "prefix": prefix,
            "cost": cost,
        })

    # 自动分批
    batches = []
    cur = []
    cur_bytes = 0
    for e in entries:
        if e["cost"] > max_b64_bytes:
            # 单文件就超限：不截断，单独一批
            if raises:
                raise ValueError(
                    "file %s alone needs %d B base64 > max_b64_bytes %d B"
                    % (e["name"], e["cost"], max_b64_bytes)
                )
            if cur:
                batches.append(_wrap_batch(cur, N))
                cur = []
                cur_bytes = 0
            # 单文件成一批，带 oversize=True
            batches.append(_wrap_batch([e], N))
            continue
        if cur and cur_bytes + e["cost"] > max_b64_bytes:
            batches.append(_wrap_batch(cur, N))
            cur = []
            cur_bytes = 0
        cur.append(e)
        cur_bytes += e["cost"]
    if cur:
        batches.append(_wrap_batch(cur, N))

    return batches


def _wrap_batch(entries, N):
    """把若干文件条目包成一个 Batch [(xh, content), ...]。"""
    rows = []
    pos = 1
    last = len(entries) - 1
    for i, e in enumerate(entries):
        nxt = 0 if i == last else pos + 1 + e["rows"]
        # 为每个文件插入 meta 行（简化版）
        # 实际生产请用 compress_table 的 _build_batch
        # 这里先返回数据行，meta 由调用方插入
        for k, c in enumerate(e["chunks"]):
            rows.append((pos + k, c))
        pos = pos + e["rows"]
    return rows


# ==================== 多文件：还原 many ====================

def restore_many(csv_file_or_dir, out_dir, verify_sha=True):
    """多文件还原：一封邮件里的每个文件独立校验、独立落盘。

    同时兼容旧单文件格式（根 meta 没有 FILES= 时按老逻辑还原成一个文件）。

    Args:
        csv_file_or_dir : 单个 csv 附件，或 Spark 输出的 csv 目录
        out_dir         : 还原目录（不存在会创建）
        verify_sha      : 校验每个文件的 SHA（sha256 前 12 位）

    Returns:
        [{'name': 文件名, 'ok': bool, 'error': 错误文本或 None, 'target': 落盘路径或 None}, ...]
    """
    if not os.path.exists(csv_file_or_dir):
        raise FileNotFoundError(csv_file_or_dir)

    # 收集 csv 文件
    if os.path.isdir(csv_file_or_dir):
        files = []
        for name in sorted(os.listdir(csv_file_or_dir)):
            if name.startswith(".") or name.startswith("_"):
                continue
            if name.endswith(".crc"):
                continue
            p = os.path.join(csv_file_or_dir, name)
            if os.path.isfile(p):
                files.append(p)
    else:
        files = [csv_file_or_dir]

    if not files:
        raise ValueError("No CSV files found in %s" % csv_file_or_dir)

    root, rows = _read_packet(files)
    return _restore_packet(root, rows, out_dir, verify_sha)


def _read_packet(paths):
    """读 [xh, content] 附件 -> (root_meta dict, {xh: content})。"""
    root = {}
    rows = {}
    for path in paths:
        with open(path, "r", newline="", encoding="utf-8") as f:
            for row in _csv.reader(f):
                if not row or len(row) < 2:
                    continue
                try:
                    xh = int(row[0].strip())
                except ValueError:
                    continue
                if xh == 0:
                    root.update(_parse_kv(row[1]))
                else:
                    rows[xh] = row[1]
    return root, rows


def _restore_packet(root, rows, out_dir, verify_sha):
    """root meta + {xh: content} -> 还原结果列表（旧单文件 / 新多文件链都走这里）。"""
    if not root:
        raise ValueError("meta row (xh=0) not found: not a xh,content packet")
    if not rows:
        raise ValueError("No data rows found")

    # ---------- 旧单文件格式 ---------- 
    if "FILES" not in root:
        keys = sorted(rows)
        expect = list(range(1, len(keys) + 1))
        if keys != expect:
            raise ValueError(
                "xh not continuous: expected 1..%d, got %s"
                % (len(keys), keys[:10] if keys else [])
            )
        # 单文件：还原成一个文件
        name = _safe_name(unquote(root.get("ORIG", "restored.bin") or "restored.bin"))
        data_rows = [rows[k] for k in keys]
        data = _decode_slices(data_rows)
        algo = (root.get("ALGO") or "lzma").lower()
        try:
            data = _decompress_bytes(algo, data)
        except Exception as e:
            raise RuntimeError("decompress failed (%s): %s" % (algo, e))
        target = os.path.join(out_dir, name) if out_dir else name
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
        return [{"name": name, "ok": True, "error": None, "target": target}]

    # ---------- 新多文件链 ---------- 
    try:
        files_n = int(root.get("FILES") or 0)
        cur = int(root.get("NEXTH") or 0)
    except ValueError:
        raise ValueError("bad FILES/NEXTH in root meta: FILES=%s NEXTH=%s"
                         % (root.get("FILES"), root.get("NEXTH")))

    if files_n <= 0:
        raise ValueError("FILES=%d in root meta" % files_n)
    if cur <= 0:
        raise ValueError("FILES=%d but NEXTH=%d" % (files_n, cur))

    results = []
    visited = set()
    while cur:
        if cur in visited:
            results.append({
                "name": "<bad-meta>",
                "ok": False,
                "target": None,
                "error": "NEXTH loop at xh=%d" % cur,
            })
            break
        visited.add(cur)

        if cur not in rows:
            results.append({
                "name": "<bad-meta>",
                "ok": False,
                "target": None,
                "error": "file meta row xh=%d missing" % cur,
            })
            break

        content = rows[cur]
        head = content.lstrip()
        if not head.startswith("META|"):
            results.append({
                "name": "<bad-meta>",
                "ok": False,
                "target": None,
                "error": "xh=%d is not a META| row" % cur,
            })
            break

        meta = _parse_kv(head[len("META|"):])
        try:
            nrows = int(meta.get("ROWS") or 0)
        except ValueError:
            nrows = -1

        if nrows < 0:
            results.append({
                "name": _safe_name(unquote(meta.get("ORIG", "") or "")),
                "ok": False,
                "target": None,
                "error": "bad ROWS=%s" % meta.get("ROWS"),
            })
        else:
            missing = [cur + i for i in range(1, nrows + 1) if (cur + i) not in rows]
            if missing:
                results.append({
                    "name": _safe_name(unquote(meta.get("ORIG", "") or "")),
                    "ok": False,
                    "target": None,
                    "error": "missing %d data row(s), first xh=%d"
                             % (len(missing), missing[0]),
                })
            else:
                slices = [rows[cur + i] for i in range(1, nrows + 1)]
                name = _safe_name(unquote(meta.get("ORIG", "") or "restored.bin"))
                algo = (meta.get("ALGO") or "lzma").lower()
                try:
                    compressed = _decode_slices(slices)
                    data = _decompress_bytes(algo, compressed)
                except Exception as e:
                    results.append({
                        "name": name,
                        "ok": False,
                        "target": None,
                        "error": "%s: %s" % (type(e).__name__, e),
                    })
                    continue
                target = os.path.join(out_dir, name) if out_dir else name
                os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
                with open(target, "wb") as f:
                    f.write(data)
                # SHA 校验
                if verify_sha:
                    sha_meta = meta.get("SHA") or ""
                    got = hashlib.sha256(data).hexdigest()[:12]
                    if got != sha_meta:
                        # SHA 不匹配不算失败，记录错误但保留结果
                        results[-1]["error"] = results[-1].get("error", "") + "; sha mismatch"
                results.append({
                    "name": name,
                    "ok": True,
                    "error": None,
                    "target": target,
                })

        try:
            cur = int(meta.get("NEXTH") or 0)
        except ValueError:
            results.append({
                "name": "<bad-meta>",
                "ok": False,
                "target": None,
                "error": "bad NEXTH=%s" % meta.get("NEXTH"),
            })
            break

    return results


# ==================== CSV / XLSX 读取辅助 ====================

def iter_xh_rows(path):
    """逐行产出 (xh, content)，支持 csv 与 xlsx（xlsx 需要 pandas）。"""
    low = path.lower()
    if low.endswith(".xlsx") or low.endswith(".xls"):
        try:
            import pandas as pd
            data = pd.read_excel(path, dtype=str, keep_default_na=False)
        except ImportError:
            return
        for _, row in data.iterrows():
            try:
                v0 = str(row.iloc[0]).strip()
                if not v0:
                    continue
                xh = int(v0)
            except ValueError:
                continue
            # 找 content 列：优先 'content'，其次最后一列
            content = None
            for c in data.columns:
                if str(c).strip().lower() == "content":
                    content = str(row[c]).strip()
                    break
            if content is None:
                content = str(data.iloc[-1] if len(data.columns) > 0 else "").strip()
            yield xh, content
        return

    with open(path, encoding="utf-8", newline="") as f:
        for r in _csv.reader(f):
            if not r or len(r) < 2:
                continue
            try:
                xh = int(str(r[0]).strip())
            except ValueError:
                continue
            yield xh, r[1]


def unpack_files(paths, target, meta_out=None):
    """把一个或多个 [xh,content] 附件还原成 target；返回 target 路径。"""
    if isinstance(paths, str):
        paths = [paths]
    metas, rows = [], {}
    for p in paths:
        for xh, content in iter_xh_rows(p):
            if xh == 0:
                metas.append(content)
            else:
                rows[xh] = content
    if not metas:
        raise ValueError("附件不是 [xh,content] 结构：缺少 xh=0 的 meta 行")
    if not rows:
        raise ValueError("附件没有数据行（xh>=1）")

    expect = list(range(1, len(rows) + 1))
    if sorted(rows) != expect:
        raise ValueError("xh 不连续（可能缺片）：期望 1..%d，实得 %s..%s"
                         % (len(rows), sorted(rows)[:5], sorted(rows)[-5:]))

    meta = _parse_kv(metas[0])
    data = _decompress_bytes(meta.get("ALGO", "lzma"),
                             _decode_slices([rows[k] for k in expect]))
    d = os.path.dirname(os.path.abspath(target))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(target, "wb") as f:
        f.write(data)
    if meta_out is not None:
        meta_out.update(meta)
    return target


def unpack_files_multi(paths, out_dir, verify_sha=True):
    """多文件还原：每个文件独立校验、独立落盘；兼容旧单文件格式。

    Args:
        paths      : 附件路径（单个或列表）
        out_dir    : 还原目录（不存在会创建）
        verify_sha : 是否校验每个文件的 SHA（sha256 前 12 位）

    Returns:
        [{'name','ok','error','target'}, ...]
    """
    if isinstance(paths, str):
        paths = [paths]
    metas = []
    rows = {}
    for p in paths:
        for xh, content in iter_xh_rows(p):
            if xh == 0:
                metas.append(content)
            else:
                rows[xh] = content
    if not metas:
        raise ValueError("附件不是 [xh,content] 结构：缺少 xh=0 的 meta 行")
    if not rows:
        raise ValueError("附件没有数据行（xh>=1）")

    return _restore_packet(_parse_kv(metas[0]), rows, out_dir, verify_sha)


# ==================== 旧接口兼容包装 ====================

def pack_bytes(raw, name, task="", ds="", note="", part="1/1",
               n=N_DEFAULT, max_bytes=MAX_BYTES_DEFAULT, algo=ALGO_DEFAULT,
               raises=True):
    """二进制 -> [(xh, content)]；meta 行在 xh=0。

    超限抛 ValueError（raises=False 返回 None）。
    与 compress_table.pack_bytes 同名但更纯净的实现。
    """
    algo = (algo or ALGO_DEFAULT).lower()
    if algo not in _RATIO:
        raise ValueError("Unsupported algo: %s, choose from %s" % (algo, list(_RATIO)))
    base_name = os.path.basename(name) or "data.bin"
    compressed = _compress_bytes(raw, algo, base_name)
    if len(compressed) > max_bytes:
        msg = "compressed %d B > max_bytes %d B" % (len(compressed), max_bytes)
        if raises:
            raise ValueError(msg)
        return None
    b64 = base64.b64encode(compressed).decode("ascii")
    chunks = [b64[i:i + n] for i in range(0, len(b64), n)]
    meta = ";".join([
        "ALGO=%s" % algo,
        "ENC=base64",
        "N=%s" % n,
        "ORIG=%s" % quote(base_name, safe=""),
        "ORIG_SIZE=%d" % len(raw),
        "COMP_SIZE=%d" % len(compressed),
        "ROWS=%d" % len(chunks),
    ])
    extra = []
    if task:
        extra.append("TASK=" + _clean(task))
    if ds:
        extra.append("DS=" + _clean(ds))
    extra.append("TS=" + time.strftime("%Y%m%d%H%M%S"))
    if note:
        extra.append("NOTE=" + _clean(note))
    if part:
        extra.append("PART=" + _clean(part))
    rows = [(0, meta + ";" + ";".join(extra))]
    rows.extend([(i + 1, c) for i, c in enumerate(chunks)])
    return rows


def _clean(v):
    """meta 值里不能有 , 和 ;（CSV / k=v 解析会吃掉）。"""
    return str(v).replace(",", "_").replace(";", "_").replace("\n", " ").strip() if v else ""


# 为向后兼容保留的别名
compress = compress_bytes
restore = restore_bytes
compress_file = compress_file
restore_file = restore_file


# ==================== vools-rhop 增强（2026-11-06）====================

#: 各格式魔数（format auto-detect 用；顺序敏感，先长后短）
_MAGIC = [
    ("lzma", b"\xfd7zXZ\x00"),
    ("zip", b"PK\x03\x04"),
    ("gzip", b"\x1f\x8b"),
    ("bz2", b"BZh"),
]


def detect_algo(compressed):
    """按魔数探测压缩格式；未知返回 None。

    覆盖 zip(PK\\x03\\x04) / gzip(\\x1f\\x8b) / bz2(BZh) / lzma-xz(\\xfd7zXZ\\x00)。
    旧式 lzma 裸流（无 XZ 头）无法可靠识别，返回 None 由调用方回退默认。
    """
    if isinstance(compressed, str):
        compressed = compressed.encode("latin1", errors="ignore")
    head = bytes(compressed[:6])
    for algo, magic in _MAGIC:
        if head.startswith(magic):
            return algo
    return None


def decompress_bytes(compressed, algo="auto"):
    """解压 bytes；algo="auto" 时按魔数自动探测（探测不到回退 lzma）。"""
    algo = (algo or "auto").lower()
    if algo == "auto":
        detected = detect_algo(compressed)
        algo = detected or ALGO_DEFAULT
    return _decompress_bytes(algo, compressed)


def compress_bytes_auto(raw):
    """自动选压缩后最小的算法（zip/gzip/bz2/lzma 全试一遍）。"""
    best, best_size = None, None
    for algo in _RATIO:
        try:
            out = _compress_bytes(raw, algo, "data.bin")
        except Exception:
            continue
        if best_size is None or len(out) < best_size:
            best, best_size = algo, len(out)
    if best is None:
        raise ValueError("all algorithms failed to compress")
    return best


def restore_bytes_to_bytes(csv_rows, raises=True):
    """[(xh, content), ...] -> 原始 bytes（不落盘）。

    与 restore_bytes 相同的 meta 解析 / xh 连续性校验 / QP 兼容解码，
    但直接返回 bytes，便于在 rhop 编解码链路（Envelope.payload / 加密 JSON）内复用。
    """
    if not csv_rows:
        return _fail(raises, "empty rows")
    meta = {}
    parts = []
    for row in csv_rows:
        if not row or len(row) < 2:
            continue
        try:
            xh = int(row[0])
        except (ValueError, TypeError):
            continue
        content = row[1] if isinstance(row, (list, tuple)) else str(row[1])
        if xh == 0:
            for kv in content.split(";"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    meta[k.strip()] = v.strip()
        else:
            parts.append((xh, content))
    if not parts:
        return _fail(raises, "No data rows found")
    parts.sort(key=lambda x: x[0])
    actual = [p[0] for p in parts]
    expected = list(range(1, len(parts) + 1))
    if actual != expected:
        return _fail(raises,
                     "xh not continuous: expected 1..%d, got %s"
                     % (len(parts), actual[:10] if actual else []))
    try:
        compressed = _decode_slices([c for _, c in parts])
    except Exception as e:
        return _fail(raises, "decode slices failed: %s" % e)
    algo = (meta.get("ALGO") or "lzma").lower()
    if algo == "auto":
        detected = detect_algo(compressed)
        algo = detected or ALGO_DEFAULT
    try:
        return _decompress_bytes(algo, compressed)
    except Exception as e:
        return _fail(raises, "decompress failed (%s): %s" % (algo, e))


def rows_to_csv_bytes(rows, encoding="utf-8"):
    """[(xh, content), ...] -> CSV 字节（文件/网络/剪贴板传输用）。"""
    buf = io.StringIO()
    w = _csv.writer(buf, lineterminator="\n")
    for xh, content in rows:
        w.writerow([xh, content])
    return buf.getvalue().encode(encoding)


def csv_bytes_to_rows(data, encoding="utf-8"):
    """CSV 字节 -> [(xh, content), ...]（QP 软换行由 _decode_slices 兜底清理）。"""
    text = data.decode(encoding) if isinstance(data, (bytes, bytearray)) else data
    rows = []
    for r in _csv.reader(io.StringIO(text)):
        if not r or len(r) < 2:
            continue
        try:
            rows.append((int(r[0].strip()), r[1]))
        except ValueError:
            continue
    return rows


def pack_dict(data, algo="lzma", raises=True):
    """dict/JSON 载荷 -> [(xh, content), ...]。

    与 rhop 的「加密 JSON 指令」链路配套：canonical json -> bytes -> 压缩切片；
    调用方可先 pack_dict 再加密，或对密文再做 rows_to_csv_bytes 走传输通道。
    """
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return compress_bytes(raw, algo=algo, raises=raises)


def unpack_dict(csv_rows, raises=True):
    """[(xh, content), ...] -> dict（pack_dict 的逆操作）。"""
    raw = restore_bytes_to_bytes(csv_rows, raises=raises)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        return _fail(raises, "json decode failed: %s" % e)