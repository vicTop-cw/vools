from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
VOOLS = ROOT / "vools"

def is_binary(p: Path) -> bool:
    return p.suffix in (".dll", ".so", ".exe", ".pyd")

def size_of(path: Path) -> tuple[int, int]:
    """返回 (代码大小, 二进制大小)"""
    if path.is_file():
        s = path.stat().st_size
        return (0, s) if is_binary(path) else (s, 0)
    code, binary = 0, 0
    for p in path.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        s = p.stat().st_size
        if is_binary(p):
            binary += s
        else:
            code += s
    return code, binary

def fmt(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.2f} MB"
    return f"{n / 1024:.2f} KB"

items = []
for p in sorted(VOOLS.iterdir()):
    if p.is_dir() and not p.name.startswith("__") and (p / "__init__.py").exists():
        code, binary = size_of(p)
        items.append((p.name, code, binary))
    elif p.is_file() and p.suffix == ".py":
        code, binary = size_of(p)
        items.append((p.name, code, binary))

items.sort(key=lambda x: -(x[1] + x[2]))

print(f"{'module':<16} {'code':>10} {'binary':>10} {'total':>10}")
print("-" * 50)
total_code = total_binary = 0
for name, code, binary in items:
    print(f"{name:<16} {fmt(code):>10} {fmt(binary):>10} {fmt(code+binary):>10}")
    total_code += code
    total_binary += binary
print("-" * 50)
print(f"{'total':<16} {fmt(total_code):>10} {fmt(total_binary):>10} {fmt(total_code+total_binary):>10}")

# 重复 lib 分析
print("\n\n重复的二进制文件分析:")
by_name = defaultdict(list)
for f in VOOLS.rglob("*"):
    if f.is_file() and is_binary(f):
        by_name[f.name].append((f, f.stat().st_size))

dup_total = 0
for name, entries in sorted(by_name.items()):
    if len(entries) > 1:
        print(f"\n{name}: {len(entries)} 处")
        for f, s in entries:
            print(f"  {s/1024/1024:.2f} MB  {f}")
        dup_total += sum(s for _, s in entries[1:])
print(f"\n重复导致的额外体积: {dup_total/1024/1024:.2f} MB")
