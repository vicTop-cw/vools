"""合规检查：__all__ 完整性和 README 覆盖率"""
import os
import sys

errors = 0

# 1. __all__ 检查
print("=" * 50)
print("检查 __all__ 完整性...")
missing_all = []
for r, dirs, files in os.walk("vools"):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".pytest_cache", "Temp")]
    for f in files:
        if not f.endswith(".py") or f == "__init__.py":
            continue
        fpath = os.path.join(r, f)
        content = open(fpath, encoding="utf-8").read()
        if "__all__" not in content:
            rel = os.path.relpath(fpath, "vools").replace("\\", "/")
            missing_all.append(rel)
if missing_all:
    print(f"缺失 __all__: {len(missing_all)}")
    for m in sorted(missing_all):
        print(f"  {m}")
    errors += len(missing_all)
else:
    print("[OK] 所有文件均有 __all__")

# 2. README 检查
print()
print("=" * 50)
print("检查 README 覆盖率...")
pkg_dirs = set()
for r, dirs, files in os.walk("vools"):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".pytest_cache", "Temp")]
    if "__init__.py" in files:
        rel = os.path.relpath(r, "vools").replace("\\", "/")
        pkg_dirs.add(rel)
missing_readme = []
for p in sorted(pkg_dirs):
    readme_path = os.path.join("vools", p, "README.md")
    if not os.path.exists(readme_path):
        missing_readme.append(p)
print(f"总子包数: {len(pkg_dirs)}")
if missing_readme:
    print(f"缺失 README.md: {len(missing_readme)}")
    for m in missing_readme:
        print("  MISS: %s/" % m)
    errors += len(missing_readme)
else:
    print("[OK] 所有子包均有 README.md")

summary = "\n" + "=" * 50
if errors:
    print(f"{summary}\n[FAIL] {errors} 个问题待修复")
else:
    print(f"{summary}\n[OK] 全部合规检查通过！")
sys.exit(errors)
