#!/usr/bin/env python
"""
vools 自动化发布脚本

使用 Fabric 实现项目的自动化发布流程，包括：
- 环境检查
- 依赖安装
- 代码打包
- 版本控制
- 发布到 PyPI
- 同步到 GitHub
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from release import ReleaseManager
from config import save_config, DEFAULT_CONFIG


def main():
    parser = argparse.ArgumentParser(description="vools 自动化发布工具")
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # release 命令
    release_parser = subparsers.add_parser("release", help="执行完整发布流程")
    release_parser.add_argument(
        "--bump", "-b",
        choices=["major", "minor", "patch"],
        default="patch",
        help="版本递增级别 (major/minor/patch)"
    )
    release_parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="发布到测试 PyPI"
    )
    release_parser.add_argument(
        "--skip-tests", "-s",
        action="store_true",
        help="跳过测试"
    )
    
    # config 命令
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_parser.add_argument(
        "--init", "-i",
        action="store_true",
        help="初始化配置文件"
    )
    config_parser.add_argument(
        "--show",
        action="store_true",
        help="显示当前配置"
    )
    
    # check 命令
    subparsers.add_parser("check", help="检查环境")
    
    # version 命令
    version_parser = subparsers.add_parser("version", help="版本管理")
    version_parser.add_argument(
        "--show", "-s",
        action="store_true",
        help="显示当前版本"
    )
    version_parser.add_argument(
        "--bump", "-b",
        choices=["major", "minor", "patch"],
        help="版本递增级别"
    )
    
    args = parser.parse_args()
    
    if args.command == "release":
        manager = ReleaseManager()
        success = manager.release(
            bump_level=args.bump,
            test=args.test,
            skip_tests=args.skip_tests
        )
        sys.exit(0 if success else 1)
    
    elif args.command == "config":
        if args.init:
            save_config(DEFAULT_CONFIG)
            print("配置文件已创建: autopypi/config.json")
        elif args.show:
            from autopypi.config import load_config
            import json
            config = load_config()
            print(json.dumps(config, indent=2, ensure_ascii=False))
        else:
            config_parser.print_help()
    
    elif args.command == "check":
        manager = ReleaseManager()
        success = manager.check_environment()
        sys.exit(0 if success else 1)
    
    elif args.command == "version":
        from config import get_current_version, increment_version, update_version
        current_version = get_current_version()
        if args.show:
            print(f"当前版本: {current_version}")
        elif args.bump:
            new_version = increment_version(current_version, args.bump)
            update_version(new_version)
            print(f"版本已更新: {current_version} -> {new_version}")
        else:
            version_parser.print_help()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()