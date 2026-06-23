"""
build_nim.py - 编译所有 Nim 源文件为 DLL，复制到 vools/lib/
需要 Nim 编译器 + MinGW GCC（Windows）
"""
import os
import shutil
import subprocess
import sys

NIM_CORE = os.path.join(os.path.dirname(__file__), 'nim_core')
LIB_DIR = os.path.join(os.path.dirname(__file__), 'vools', 'lib')

# 候选 MinGW 路径（按优先级）
MINGW_PATHS = [
    r"C:\Users\victo\.codearts-cpp\tools\mingw\bin",
    r"E:\Dowloads\nim-2.2.10_x64\nim-2.2.10\bin",
]

# 候选 Nim 路径
NIM_PATHS = [
    r"E:\Dowloads\nim-2.2.10_x64\nim-2.2.10\bin\nim.exe",
    "nim",
]


def find_tool(name, candidates):
    for c in candidates:
        if os.path.isabs(c) and os.path.exists(c):
            return c
        # 试 PATH
        try:
            r = subprocess.run([c, '--version'], capture_output=True, timeout=5)
            if r.returncode == 0:
                return c
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    return None


def main():
    os.makedirs(LIB_DIR, exist_ok=True)

    nim = find_tool('nim', NIM_PATHS)
    if nim is None:
        print('[ERROR] Nim compiler not found.')
        print('Set NIM_PATHS in build_nim.py or add nim to PATH.')
        return 1

    print(f'[INFO] Using Nim: {nim}')

    sources = [
        'vools_crypto.nim',
        'vools_encoding.nim',
        'vools_seq.nim',
        'vools_datetime.nim',
        'vools_curried.nim',
    ]

    failed = []
    for src in sources:
        out_dll = os.path.splitext(src)[0] + '.dll'
        print(f'\n[BUILD] {src} -> {out_dll}')
        cmd = [
            nim, 'c',
            '--app:lib',
            f'--out:{out_dll}',
            '--passL:-Wl,--export-all',
            '-d:release',
            src,
        ]
        r = subprocess.run(cmd, cwd=NIM_CORE, capture_output=True, text=True)
        if r.returncode != 0:
            print(f'[FAIL] {src}')
            print(r.stdout[-2000:] if r.stdout else '')
            print(r.stderr[-2000:] if r.stderr else '')
            failed.append(src)
            continue
        src_dll = os.path.join(NIM_CORE, out_dll)
        if not os.path.exists(src_dll):
            print(f'[FAIL] {src}: output not found')
            failed.append(src)
            continue
        dest_dll = os.path.join(LIB_DIR, out_dll)
        shutil.copy2(src_dll, dest_dll)
        print(f'[OK] {src} -> {dest_dll} ({os.path.getsize(dest_dll)} bytes)')

    if failed:
        print(f'\n[ERROR] {len(failed)} source(s) failed: {failed}')
        return 1

    print(f'\n[SUCCESS] Built {len(sources)} DLL(s) in {LIB_DIR}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
