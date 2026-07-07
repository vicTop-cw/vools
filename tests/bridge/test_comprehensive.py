"""
编译器自动发现功能 - 综合测试套件

测试内容：
1. probe 模块核心功能
2. manager 模块 auto_discover 功能
3. auto_discovery 模块完整流程
4. 边界条件与异常处理
5. 配置持久化
"""

import os
import sys
import tempfile
import unittest
from typing import Optional

# ---------------------------------------------------------------------------
# probe 模块测试
# ---------------------------------------------------------------------------

class TestProbeModule(unittest.TestCase):
    """probe 模块测试"""

    @classmethod
    def setUpClass(cls):
        from vools.bridge import probe
        cls.probe = probe

    def test_language_probes_exists(self):
        """测试 LANGUAGE_PROBES 配置存在且完整"""
        self.assertIsInstance(self.probe.LANGUAGE_PROBES, dict)
        self.assertGreater(len(self.probe.LANGUAGE_PROBES), 0)
        
        for lang, config in self.probe.LANGUAGE_PROBES.items():
            self.assertIn('commands', config)
            self.assertIsInstance(config['commands'], list)
            self.assertGreater(len(config['commands']), 0)

    def test_bridge_supported_matches_probes(self):
        """测试 BRIDGE_SUPPORTED 与 LANGUAGE_PROBES 一致"""
        probe_langs = set(self.probe.LANGUAGE_PROBES.keys())
        bridge_langs = set(self.probe.BRIDGE_SUPPORTED)
        self.assertEqual(probe_langs, bridge_langs)

    def test_common_install_paths_exists(self):
        """测试 COMMON_INSTALL_PATHS 存在"""
        self.assertIsInstance(self.probe.COMMON_INSTALL_PATHS, dict)

    def test_language_status_dataclass(self):
        """测试 LanguageStatus 数据类"""
        status = self.probe.LanguageStatus(name='test')
        self.assertEqual(status.name, 'test')
        self.assertFalse(status.available)
        self.assertIsNone(status.path)
        self.assertIsNone(status.version)

    def test_probe_report_dataclass(self):
        """测试 ProbeReport 数据类"""
        report = self.probe.ProbeReport(
            platform='test',
            arch='x86_64',
            python_version='3.10.0',
            host='test',
        )
        self.assertEqual(report.platform, 'test')
        self.assertEqual(report.host, 'test')
        self.assertIsInstance(report.languages, dict)
        self.assertEqual(report.available_languages(), [])

    def test_expand_wildcard_paths_empty(self):
        """测试通配符路径展开 - 空输入"""
        result = self.probe.expand_wildcard_paths([])
        self.assertEqual(result, [])

    def test_expand_wildcard_paths_nonexistent(self):
        """测试通配符路径展开 - 不存在的路径"""
        result = self.probe.expand_wildcard_paths([r'C:\nonexistent\path\*\bin'])
        self.assertEqual(result, [])

    def test_probe_environment_basic(self):
        """测试基本环境探测"""
        report = self.probe.probe_environment()
        self.assertIsNotNone(report.platform)
        self.assertIsNotNone(report.arch)
        self.assertIsInstance(report.languages, dict)
        self.assertGreater(len(report.languages), 0)

    def test_probe_environment_specific_languages(self):
        """测试指定语言的环境探测"""
        report = self.probe.probe_environment(languages=['python', 'nim', 'c'])
        self.assertLessEqual(len(report.languages), 3)

    def test_get_available_languages(self):
        """测试 get_available_languages 函数"""
        langs = self.probe.get_available_languages()
        self.assertIsInstance(langs, list)

    def test_print_report(self):
        """测试报告生成"""
        report = self.probe.probe_environment(languages=['nim', 'c'])
        output = self.probe.print_report(report)
        self.assertIsInstance(output, str)
        self.assertGreater(len(output), 0)

    def test_list_wsl_distributions(self):
        """测试 WSL 发行版列表（在 Windows 上）"""
        import platform
        if platform.system() == 'Windows':
            distros = self.probe.list_wsl_distributions()
            self.assertIsInstance(distros, list)
        else:
            distros = self.probe.list_wsl_distributions()
            self.assertEqual(distros, [])

    def test_search_windows_registry(self):
        """测试 Windows 注册表搜索"""
        import platform
        if platform.system() == 'Windows':
            result = self.probe.search_windows_registry()
            self.assertIsInstance(result, dict)
        else:
            result = self.probe.search_windows_registry()
            self.assertEqual(result, {})

    def test_probe_with_extra_paths(self):
        """测试带额外路径的探测"""
        report = self.probe.probe_with_extra_paths(
            languages=['nim'],
            extra_paths={'nim': [r'C:\nonexistent']},
            use_common_paths=True,
        )
        self.assertIn('nim', report.languages)


