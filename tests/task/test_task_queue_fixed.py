"""
测试任务队列功能 - 修复版本
使用单独模块中的函数来确保多进程可pickle
"""
import os
import time
import tempfile

from vools.task import TaskQueue, WorkerPool, task
from tests.test_functions import add, multiply, sometimes_fails


def test_basic_functionality():
    """测试基本功能"""
    print("=== 测试基本功能 ===")

    # 使用临时文件但不自动删除
    db_path = tempfile.mktemp(suffix='.db')
    print(f"Database: {db_path}")

    try:
        queue = TaskQueue(db_path)

        # 提交任务
        task_id1 = queue.submit(add, 2, 3)
        task_id2 = queue.submit(multiply, 4, 5)

        print(f"Task 1 submitted: {task_id1}")
        print(f"Task 2 submitted: {task_id2}")

        # 启动Worker
        pool = WorkerPool(num_workers=2, db_path=db_path, poll_interval=0.1)
        pool.start()

        # 等待任务完成
        try:
            result1 = queue.get_result(task_id1, timeout=10)
            result2 = queue.get_result(task_id2, timeout=10)

            print(f"Task 1 result: {result1}")
            print(f"Task 2 result: {result2}")

            assert result1 == 5
            assert result2 == 20

            print("✓ 基本功能测试通过")
        finally:
            pool.stop()

    finally:
        # 清理数据库
        try:
            os.unlink(db_path)
            os.unlink(db_path + '-wal')
            os.unlink(db_path + '-shm')
        except:
            pass


def main():
    """运行所有测试"""
    print("任务队列系统测试（修复版本）\n")
    test_basic_functionality()
    print("\n🎉 所有测试通过!")


if __name__ == '__main__':
    main()
