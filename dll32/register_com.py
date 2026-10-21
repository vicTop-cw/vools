# -*- coding: utf-8 -*-
"""把 dll32/_dlls 下的 COM DLL 注册到本机（解决部署移植性）。

背景：
    vbRichClient5.dll 是 32 位 COM DLL，`win32com.EnsureDispatch` /
    `CoCreateInstance` 都依赖注册表里的 ProgID -> CLSID -> InprocServer32。
    本机当前注册的 InprocServer32 指向外部目录 E:\\vb\\VB6Mini\\lib\\vbRichClient\\，
    一旦该目录不存在（换机器/重装），dll32 自带的 _dlls/vbRichClient5.dll 虽在，
    却不会被 COM 加载——这就是"打包带走了 DLL 但跑不起来"的移植性问题。

用法（需管理员权限，且必须用 32 位 Python）：
    dll32/vools/dll32/_python32/python.exe dll32/register_com.py
    dll32/vools/dll32/_python32/python.exe dll32/register_com.py --check

注意：
    只能由 32 位进程注册 32 位 DLL。用 64 位 Python 跑 regsvr32 会注册到
    WOW6432Node 之外的视图，反而让 32 位客户端找不到。
"""
import os
import sys
import ctypes
import argparse

# 需注册的 COM DLL（顺序无关，但依赖 DLL 建议先注册）
COM_DLLS = (
    'vbRichClient5.dll',
    'RC6.dll',
    'RC6Widgets.dll',
    'DirectCOM.dll',
)


def _dlls_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, '_dlls')


def is_32bit_python() -> bool:
    """当前进程是否 32 位。"""
    return ctypes.sizeof(ctypes.c_void_p) == 4


def register_dll(path: str) -> bool:
    """调用 DLL 的 DllRegisterServer（等价 regsvr32 /s）。"""
    if not os.path.exists(path):
        print('  [跳过] 不存在: {}'.format(path))
        return False
    try:
        mod = ctypes.WinDLL(path)
        entry = getattr(mod, 'DllRegisterServer', None)
        if entry is None:
            print('  [跳过] 无 DllRegisterServer 导出: {}'.format(os.path.basename(path)))
            return False
        hr = entry()
        # S_OK = 0, S_FALSE = 1（已注册过也视为成功）
        if hr in (0, 1):
            print('  [OK] {}'.format(os.path.basename(path)))
            return True
        print('  [失败] {} HRESULT=0x{:08X}'.format(os.path.basename(path), hr & 0xFFFFFFFF))
        return False
    except OSError as e:
        print('  [失败] {} : {}'.format(os.path.basename(path), e))
        return False


def check_progid(prog_id: str) -> str:
    """读注册表里 ProgID 的 InprocServer32（WOW6432Node 视图）。"""
    import winreg
    for hive, sub in (
        (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Classes\{}\CLSID'.format(prog_id)),
        (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Classes\{}\CLSID'.format(prog_id)),
    ):
        try:
            with winreg.OpenKey(hive, sub) as k:
                clsid, _ = winreg.QueryValueEx(k, None)
            for hive2, sub2 in (
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Classes\CLSID\{}\InprocServer32'.format(clsid)),
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Classes\CLSID\{}\InprocServer32'.format(clsid)),
            ):
                try:
                    with winreg.OpenKey(hive2, sub2) as k2:
                        path, _ = winreg.QueryValueEx(k2, None)
                        return path
                except FileNotFoundError:
                    continue
            return '<CLSID {} 已注册但读不到 InprocServer32>'.format(clsid)
        except FileNotFoundError:
            continue
    return '<未注册>'


def main() -> int:
    ap = argparse.ArgumentParser(description='注册 dll32/_dlls 下的 COM DLL')
    ap.add_argument('--check', action='store_true', help='只检查注册状态，不注册')
    args = ap.parse_args()

    if not is_32bit_python():
        print('错误: 必须用 32 位 Python 运行（当前 {} 位）。'.format(
            64 if ctypes.sizeof(ctypes.c_void_p) == 8 else 32))
        print('请用: dll32/vools/dll32/_python32/python.exe {}'.format(__file__))
        return 2

    dlls = _dlls_dir()
    print('DLL 目录:', dlls)

    if args.check:
        print('\n=== 注册状态检查 ===')
        for name in COM_DLLS:
            path = os.path.join(dlls, name)
            exists = '存在' if os.path.exists(path) else '缺失'
            print('{:24s} [{}]'.format(name, exists))
        for prog in ('vbRichClient5.cConstructor', 'RC6.cRC6'):
            print('{:24s} -> {}'.format(prog, check_progid(prog)))
        return 0

    print('\n=== 开始注册（需管理员权限）===')
    ok = 0
    for name in COM_DLLS:
        if register_dll(os.path.join(dlls, name)):
            ok += 1
    print('\n注册完成: {}/{} 成功'.format(ok, len(COM_DLLS)))
    return 0 if ok == len(COM_DLLS) else 1


if __name__ == '__main__':
    sys.exit(main())
