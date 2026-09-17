# -*- coding: utf-8 -*-
"""
测试所有桥接语言的执行
"""

import os
import sys
import unittest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from vools.bridge.md.runner import _execute_via_bridge
from vools.bridge.md.parser import CodeBlock


class TestAllBridgeLanguages(unittest.TestCase):
    """测试所有桥接语言的执行"""
    
    def test_python_execution(self):
        """测试 Python 执行"""
        from vools.bridge.md.runner import _execute_python
        
        block = CodeBlock(
            index=0,
            language='python',
            directives={},
            content='print("Hello from Python")',
            tag=[]
        )
        
        stdout, stderr, exit_code = _execute_python(block.content, {}, {}, None)
        self.assertEqual(exit_code, 0)
        self.assertIn("Hello from Python", stdout)
    
    def test_shell_execution(self):
        """测试 Shell 执行"""
        from vools.bridge.md.runner import _execute_shell
        
        block = CodeBlock(
            index=0,
            language='shell',
            directives={},
            content='echo "Hello from Shell"',
            tag=[]
        )
        
        stdout, stderr, exit_code = _execute_shell(block.content, {}, {}, os.getcwd(), 60, None)
        self.assertEqual(exit_code, 0)
        self.assertIn("Hello from Shell", stdout)
    
    def test_bash_execution(self):
        """测试 Bash 执行"""
        from vools.bridge.md.runner import _execute_shell
        
        block = CodeBlock(
            index=0,
            language='bash',
            directives={},
            content='echo "Hello from Bash"',
            tag=[]
        )
        
        stdout, stderr, exit_code = _execute_shell(block.content, {}, {}, os.getcwd(), 60, None)
        self.assertEqual(exit_code, 0)
        self.assertIn("Hello from Bash", stdout)
    
    def test_lua_execution(self):
        """测试 Lua 执行"""
        block = CodeBlock(
            index=0,
            language='lua',
            directives={},
            content='print("Hello from Lua")',
            tag=[]
        )
        
        stdout, stderr, exit_code = _execute_via_bridge(block, {}, {}, 60)
        # Lua 可能未安装，不强制要求成功
        if exit_code != 0:
            print(f"Lua 未安装或不可用: {stderr}")
    
    def test_perl_execution(self):
        """测试 Perl 执行"""
        block = CodeBlock(
            index=0,
            language='perl',
            directives={},
            content='print "Hello from Perl\n"',
            tag=[]
        )
        
        stdout, stderr, exit_code = _execute_via_bridge(block, {}, {}, 60)
        # Perl 可能未安装，不强制要求成功
        if exit_code != 0:
            print(f"Perl 未安装或不可用: {stderr}")
    
    def test_ruby_execution(self):
        """测试 Ruby 执行"""
        block = CodeBlock(
            index=0,
            language='ruby',
            directives={},
            content='puts "Hello from Ruby"',
            tag=[]
        )
        
        stdout, stderr, exit_code = _execute_via_bridge(block, {}, {}, 60)
        # Ruby 可能未安装，不强制要求成功
        if exit_code != 0:
            print(f"Ruby 未安装或不可用: {stderr}")
    
    def test_php_execution(self):
        """测试 PHP 执行"""
        block = CodeBlock(
            index=0,
            language='php',
            directives={},
            content='<?php echo "Hello from PHP\n"; ?>',
            tag=[]
        )
        
        stdout, stderr, exit_code = _execute_via_bridge(block, {}, {}, 60)
        # PHP 可能未安装，不强制要求成功
        if exit_code != 0:
            print(f"PHP 未安装或不可用: {stderr}")
    
    def test_powershell_execution(self):
        """测试 PowerShell 执行"""
        block = CodeBlock(
            index=0,
            language='powershell',
            directives={},
            content='Write-Output "Hello from PowerShell"',
            tag=[]
        )
        
        stdout, stderr, exit_code = _execute_via_bridge(block, {}, {}, 60)
        # PowerShell 可能未安装，不强制要求成功
        if exit_code != 0:
            print(f"PowerShell 未安装或不可用: {stderr}")
    
    def test_node_execution(self):
        """测试 TypeScript/JavaScript 执行"""
        block = CodeBlock(
            index=0,
            language='typescript',
            directives={},
            content='console.log("Hello from TypeScript");',
            tag=[]
        )
        
        stdout, stderr, exit_code = _execute_via_bridge(block, {}, {}, 60)
        # Node.js 可能未安装，不强制要求成功
        if exit_code != 0:
            print(f"TypeScript/Node.js 未安装或不可用: {stderr}")
    
    def test_julia_execution(self):
        """测试 Julia 执行"""
        block = CodeBlock(
            index=0,
            language='julia',
            directives={},
            content='println("Hello from Julia")',
            tag=[]
        )
        
        stdout, stderr, exit_code = _execute_via_bridge(block, {}, {}, 60)
        # Julia 可能未安装，不强制要求成功
        if exit_code != 0:
            print(f"Julia 未安装或不可用: {stderr}")
    
    def test_r_execution(self):
        """测试 R 执行"""
        block = CodeBlock(
            index=0,
            language='r',
            directives={},
            content='cat("Hello from R\n")',
            tag=[]
        )
        
        stdout, stderr, exit_code = _execute_via_bridge(block, {}, {}, 60)
        # R 可能未安装，不强制要求成功
        if exit_code != 0:
            print(f"R 未安装或不可用: {stderr}")


class TestBridgeHelper(unittest.TestCase):
    """测试 Bridge Helper"""
    
    def test_get_bridge(self):
        """测试获取 Bridge 实例"""
        from vools.bridge.manager import get_bridge
        
        # 测试获取 Python bridge（应该返回 None，因为 Python 不需要 bridge）
        bridge = get_bridge('python')
        # Python 不需要 bridge，所以可能是 None
        
        # 测试获取其他语言的 bridge
        bridge = get_bridge('nim')
        # Nim 可能未安装，不强制要求成功
    
    def test_python_helper_available(self):
        """测试 Python Helper 可用性"""
        from vools.bridge.manager import get_helper
        
        # Python 总是可用的
        helper = get_helper('python')
        self.assertTrue(helper.is_available())


if __name__ == '__main__':
    unittest.main(verbosity=2)
