"""sandbox 隔离细则（docs/07 §5）。

范围与边界（诚实声明）：
- 本模块提供**尽力而为**的进程级隔离，不是操作系统级强制沙箱
  （完整方案需要 Job Object / containers / seccomp，见 docs/09 §7 后续路线）；
- 当前保证：独立 jail 根目录（artifacts/_sandbox/<exec_id>/）、文件路径
  越界校验工具、块级超时、子进程资源限额（Windows Job Object 内存上限 /
  POSIX rlimit，可用即启用）；
- 动作代码通过环境变量获得 jail 根，越界写由 actus.guard 帮助函数拦截；
  直接调用 os API 的裸代码不受强制（这是"尽力而为"的边界）。

用法（执行核心集成）：
    root = sandbox.prepare(meta_dir, artifacts_dir, exec_id)
    env = sandbox.sandbox_env(root)
    # executor 在 sandbox 策略下用 root 作为 build_dir/workdir 并注入 env
"""

__all__ = ['prepare', 'sandbox_env', 'guard_write', 'cleanup', 'JOB_LIMITS']

import os
import shutil

# Windows Job Object 内存上限（字节）：512MB；POSIX 同样应用于 RLIMIT_AS
JOB_LIMITS = {'memory_bytes': 512 * 1024 * 1024, 'cpu_seconds': 60}


def prepare(artifacts_dir: str, exec_id: str) -> str:
    """创建沙箱 jail 根：artifacts/_sandbox/<exec_id>/（docs/07 §5）。"""
    root = os.path.join(artifacts_dir, '_sandbox', exec_id)
    os.makedirs(root, exist_ok=True)
    return root


def sandbox_env(root: str) -> dict:
    """注入沙箱环境变量（动作代码可读，guard 函数依赖 ACTUS_SANDBOX_ROOT）。"""
    return {
        'ACTUS_SANDBOX': '1',
        'ACTUS_SANDBOX_ROOT': root,
        'TMPDIR': root,          # POSIX
        'TEMP': root,            # Windows
        'TMP': root,
    }


def guard_write(path: str, root: str = None) -> str:
    """路径校验：写目标必须位于沙箱根内（docs/07 §5 越界写拦截）。

    返回规范化后的绝对路径；越界抛 PermissionError。
    root 缺省取环境变量 ACTUS_SANDBOX_ROOT；未启用沙箱时直接放行。
    """
    if root is None:
        root = os.environ.get('ACTUS_SANDBOX_ROOT')
        if not root:
            return os.path.abspath(path)
    root_abs = os.path.abspath(root)
    target = os.path.abspath(path)
    if os.path.commonpath([target, root_abs]) != root_abs:
        raise PermissionError(
            f'sandbox 越界写被拒绝: {target} 不在沙箱根 {root_abs} 内（docs/07 §5）')
    return target


def _apply_windows_job(proc) -> bool:
    """Windows Job Object：内存上限。成功返回 True。"""
    try:
        import ctypes
        from ctypes import wintypes

        # 完整结构体定义（布局必须与 winbase.h 一致）
        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in
                        ('ReadOperationCount', 'WriteOperationCount',
                         'OtherOperationCount', 'ReadTransferCount',
                         'WriteTransferCount', 'OtherTransferCount')]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('PerProcessUserTimeLimit', ctypes.c_longlong),
                ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.POINTER(wintypes.ULONG)),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD),
            ]

        class JOB_INFO(ctypes.Structure):
            _fields_ = [
                ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ('IoInfo', IO_COUNTERS),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
        kernel32 = ctypes.windll.kernel32
        hjob = kernel32.CreateJobObjectW(None, None)
        if not hjob:
            return False

        info = JOB_INFO()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY
        info.ProcessMemoryLimit = JOB_LIMITS['memory_bytes']
        if not kernel32.SetInformationJobObject(
                hjob, 9, ctypes.byref(info), ctypes.sizeof(info)):  # JobObjectExtendedLimitInformation
            return False
        return bool(kernel32.AssignProcessToJobObject(
            hjob, int(proc._handle)))
    except Exception:
        return False


def _apply_posix_limits() -> bool:
    """POSIX rlimit：地址空间 + CPU 秒。成功返回 True。"""
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (
            JOB_LIMITS['memory_bytes'], resource.RLIM_INFINITY))
        resource.setrlimit(resource.RLIMIT_CPU, (
            JOB_LIMITS['cpu_seconds'], JOB_LIMITS['cpu_seconds'] + 5))
        return True
    except Exception:
        return False


def apply_limits(proc=None) -> bool:
    """尽力应用资源限额：Windows 用 Job Object，POSIX 用 rlimit。"""
    if os.name == 'nt':
        return _apply_windows_job(proc) if proc is not None else False
    return _apply_posix_limits()


def cleanup(artifacts_dir: str, exec_id: str, keep: bool = False) -> None:
    """沙箱回收：默认删除 jail 根（结果已留痕 _meta/runs）；keep=True 保留审计。"""
    if keep:
        return
    root = os.path.join(artifacts_dir, '_sandbox', exec_id)
    shutil.rmtree(root, ignore_errors=True)
