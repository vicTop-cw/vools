"""
核心层重构测试：CompileMode, LangType, CompileTracker, LangBridge 新方法
"""
import os
import sys
import tempfile
import hashlib


# 测试 CompileMode
def test_compile_mode_members():
    from vools.bridge.core.types import CompileMode
    assert CompileMode.NORMAL == 'NORMAL'
    assert CompileMode.DEBUG == 'DEBUG'
    assert CompileMode.FORCE == 'FORCE'
    assert CompileMode.ONLY_RUN == 'ONLY_RUN'
    assert CompileMode.ONLY_CODE == 'ONLY_CODE'
    assert CompileMode.WHEN_CHANGE_JUST == 'WHEN_CHANGE_JUST'
    assert CompileMode.WHEN_CHANGE_AND_RUN == 'WHEN_CHANGE_AND_RUN'


def test_compile_mode_normalize():
    from vools.bridge.core.types import CompileMode
    assert CompileMode.normalize('normal') == 'NORMAL'
    assert CompileMode.normalize('DEBUG') == 'DEBUG'
    assert CompileMode.normalize('Only_Code') == 'ONLY_CODE'
    assert CompileMode.normalize(CompileMode.NORMAL) == 'NORMAL'
    try:
        CompileMode.normalize('INVALID')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_compile_mode_helpers():
    from vools.bridge.core.types import CompileMode
    assert CompileMode.is_change_aware('WHEN_CHANGE_JUST') is True
    assert CompileMode.is_change_aware('WHEN_CHANGE_AND_RUN') is True
    assert CompileMode.is_change_aware('NORMAL') is False
    assert CompileMode.is_force_recompile('DEBUG') is True
    assert CompileMode.is_force_recompile('FORCE') is True
    assert CompileMode.is_force_recompile('NORMAL') is False
    assert CompileMode.should_execute('NORMAL') is True
    assert CompileMode.should_execute('FORCE') is False
    assert CompileMode.should_execute('ONLY_CODE') is False
    assert CompileMode.should_execute('WHEN_CHANGE_JUST') is False


# 测试 LangType
def test_lang_type():
    from vools.bridge.core.types import LangType
    assert LangType.COMPILED == 'compiled'
    assert LangType.INTERPRETED == 'interpreted'
    assert LangType.JVM == 'jvm'
    assert LangType.DOTNET == 'dotnet'
    assert LangType.BEAM == 'beam'


# 测试 CompileTracker
# 为 CompileTracker 测试创建临时数据库
_test_tracker_db_dir = None


def _get_test_tracker():
    """获取使用临时数据库的 CompileTracker 实例"""
    global _test_tracker_db_dir
    if _test_tracker_db_dir is None:
        _test_tracker_db_dir = tempfile.mkdtemp(prefix='vools_test_tracker_')
    db_path = os.path.join(_test_tracker_db_dir, 'bridge_records.db')
    from vools.bridge.core.tracker import CompileTracker
    return CompileTracker(db_path=db_path)


def test_tracker_db_path():
    tracker = _get_test_tracker()
    db_path = tracker.get_db_path()
    assert 'bridge_records.db' in db_path
    assert os.path.exists(db_path)


def test_tracker_upsert_and_get():
    tracker = _get_test_tracker()
    record_key = 'test_module:test_func'
    source_md5 = 'abc123'

    tracker.upsert_record(
        record_key,
        language='nim',
        lang_type='compiled',
        func_name='test_func',
        source_md5=source_md5,
        lib_path='/tmp/test.dll',
        compile_mode='NORMAL',
        python_module='test_module',
        python_file='test_module.py',
    )

    record = tracker.get_record(record_key)
    assert record is not None
    assert record['language'] == 'nim'
    assert record['source_md5'] == source_md5
    assert record['func_name'] == 'test_func'


def test_tracker_is_changed():
    tracker = _get_test_tracker()
    record_key = 'test_module:changed_test'

    # 无记录时应该返回 True（已变更）
    assert tracker.is_changed(record_key, 'new_md5') is True

    # 插入记录
    tracker.upsert_record(
        record_key,
        language='nim',
        func_name='changed_test',
        source_md5='old_md5',
        lib_path='/tmp/test.dll',
        compile_mode='NORMAL',
        python_module='test_module',
        python_file='test_module.py',
    )

    # 相同 MD5 应该返回 False（未变更）
    assert tracker.is_changed(record_key, 'old_md5') is False

    # 不同 MD5 应该返回 True（已变更）
    assert tracker.is_changed(record_key, 'new_md5') is True


def test_tracker_make_record_key():
    from vools.bridge.core.tracker import CompileTracker

    def my_function():
        pass

    key = CompileTracker.make_record_key(my_function)
    assert ':' in key
    assert 'my_function' in key


def test_tracker_upsert_update():
    tracker = _get_test_tracker()
    record_key = 'test_module:update_test'

    # 首次插入
    tracker.upsert_record(
        record_key,
        language='nim',
        func_name='update_test',
        source_md5='md5_v1',
        lib_path='/tmp/v1.dll',
        compile_mode='NORMAL',
        python_module='test_module',
        python_file='test_module.py',
    )

    record = tracker.get_record(record_key)
    assert record['source_md5'] == 'md5_v1'

    # 更新
    tracker.upsert_record(
        record_key,
        language='nim',
        func_name='update_test',
        source_md5='md5_v2',
        lib_path='/tmp/v2.dll',
        compile_mode='DEBUG',
        python_module='test_module',
        python_file='test_module.py',
    )

    record = tracker.get_record(record_key)
    assert record['source_md5'] == 'md5_v2'
    assert record['compile_mode'] == 'DEBUG'


# 测试 LangBridge 新属性
def test_lang_bridge_defaults():
    from vools.bridge._base import LangBridge
    from vools.bridge.core.types import LangType, CompileMode

    # 测试类属性默认值
    assert LangBridge.is_compiled is True
    assert LangBridge.lang_type == LangType.COMPILED


# 测试从 vools.bridge 导入
def test_import_from_bridge():
    # 使用临时目录避免沙箱访问限制
    tmp_dir = tempfile.mkdtemp(prefix='vools_test_import_')
    old_localappdata = os.environ.get('LOCALAPPDATA')
    os.environ['LOCALAPPDATA'] = tmp_dir
    try:
        from vools.bridge import CompileMode, CompileTracker, LangType, get_tracker
        assert CompileMode.NORMAL == 'NORMAL'
        assert isinstance(get_tracker(), CompileTracker)
        assert LangType.COMPILED == 'compiled'
    finally:
        if old_localappdata is not None:
            os.environ['LOCALAPPDATA'] = old_localappdata
        else:
            del os.environ['LOCALAPPDATA']


# 运行所有测试
if __name__ == '__main__':
    tests = [
        test_compile_mode_members,
        test_compile_mode_normalize,
        test_compile_mode_helpers,
        test_lang_type,
        test_tracker_db_path,
        test_tracker_upsert_and_get,
        test_tracker_is_changed,
        test_tracker_make_record_key,
        test_tracker_upsert_update,
        test_lang_bridge_defaults,
        test_import_from_bridge,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print("[PASS] {}".format(test.__name__))
            passed += 1
        except Exception as e:
            print("[FAIL] {}: {}".format(test.__name__, e))
            failed += 1

    print("\n{}".format('=' * 50))
    print("Results: {} passed, {} failed".format(passed, failed))
    if failed > 0:
        sys.exit(1)