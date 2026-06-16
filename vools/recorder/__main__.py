"""
recorder 命令行入口

用法:
    python -m recorder          # 启动 GUI
    python -m recorder --help   # 查看帮助
"""
import sys
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        description="vools-recorder: 键鼠操作录制与回放工具"
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="使用命令行模式（而非 GUI）"
    )
    args, _ = parser.parse_known_args()

    if args.cli:
        print("命令行模式尚未实现，将启动 GUI...")

    # 启动 GUI
    try:
        from .gui import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"错误: 无法加载 GUI 模块 — {e}")
        print("请确保 tkinter 已安装（Python 标准库）")
        sys.exit(1)


if __name__ == "__main__":
    main()
