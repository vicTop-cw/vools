#!/usr/bin/env python3
"""R10H 一次性基线驱动：逐文件独立进程跑 actus/tests/test_*.py。

背景：上轮修复收集错误后 full suite 收集 5657 tests，但
`python -m pytest -q tests` 10 分钟无输出，未定论是慢还是挂。
本脚本用 subprocess 逐个跑测试文件（单文件硬超时 300s，超时记 HANG），
汇总每文件用例数/耗时/结果，输出 Markdown 报告 actus/docs/BASELINE_R10H.md。

用法：
    python tools/_baseline_r10h.py                # 全量（支持断点续跑）
    python tools/_baseline_r10h.py --only a.py,b.py
    python tools/_baseline_r10h.py --rerun        # 忽略已有结果重跑
    python tools/_baseline_r10h.py --timeout 300

产物：
    actus/tools/_baseline_r10h_results.jsonl   # 增量结果（可删）
    actus/tools/_baseline_r10h.log             # 控制台日志（后台跑时用）
    actus/docs/BASELINE_R10H.md                # 报告
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

_HERE = os.path.dirname(os.path.abspath(__file__))
ACTUS = os.path.dirname(_HERE)                      # .../vools/actus
TESTS = os.path.join(ACTUS, "tests")
DOCS = os.path.join(ACTUS, "docs")
RESULTS_JSONL = os.path.join(_HERE, "_baseline_r10h_results.jsonl")
REPORT_MD = os.path.join(DOCS, "BASELINE_R10H.md")

# HANG 清单里待二分定位的文件用 -x 收紧
TAIL_CHARS = 4000


def discover() -> list[str]:
    files = sorted(
        f for f in os.listdir(TESTS)
        if f.startswith("test_") and f.endswith(".py")
    )
    return files


def load_done() -> dict[str, dict]:
    done: dict[str, dict] = {}
    if os.path.exists(RESULTS_JSONL):
        with open(RESULTS_JSONL, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                done[rec["file"]] = rec
    return done


def parse_junit(path: str) -> dict:
    """junitxml 是权威计数：本机 pytest 9.1.1 终端摘要行被吞（stdout 只有进度点），
    按 stdout 解析 "N passed" 不可靠（连裸 probe 文件都没有摘要行）。"""
    suite = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    try:
        root = ET.parse(path).getroot()
        # pytest 9 根是 <testsuites> 内嵌 <testsuite>；旧版/单套件时根即 <testsuite>
        suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
        for ts in suites:
            for k in suite:
                suite[k] += int(ts.attrib.get(k, 0))
    except Exception:
        pass
    suite["passed"] = max(
        0, suite["tests"] - suite["failures"] - suite["errors"] - suite["skipped"])
    return suite


def run_one(fname: str, timeout: int) -> dict:
    # 每文件独立 basetemp：避开系统 %TEMP%\pytest-of-<user>\pytest-current
    # 死联接在 Windows 上收尾 PermissionError(WinError 5) 污染退出码的问题，
    # 同时隔离各文件 tmp_path 互不影响。
    tag = fname[:-3] if fname.endswith(".py") else fname
    base = os.path.join("tools", "_r10h_tmp", tag)
    os.makedirs(base, exist_ok=True)  # pytest 不建 basetemp 根，需预创建
    junit = os.path.abspath(os.path.join("tools", "_r10h_junit", tag + ".xml"))
    os.makedirs(os.path.dirname(junit), exist_ok=True)
    cmd = [sys.executable, "-m", "pytest", os.path.join("tests", fname),
           "-q", "--tb=line", "-p", "no:cacheprovider",
           "--basetemp", base, "--junitxml", junit]
    outpath = os.path.join("tools", "_r10h_out", tag + ".out.txt")
    errpath = os.path.join("tools", "_r10h_out", tag + ".err.txt")
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    t0 = time.time()
    # 输出重定向到文件而非管道：taskkill 杀树后孤儿孙进程会握住管道写端，
    # communicate() 将永久阻塞（R10H 实测驱动因此停摆在 3/199）；文件则杀完即读，永不阻塞。
    with open(outpath, "w", encoding="utf-8", newline="") as fo, \
            open(errpath, "w", encoding="utf-8", newline="") as fe:
        proc = subprocess.Popen(cmd, cwd=ACTUS, stdout=fo, stderr=fe, env=env)
        hung = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            hung = True
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass  # 直属子进程仍未退——不再等，超时本身已是 HANG 证据
    elapsed = round(time.time() - t0, 1)

    def _tail(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read()[-TAIL_CHARS:]
        except OSError:
            return ""

    out, err = _tail(outpath), _tail(errpath)
    counts = parse_junit(junit)
    rc = proc.returncode
    total = counts["tests"]
    # 分类以 junitxml 计数为准；stderr 里的收尾 traceback（如 tmpdir 清理
    # PermissionError）不影响用例结果判定。
    if hung:
        status = "HANG"
    elif counts["failures"]:
        status = "FAIL"
    elif counts["errors"]:
        status = "ERROR"
    elif total == 0:
        # 0 用例：区分「文件本就无用例/全被跳过收集」与「异常退出」
        status = "EMPTY" if rc in (0, 5) else "ERROR"
    elif counts["skipped"] == total and rc in (0, 5):
        status = "PASS"   # 全 skip 视作通过档（不计失败），报告中单列 skipped
    elif rc in (0, 5):
        status = "PASS"
    else:
        status = "ERROR"  # rc=2 中断 / rc=3 内部错误 / rc=4 用法错误等
    rec = {
        "file": fname,
        "status": status,
        "tests": total,
        "counts": counts,
        "seconds": elapsed,
        "returncode": rc,
        "hung": hung,
    }
    if status != "PASS":
        if out:
            rec["out_tail"] = out[-TAIL_CHARS:]
        if err:
            rec["err_tail"] = err[-TAIL_CHARS:]
    return rec


def fmt_result(rec: dict) -> str:
    if rec["status"] == "HANG":
        return "**HANG**(>%.0fs)" % rec["seconds"]
    if rec["status"] == "EMPTY":
        return "no tests"
    c = rec["counts"]
    parts = []
    if c.get("passed"):
        parts.append("passed %d" % c["passed"])
    if c.get("failures"):
        parts.append("**failed %d**" % c["failures"])
    if c.get("errors"):
        parts.append("**error %d**" % c["errors"])
    if c.get("skipped"):
        parts.append("skipped %d" % c["skipped"])
    return ", ".join(parts) or ("rc=%s" % rec["returncode"])


def write_report(records: list[dict], done_all: bool) -> None:
    os.makedirs(DOCS, exist_ok=True)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tot = {"tests": 0, "passed": 0, "failures": 0, "errors": 0,
           "skipped": 0, "seconds": 0.0}
    hangs, fails = [], []
    for r in records:
        for k in ("tests", "passed", "failures", "errors", "skipped"):
            tot[k] += r["counts"].get(k, 0)
        tot["seconds"] += r["seconds"]
        if r["status"] == "HANG":
            hangs.append(r)
        if r["status"] in ("FAIL", "ERROR"):
            fails.append(r)

    lines: list[str] = []
    lines.append("# actus 测试基线复测报告（R10H 统帅轮 · 逐文件驱动）")
    lines.append("")
    lines.append(f"- 生成时间：{now}（{'全量完成' if done_all else '进行中（部分结果）'}）")
    lines.append("- 方法：`actus/tools/_baseline_r10h.py`，每个 `tests/test_*.py` 用独立进程跑")
    lines.append("  `python -m pytest <file> -q --tb=line -p no:cacheprovider --basetemp <独立tmp> --junitxml <独立xml>`，")
    lines.append("  单文件硬超时 300s，超时记 HANG；计数以 junitxml 为准（本机 pytest 9.1.1 终端摘要行被吞，stdout 解析不可靠）。")
    lines.append("- 背景：全量 `python -m pytest -q tests` 10 分钟无输出，本报告定位慢点/挂点。")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 测试文件数 | {len(records)} |")
    lines.append(f"| 总用例数 | {tot['tests']} |")
    lines.append(f"| passed | {tot['passed']} |")
    lines.append(f"| failed | {tot['failures']} |")
    lines.append(f"| error（收集/夹具错误） | {tot['errors']} |")
    lines.append(f"| skipped | {tot['skipped']} |")
    lines.append(f"| HANG 文件数 | {len(hangs)} |")
    lines.append(f"| FAIL/ERROR 文件数 | {len(fails)} |")
    lines.append(f"| 总耗时（驱动侧秒，含进程启动） | {tot['seconds']:.1f}s |")
    lines.append("")

    if hangs:
        lines.append("## HANG 文件清单")
        lines.append("")
        lines.append("| 文件 | 已等待秒 |")
        lines.append("| --- | --- |")
        for r in sorted(hangs, key=lambda x: -x["seconds"]):
            lines.append(f"| `{r['file']}` | {r['seconds']:.0f} |")
        lines.append("")

    if fails:
        lines.append("## FAIL/ERROR 文件清单")
        lines.append("")
        lines.append("| 文件 | 结果 |")
        lines.append("| --- | --- |")
        for r in fails:
            lines.append(f"| `{r['file']}` | {fmt_result(r)} |")
        lines.append("")

    slow = sorted(records, key=lambda x: -x["seconds"])[:10]
    lines.append("## 最慢 10 文件")
    lines.append("")
    lines.append("| 文件 | 秒 | 结果 |")
    lines.append("| --- | --- | --- |")
    for r in slow:
        lines.append(f"| `{r['file']}` | {r['seconds']:.1f} | {fmt_result(r)} |")
    lines.append("")

    lines.append("## 全文件清单")
    lines.append("")
    lines.append("| 文件 | 用例数 | 秒 | 结果 |")
    lines.append("| --- | --- | --- | --- |")
    for r in records:
        lines.append(f"| `{r['file']}` | {r['tests']} | {r['seconds']:.1f} | {fmt_result(r)} |")
    lines.append("")

    # 诊断节由人工/后续轮补写，占位保留
    lines.append("## 失败诊断")
    lines.append("")
    lines.append("（见报告末尾追加的诊断记录）")
    lines.append("")

    with open(REPORT_MD, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated file names to run")
    ap.add_argument("--rerun", action="store_true", help="ignore existing results")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    files = discover()
    only = [s.strip() for s in args.only.split(",") if s.strip()]
    if only:
        files = [f for f in files if f in only]

    done = {} if args.rerun else load_done()
    todo = [f for f in files if f not in done]
    records = [done[f] for f in files if f in done]
    total_start = time.time()
    print(f"[baseline-r10h] files={len(files)} already_done={len(records)} todo={len(todo)}", flush=True)

    for i, fname in enumerate(todo, 1):
        print(f"[baseline-r10h] ({i}/{len(todo)}) {fname} ...", flush=True)
        t0 = time.time()
        try:
            rec = run_one(fname, args.timeout)
        except Exception as exc:  # driver 自己别死
            rec = {"file": fname, "status": "DRIVER_ERROR", "tests": 0,
                   "counts": {}, "seconds": round(time.time() - t0, 1),
                   "returncode": -1, "hung": False,
                   "out_tail": repr(exc)[-TAIL_CHARS:]}
        records.append(rec)
        with open(RESULTS_JSONL, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[baseline-r10h]   -> {rec['status']} tests={rec['tests']} "
              f"{rec['seconds']}s", flush=True)
        # 每个文件跑完即重写报告，防中断丢证据
        write_report(records, done_all=False)

    write_report(records, done_all=len(todo) == len(files))
    wall = time.time() - total_start
    print(f"[baseline-r10h] DONE wall={wall:.1f}s files={len(records)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
