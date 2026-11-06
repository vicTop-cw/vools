"""compress.py 测试：clone 自 clip/Jump/common/universal_compress.py 的压缩能力 + vools-rhop 增强。

覆盖：
- 单文件 bytes 往返（zip/gzip/bz2/lzma 四格式）
- 文件级压缩/还原（compress_file / restore_file）
- 格式自动探测（detect_algo / decompress_bytes auto）
- 自动选优算法（compress_bytes_auto）
- 多文件批次结构（compress_many）
- rows <-> CSV 字节往返（传输链路适配）
- dict 载荷打包/还原（pack_dict / unpack_dict）
"""

import io
import json
import os

import pytest

from vools.rhop.compress import (
    ALGO_DEFAULT,
    compress_bytes,
    compress_bytes_auto,
    compress_file,
    compress_many,
    csv_bytes_to_rows,
    decompress_bytes,
    detect_algo,
    pack_dict,
    restore_bytes,
    restore_bytes_to_bytes,
    restore_file,
    restore_many,
    rows_to_csv_bytes,
    unpack_dict,
)

ALGOS = ["zip", "gzip", "bz2", "lzma"]


def _sample(size=2048):
    """可压缩性适中的样本（含重复块与随机段）。"""
    block = (b"hello vools-rhop compress roundtrip " * 20)
    return block * (size // len(block) + 1) + b"\x00\x01\x02random-tail"


class TestSingleFileRoundtrip:
    @pytest.mark.parametrize("algo", ALGOS)
    def test_bytes_roundtrip(self, algo, tmp_path):
        raw = _sample()
        rows = compress_bytes(raw, algo=algo)
        assert rows is not None
        meta = [c for xh, c in rows if xh == 0][0]
        assert ("ALGO=%s" % algo) in meta
        # 不落盘还原
        out = restore_bytes_to_bytes(rows)
        assert out == raw
        # 落盘还原
        target = str(tmp_path / ("out_" + algo + ".bin"))
        restored = restore_bytes(rows, target)
        assert restored == target
        with open(target, "rb") as f:
            assert f.read() == raw

    def test_algo_default_lzma(self):
        raw = _sample()
        rows = compress_bytes(raw)
        meta = [c for xh, c in rows if xh == 0][0]
        assert ("ALGO=%s" % ALGO_DEFAULT) in meta


class TestFileInterface:
    def test_compress_file_restore_file(self, tmp_path):
        src = tmp_path / "src.bin"
        src.write_bytes(_sample())
        rows = compress_file(str(src))
        assert rows is not None
        csv_path = tmp_path / "packet.csv"
        with open(str(csv_path), "w", newline="", encoding="utf-8") as f:
            import csv as _csv
            w = _csv.writer(f)
            for xh, c in rows:
                w.writerow([xh, c])
        target = tmp_path / "restored.bin"
        restore_file(str(csv_path), str(target))
        assert target.read_bytes() == src.read_bytes()

    def test_compress_many_structure(self, tmp_path):
        files = []
        for i, algo in enumerate(ALGOS):
            p = tmp_path / ("f%d.txt" % i)
            p.write_bytes(_sample(1024 * (i + 1)))
            files.append(str(p))
        batches = compress_many(files, algo="lzma")
        assert isinstance(batches, list) and batches
        for batch in batches:
            # 每批都是 [(xh, content)] 数据行，xh 连续 1..ROWS（xh=0 的 meta 由调用方插入）
            rows = [(xh, c) for xh, c in batch]
            assert rows
            assert rows[0][0] == 1
            assert [xh for xh, _ in rows] == list(range(1, len(rows) + 1))


class TestAutoDetect:
    @pytest.mark.parametrize("algo", ALGOS)
    def test_detect_algo(self, algo):
        compressed = __import__("vools.rhop.compress", fromlist=["_compress_bytes"])._compress_bytes(_sample(), algo, "data.bin")
        assert detect_algo(compressed) == algo

    @pytest.mark.parametrize("algo", ALGOS)
    def test_decompress_bytes_auto(self, algo):
        compressed = __import__("vools.rhop.compress", fromlist=["_compress_bytes"])._compress_bytes(_sample(), algo, "data.bin")
        assert decompress_bytes(compressed, algo="auto") == _sample()

    def test_detect_unknown(self):
        assert detect_algo(b"not a compressed stream") is None


class TestAutoChoose:
    def test_compress_bytes_auto(self):
        raw = _sample()
        algo = compress_bytes_auto(raw)
        assert algo in ALGOS
        rows = compress_bytes(raw, algo=algo)
        assert restore_bytes_to_bytes(rows) == raw


class TestTransportAdapter:
    def test_rows_csv_bytes_roundtrip(self):
        raw = _sample()
        rows = compress_bytes(raw, algo="lzma")
        data = rows_to_csv_bytes(rows)
        assert isinstance(data, bytes)
        rows2 = csv_bytes_to_rows(data)
        assert restore_bytes_to_bytes(rows2) == raw

    def test_csv_bytes_tolerates_wrapping(self):
        # 模拟 SMTP QP 软换行与空白混入：_decode_slices 必须兜住
        raw = _sample()
        rows = compress_bytes(raw, algo="gzip")
        text = rows_to_csv_bytes(rows).decode("utf-8")
        corrupted = text.replace("\n", "=\r\n")
        rows2 = csv_bytes_to_rows(corrupted.encode("utf-8"))
        assert restore_bytes_to_bytes(rows2) == raw


class TestPayloadDict:
    def test_pack_unpack_dict(self):
        payload = {"action": "run", "args": ["a", "b"], "k": "中文值", "n": 3}
        rows = pack_dict(payload)
        assert restore_bytes_to_bytes(rows) == json.dumps(
            payload, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        assert unpack_dict(rows) == payload

    def test_unpack_dict_roundtrip_via_csv(self):
        payload = {"task": "p3_demo", "ds": "20261106"}
        rows = pack_dict(payload)
        assert unpack_dict(csv_bytes_to_rows(rows_to_csv_bytes(rows))) == payload
