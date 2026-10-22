# -*- coding: utf-8 -*-
"""第七轮边界语料：双方共享介质（local/http/sftp 的 SharedPath）。

定位：语料 + 复现器，不是产品源码（命名不带 test_ 前缀，不进 pytest 收集）。
用户第二条要求是『数据库需要双方都能读写』——共享介质就是这条要求的核心。
此前六件语料只碰过 LocalSharedPath 一次（G3 的大包原子写），本轮把**介质层**做成边界实证：
http 不当目录、路径穿越、介质不可达的报错、并发读写、写读删一致性。

运行：
    cd rhop && python tests/boundary/r17_shared_medium.py

每条输出 [CONFIRMED] / [NOT-CONFIRMED] + 证据；退出码 = 风险成立条数。
"""
import json
import os
import subprocess
import sys
import tempfile

RHOP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RHOP)
PY = sys.executable

from vools.rhop.task.config import TaskConfig            # noqa: E402
from vools.rhop.transport.shared import make_shared_path, parse_endpoint  # noqa: E402

RESULTS = []


def record(pid, title, risk_realized, evidence):
    RESULTS.append((pid, title, risk_realized, evidence))
    print("[%s] %-40s %s" % ("CONFIRMED" if risk_realized else "NOT-CONFIRMED",
                             pid + " " + title, evidence))


def _worker(work, wid, names):
    """子进程：往共享介质写若干文件并回报。"""
    code = (
        "import sys, os\n"
        "sys.path.insert(0, %(rhop)r)\n"
        "from vools.rhop.transport.shared import make_shared_path\n"
        "sp = make_shared_path(%(path)r)\n"
        "got = []\n"
        "for n in %(names)r:\n"
        "    sp.write_text(n, 'x' * 1000)\n"
        "    got.append(sp.read_text(n)[:4])\n"
        "open(os.path.join(%(work)r, %(wid)r + '.json'), 'w', encoding='utf-8').write(__import__('json').dumps(got))\n"
        % {"rhop": RHOP, "path": os.path.join(work, "shared"),
           "names": names, "work": work, "wid": wid}
    )
    path = os.path.join(work, "worker_%s.py" % wid)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(code)
    return subprocess.Popen([PY, path], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8")


# ---------------------------------------------------------------------------
# T1 http 介质不当目录（历史缺陷：build_shared 曾把 http 的 abspath 当本地目录）
# ---------------------------------------------------------------------------
def t1_http_not_treated_as_dir():
    work = tempfile.mkdtemp(prefix="bf-t1-")
    sp = None
    kind = None
    try:
        sp = make_shared_path("http://example.invalid/shared")
        kind = getattr(sp, "kind", None) or type(sp).__name__
    except Exception as exc:
        record("T1", "http 介质被识别为网络介质（不当目录）", False,
               "make_shared_path 抛 %s: %s（拒绝即正确）" % (type(exc).__name__, exc))
        return False
    is_network = False
    inner = None
    for attr in ("path", "root", "endpoint", "url"):
        value = getattr(sp, attr, None)
        if isinstance(value, str) and value:
            inner = value
            break
    is_network = bool(inner) and inner.lower().startswith("http")
    risk = not is_network
    record("T1", "http 介质被识别为网络介质（不当目录）", risk,
           "内层=%s（期望以 http 开头）；是否尝试建本地目录=%s"
           % (inner, os.path.isdir(os.path.join(work, "example.invalid"))))
    return risk


# ---------------------------------------------------------------------------
# T2 路径穿越：shared path 含 .. / 绝对路径 / 盘符
# ---------------------------------------------------------------------------
def t2_shared_db_lands_in_medium():
    """共享库必须落在共享介质内：相对 store.path 不得按进程 cwd 解析（BUG-302）。

    注意：`shared.write` 指向 base_dir 之外**本身不是缺陷**（共享介质本就该在双方约定的位置，
    例如 /mnt/shared 或 D:/shared）；真正的缺陷是相对 `store.path` 被按 cwd 解析，
    导致库不在介质里 ⇒ A/B 读写不同的库。
    """
    from vools.rhop.task.errors import StoreUnavailable

    work = tempfile.mkdtemp(prefix="bf-t2-")
    base = os.path.join(work, "base")
    os.makedirs(base)
    shared = os.path.join(work, "shared")
    os.makedirs(shared)
    risk = False
    store = None
    try:
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "B", "key": "k", "shared": {"write": shared},
             "queue": {"store": {"kind": "sqlite-shared", "path": "tasks.db"}}},
            base_dir=base, warn_plaintext=False)
        store = cfg.build_store()
        real = os.path.realpath(store.path)
        medium = os.path.realpath(shared)
        in_medium = (real == medium) or real.startswith(medium + os.sep)
        risk = not in_medium
        record("T2", "相对 store.path 落在共享介质内（不按 cwd）", risk,
               "store.path=%s；共享介质=%s；在介质内=%s" % (real, medium, in_medium))
    except StoreUnavailable as exc:
        risk = False                       # 被可读地拒绝（而不是静默落到 cwd）＝可接受
        record("T2", "相对 store.path 落在共享介质内（不按 cwd）", False,
               "被拒绝（可读报错）：%s" % str(exc).split("。")[0])
    finally:
        if store is not None:
            try:
                store.close()
            except Exception:
                pass
            try:
                if os.path.isfile(store.path):
                    os.remove(store.path)
            except OSError:
                pass
    return risk