# ---------------------------------------------------------------------------
# manager 模块测试
# ---------------------------------------------------------------------------

class TestManagerModule(unittest.TestCase):
    """manager 模块测试"""

    @classmethod
    def setUpClass(cls):
        from vools.bridge import manager
        cls.manager = manager

    def test_manager_singleton(self):
        """测试 manager 是单例"""
        from vools.bridge.manager import manager as m2
        self.assertIs(self.manager, m2)

    def test_language_config_dataclass(self):
        """测试 LanguageConfig 数据类"""
        from vools.bridge.manager import LanguageConfig
        config = LanguageConfig(name='test', compiler='testc')
        self.assertEqual(config.name, 'test')
        self.assertEqual(config.compiler, 'testc')

    def test_list_languages(self):
        """测试 list_languages"""
        from vools.bridge import list_languages
        langs = list_languages()
        self.assertIsInstance(langs, list)
        self.assertGreater(len(langs), 0)

    def test_get_config(self):
        """测试 get_config"""
        from vools.bridge.manager import manager
        config = manager.get_config('nim')
        self.assertIsNotNone(config)
        self.assertEqual(config.name, 'nim')

    def test_get_config_nonexistent(self):
        """测试获取不存在的语言配置"""
        from vools.bridge.manager import manager
        config = manager.get_config('nonexistent_language')
        self.assertIsNone(config)

    def test_is_available(self):
        """测试 is_available"""
        from vools.bridge.manager import manager
        result = manager.is_available('nim')
        self.assertIsInstance(result, bool)

    def test_get_status(self):
        """测试 get_status"""
        from vools.bridge.manager import manager
        status = manager.get_status('nim')
        self.assertIsNotNone(status)

    def test_get_compiler_path(self):
        """测试 get_compiler_path"""
        from vools.bridge import get_compiler_path
        path = get_compiler_path('nim')
        # 可能是 None 或路径字符串
        self.assertTrue(path is None or isinstance(path, str))

    def test_register_unregister(self):
        """测试注册和注销语言配置"""
        from vools.bridge.manager import manager, LanguageConfig
        
        test_config = LanguageConfig(
            name='testlang',
            compiler='testc',
            compiler_paths=[],
        )
        
        # 注册
        manager.register(test_config)
        self.assertIsNotNone(manager.get_config('testlang'))
        
        # 注销
        result = manager.unregister('testlang')
        self.assertTrue(result)
        self.assertIsNone(manager.get_config('testlang'))

    def test_unregister_nonexistent(self):
        """测试注销不存在的语言"""
        from vools.bridge.manager import manager
        result = manager.unregister('nonexistent_language')
        self.assertFalse(result)

    def test_clear_cache(self):
        """测试清除缓存"""
        from vools.bridge.manager import manager
        manager.clear_cache('nim')
        manager.clear_cache()  # 清除所有

    def test_save_load_config(self):
        """测试配置保存和加载"""
        from vools.bridge.manager import manager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'test_config.json')
            
            # 保存
            saved_path = manager.save_config(config_path)
            self.assertEqual(saved_path, config_path)
            self.assertTrue(os.path.exists(config_path))
            
            # 加载
            count = manager.load_config(config_path)
            self.assertGreater(count, 0)

    def test_auto_discover(self):
        """测试 auto_discover 方法"""
        from vools.bridge.manager import manager
        result = manager.auto_discover(include_wsl=False)
        self.assertIsInstance(result, dict)
        self.assertIn('local', result)
        self.assertIn('wsl', result)


