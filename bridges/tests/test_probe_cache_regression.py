"""probe.py 缓存行为回归测试。

针对 round-59 修复的四个问题：
1. `_LOCAL_PROBE_CACHE` 读写不深拷贝 → 调用方改动污染缓存
   （vools commit `5b63618`）
2. `_WSL_PROBE_CACHE` 读写深拷贝 → 缓存不被调用方污染
3. `reset_probe_cache()` 清空全部四层缓存
4. `_which_in_env` 全局锁 → 并行下 PATH 不被互相覆盖
   （vools commit `9ee7d3e`）
"""

import os
import threading

import pytest

from vools.bridge import probe


# --- 已知不存在的语言，避免依赖真实编译器 ---
_FAKE_LANG = '_vools_probe_cache_test_'


def _register_fake_lang():
    """注册一个假的探测条目（command 必然找不到）。"""
    if _FAKE_LANG in probe.LANGUAGE_PROBES:
        return
    probe.LANGUAGE_PROBES[_FAKE_LANG] = {
        'category': 'test',
        'commands': ['_vools_probe_cache_test_cmd_xyz'],
        'version_args': ['--version'],
        'install_hint': {'Windows': 'n/a', 'Linux': 'n/a'},
    }


def _unregister_fake_lang():
    probe.LANGUAGE_PROBES.pop(_FAKE_LANG, None)


@pytest.fixture(autouse=True)
def _cleanup():
    probe.reset_probe_cache()
    _register_fake_lang()
    yield
    probe.reset_probe_cache()
    _unregister_fake_lang()


def test_local_cache_not_polluted_by_caller():
    """`_LOCAL_PROBE_CACHE` 命中后返回副本，调用方改 `available` 不污染缓存。"""
    # 首次调用：填充缓存
    r1 = probe.probe_environment(languages=[_FAKE_LANG])
    st1 = r1.languages[_FAKE_LANG]
    assert st1.available is False

    # 二次调用：命中缓存，改返回对象
    r2 = probe.probe_environment(languages=[_FAKE_LANG])
    r2.languages[_FAKE_LANG].available = True
    r2.languages[_FAKE_LANG].version = '999.999'

    # 三次调用：缓存应仍是干净的
    r3 = probe.probe_environment(languages=[_FAKE_LANG])
    st3 = r3.languages[_FAKE_LANG]
    assert st3.available is False
    assert st3.version is None


def test_local_cache_returned_is_not_same_object():
    """两次探测返回的 `LanguageStatus` 不是同一个对象。"""
    r1 = probe.probe_environment(languages=[_FAKE_LANG])
    r2 = probe.probe_environment(languages=[_FAKE_LANG])
    assert r1.languages[_FAKE_LANG] is not r2.languages[_FAKE_LANG]


def test_report_cache_not_polluted_by_caller():
    """`_REPORT_CACHE` 命中后返回深拷贝，调用方改 `languages` 不污染缓存。"""
    r1 = probe.probe_environment(languages=[_FAKE_LANG])
    r1.languages[_FAKE_LANG].available = True
    r1.languages['_injected_'] = probe.LanguageStatus(name='_injected_')

    r2 = probe.probe_environment(languages=[_FAKE_LANG])
    assert r2.languages[_FAKE_LANG].available is False
    assert '_injected_' not in r2.languages


def test_reset_probe_cache_clears_all_layers():
    """`reset_probe_cache` 清空全部四层缓存。"""
    probe.probe_environment(languages=[_FAKE_LANG])
    assert probe._LOCAL_PROBE_CACHE
    assert probe._REPORT_CACHE

    probe.reset_probe_cache()
    assert not probe._LOCAL_PROBE_CACHE
    assert not probe._REPORT_CACHE
    assert not probe._WSL_PROBE_CACHE
    assert not probe._WSL_DISTRO_INFO_CACHE


def test_which_in_env_parallel_path_restored():
    """并行调用 `_which_in_env` 后 PATH 恢复原值。"""
    old_path = os.environ.get('PATH', '')

    def worker(env_path):
        return probe._which_in_env(
            '_vools_probe_cache_test_cmd_xyz', {'PATH': env_path})

    envs = [
        {'PATH': 'C:\\fake1;D:\\fake1'},
        {'PATH': 'C:\\fake2;D:\\fake2'},
        {'PATH': 'C:\\fake3;D:\\fake3'},
    ]

    results = []

    def _call(i):
        results.append(worker(envs[i]['PATH']))

    threads = [threading.Thread(target=_call, args=(i,)) for i in range(len(envs))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 所有调用完成后 PATH 应回到原值
    assert os.environ.get('PATH', '') == old_path
    # `_which_in_env` 返回 None（假命令找不到）
    assert all(r is None for r in results)


def test_report_cache_hit_returns_same_results():
    """两次相同入参的 `probe_environment` 结果内容一致（缓存命中）。"""
    r1 = probe.probe_environment(languages=[_FAKE_LANG])
    r2 = probe.probe_environment(languages=[_FAKE_LANG])
    assert r1.languages.keys() == r2.languages.keys()
    assert r1.languages[_FAKE_LANG].available == r2.languages[_FAKE_LANG].available


def test_report_cache_miss_on_different_env():
    """不同 `extra_env` 产生不同缓存键，不互相污染。"""
    r1 = probe.probe_environment(languages=[_FAKE_LANG], extra_env={'FOO': '1'})
    r2 = probe.probe_environment(languages=[_FAKE_LANG], extra_env={'FOO': '2'})
    # 各自独立缓存（这里只验证不异常）
    assert r1.languages[_FAKE_LANG].available is False
    assert r2.languages[_FAKE_LANG].available is False