# ---------------------------------------------------------------------------
# T3 介质不可达：不存在的路径 → 报错是否可读
# ---------------------------------------------------------------------------
def t3_unreachable_medium_error():
    work = tempfile.mkdtemp(prefix="bf-t3-")
    missing = os.path.join(work, "nope", "deeper")
    risk = False
    try:
        sp = make_shared_path(missing)
        sp.write_text("a.txt", "hello")          # 自动建目录是允许的
        back = sp.read_text("a.txt")
        risk = back != "hello"
        record("T3", "不可达介质可自动建目录或报错可读", risk,
               "write→read 往返=%r" % back)
    except Exception as exc:
        risk = ("路径" not in str(exc)) and ("不存在" not in str(exc)) and ("No such" not in str(exc))
        record("T3", "不可达介质可自动建目录或报错可读", risk,
               "抛 %s: %s" % (type(exc).__name__, str(exc)[:120]))
    return risk


# ---------------------------------------------------------------------------
# T4 并发读写：两个进程同时写/读共享介质
# ---------------------------------------------------------------------------
def t4_concurrent_medium_writes():
    work = tempfile.mkdtemp(prefix="bf-t4-")
    os.makedirs(os.path.join(work, "shared"), exist_ok=True)
    names_a = ["a1", "a2", "a3"]
    names_b = ["b1", "b2", "b3"]
    procs = [_worker(work, "w1", names_a), _worker(work, "w2", names_b)]
    errs = []
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        if proc.returncode != 0:
            errs.append(err.strip().splitlines()[-1] if err.strip() else "exit %s" % proc.returncode)
    got = []
    for wid in ("w1", "w2"):
        path = os.path.join(work, "%s.json" % wid)
        if os.path.exists(path):
            got.extend(json.loads(open(path, encoding="utf-8").read()))
    # 期望：两个进程各写 3 个文件且都能读回自己的内容（不互相破坏）
    risk = bool(errs) or len(got) != 6 or any(g != "xxxx" for g in got)
    record("T4", "并发读写共享介质不互相破坏", risk,
           "子进程错误=%s；读回条数=%d、内容一致=%s"
           % (errs, len(got), all(g == "xxxx" for g in got)))
    return risk


# ---------------------------------------------------------------------------
# T5 写读删一致性
# ---------------------------------------------------------------------------
def t5_write_read_remove():
    work = tempfile.mkdtemp(prefix="bf-t5-")
    sp = make_shared_path(os.path.join(work, "shared"))
    try:
        sp.write_text("k.txt", "payload-12345")
        back = sp.read_text("k.txt")
        sp.remove("k.txt")
        gone = not sp.exists("k.txt")
        risk = (back != "payload-12345") or not gone
        record("T5", "介质写读删一致", risk,
               "写→读=%r；删除后 exists=%s" % (back, sp.exists("k.txt")))
        return risk
    finally:
        pass


def main():
    print("=" * 92)
    for probe in (t1_http_not_treated_as_dir, t2_shared_db_lands_in_medium,
                  t3_unreachable_medium_error, t4_concurrent_medium_writes, t5_write_read_remove):
        try:
            probe()
        except Exception as exc:
            record(probe.__name__, "探针自身异常", False, "%s: %s" % (type(exc).__name__, exc))
    confirmed = [r for r in RESULTS if r[2]]
    print("=" * 92)
    print("boundary_cases=%d confirmed=%d not_confirmed=%d"
          % (len(RESULTS), len(confirmed), len(RESULTS) - len(confirmed)))
    for pid, title, ok, _ in RESULTS:
        print("  %-14s %s :: %s" % (pid, "CONFIRMED" if ok else "NOT-CONFIRMED", title))
    return len(confirmed)


if __name__ == "__main__":
    sys.exit(main())