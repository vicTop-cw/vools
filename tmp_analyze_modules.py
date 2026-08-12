import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VOOLS = ROOT / "vools"

def size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for p in path.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            total += p.stat().st_size
    return total

def fmt(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.2f} MB"
    return f"{n / 1024:.2f} KB"

items = []
for p in sorted(VOOLS.iterdir()):
    if p.is_dir() and not p.name.startswith("__") and (p / "__init__.py").exists():
        items.append((p.name, size_of(p)))
    elif p.is_file() and p.suffix == ".py":
        items.append((p.name, size_of(p)))

items.sort(key=lambda x: -x[1])

print(f"{'module':<20} {'size':>12}")
print("-" * 34)
for name, s in items:
    print(f"{name:<20} {fmt(s):>12}")

print("-" * 34)
print(f"{'total dirs':<20} {fmt(sum(s for _, s in items)):>12}")