# ---------------------------------------------------------------------------
# auto_discovery 模块测试
# ---------------------------------------------------------------------------

class TestAutoDiscoveryModule(unittest.TestCase):
    """auto_discovery 模块测试"""

    def test_discover_local(self):
        """测试 discover_local"""
        from vools.bridge import discover_local
        result = discover_local(configure_manager=False)
        self.assertIsInstance(result, dict)
        self.assertIn('local', result)
        self.assertIn('discovered', result)
        self.assertIn('report', result)

    def test_discover_wsl(self):
        """测试 discover_wsl"""
        from vools.bridge import discover_wsl
        result = discover_wsl()
        self.assertIsInstance(result, list)

    def test_discover_all(self):
        """测试 discover_all"""
        from vools.bridge import discover_all
        result = discover_all(include_wsl=False, configure_manager=False)
        self.assertIsInstance(result, dict)
        self.assertIn('local', result)
        self.assertIn('wsl', result)
        self.assertIn('discovered', result)
        self.assertIn('report', result)

    def test_get_discovery_report(self):
        """测试 get_discovery_report"""
        from vools.bridge import get_discovery_report
        report = get_discovery_report(include_wsl=False)
        self.assertIsInstance(report, str)
        self.assertGreater(len(report), 0)

    def test_configure_from_discovery(self):
        """测试 configure_from_discovery"""
        from vools.bridge import configure_from_discovery
        count = configure_from_discovery(include_wsl=False)
        self.assertIsInstance(count, int)
        self.assertGreater(count, 0)


# ---------------------------------------------------------------------------
# 集成测试
# ---------------------------------------------------------------------------

class TestIntegration(unittest.TestCase):
    """集成测试"""

    def test_full_workflow(self):
        """测试完整工作流：发现 -> 配置 -> 保存 -> 加载"""
        from vools.bridge import (
            discover_all,
            configure_from_discovery,
            save_config,
            load_config,
            manager,
        )
        
        # 1. 发现
        result = discover_all(include_wsl=False, configure_manager=False)
        self.assertIn('local', result)
        
        # 2. 配置
        count = configure_from_discovery(include_wsl=False)
        self.assertGreater(count, 0)
        
        # 3. 保存
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'integration_test.json')
            saved = save_config(config_path)
            self.assertTrue(os.path.exists(saved))
            
            # 4. 加载
            loaded = load_config(config_path)
            self.assertGreater(loaded, 0)

    def test_language_compiler_helper(self):
        """测试 LanguageCompilerHelper"""
        from vools.bridge import get_helper
        
        helper = get_helper('nim')
        self.assertIsNotNone(helper)
        
        # 测试方法
        result = helper.is_available()
        self.assertIsInstance(result, bool)
        
        path = helper.get_compiler_path()
        self.assertTrue(path is None or isinstance(path, str))

    def test_all_registered_languages_status(self):
        """测试所有已注册语言的状态"""
        from vools.bridge.manager import manager
        
        langs = manager.list_languages()
        self.assertGreater(len(langs), 0)
        
        for lang in langs[:5]:  # 只测试前 5 个，避免太慢
            status = manager.get_status(lang)
            self.assertIsNotNone(status)


def run_tests():
    """运行所有测试"""
    print('=' * 70)
    print('编译器自动发现功能 - 综合测试')
    print('=' * 70)
    print(f'Python 版本: {sys.version}')
    print(f'平台: {sys.platform}')
    print()
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加所有测试类
    suite.addTests(loader.loadTestsFromTestCase(TestProbeModule))
    suite.addTests(loader.loadTestsFromTestCase(TestManagerModule))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoDiscoveryModule))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print()
    print('=' * 70)
    if result.wasSuccessful():
        print('✅ 所有测试通过！')
    else:
        print(f'❌ 测试失败: {len(result.failures)} 失败, {len(result.errors)} 错误')
    print('=' * 70)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
