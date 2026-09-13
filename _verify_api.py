"""验证所有 vools API 可用性"""
import sys

results = []

def check(name, func):
    try:
        func()
        results.append((name, True, None))
        print(f"  OK  {name}")
    except Exception as e:
        results.append((name, False, str(e)))
        print(f"  FAIL {name}: {e}")

print("=== 核心 API ===")
import vools
check("version", lambda: print(f"vools {vools.__version__}"))
check("memorize", lambda: vools.memorize)
check("curry", lambda: vools.curry)
check("Seq", lambda: vools.Seq)
check("Pipe", lambda: vools.Pipe)
check("Box", lambda: vools.Box)
check("stuff", lambda: vools.stuff)
check("overload", lambda: vools.overload)
check("retry", lambda: vools.retry)
check("safe_eval", lambda: vools.safe_eval("1 + 2"))

print("\n=== 数据 API ===")
check("data.Table", lambda: vools.data.Table)
check("data.Seq", lambda: vools.data.Seq)
check("data.Itor", lambda: vools.data.Itor)
check("data.VList", lambda: vools.VList)
check("data.VText", lambda: vools.VText)

print("\n=== 日期 API ===")
check("datetime.vDate", lambda: vools.vDate)
check("datetime.VDate", lambda: vools.VDate)

print("\n=== OOP API ===")
check("oop.Selector", lambda: vools.Selector)
check("oop.Mixer", lambda: vools.Mixer)
check("oop.derive", lambda: vools.derive)
check("oop.create_derive", lambda: vools.create_derive)
check("oop.clone", lambda: vools.clone)

print("\n=== Markdown API ===")
check("md.parse", lambda: vools.md.parse)
check("md.generate", lambda: vools.md.generate)
check("md.to_html", lambda: vools.md.to_html)
check("md.extract_metadata", lambda: vools.md.extract_metadata)
check("md.generate_toc", lambda: vools.md.generate_toc)

print("\n=== 编码/加密 API ===")
check("encoding.b64encode", lambda: vools.b64encode(b"hello"))
check("crypto.md5", lambda: vools.md5(b"hello"))
check("crypto.sha256", lambda: vools.sha256(b"hello"))

print("\n=== 子包 API ===")
check("bridge", lambda: vools.bridge)
check("reactive", lambda: vools.reactive)
check("dll32", lambda: vools.dll32)
check("xl", lambda: vools.xl)

print("\n=== 桥接语言 ===")
check("bridge.nim", lambda: vools.bridge.nim)
check("bridge.rust", lambda: vools.bridge.rust)
check("bridge.md", lambda: vools.bridge.md)
check("bridge.cypy", lambda: vools.bridge.cypy)
check("bridge.tnr", lambda: vools.bridge.tnr)
check("bridge.lz", lambda: vools.bridge.lz)
check("bridge.zi", lambda: vools.bridge.zi)

print("\n=== 功能验证 ===")
def test_seq():
    s = vools.Seq([1, 2, 3])
    assert s.map(lambda x: x * 2).collect() == [2, 4, 6]
check("Seq.map", test_seq)

def test_curry():
    @vools.curry
    def add(a, b, c):
        return a + b + c
    assert add(1)(2)(3) == 6
check("curry", test_curry)

def test_md_parse():
    doc = vools.md.parse("# Hello\n\nWorld")
    assert len(doc.children) > 0
check("md.parse", test_md_parse)

def test_table():
    t = vools.data.Table([[1, 2], [3, 4]], columns=['a', 'b'])
    assert t.rows() == 2
check("Table", test_table)

print("\n" + "=" * 50)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f"总计: {len(results)} 项, 通过: {passed}, 失败: {failed}")
if failed > 0:
    print("\n失败项:")
    for name, ok, err in results:
        if not ok:
            print(f"  - {name}: {err}")
    sys.exit(1)
else:
    print("全部 API 验证通过!")
