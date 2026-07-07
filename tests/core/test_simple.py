"""
简单调试测试
"""
import os
from vools.task import TaskQueue
import time
import tempfile


def simple_func(a: int, b: int) -> int:
    print(f"Executing simple_func({a}, {b})")
    return a + b


def test_simple():
    print("简单测试")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        queue = TaskQueue(db_path)

        task_id = queue.submit(simple_func, 2, 3)
        print(f"Task submitted: {task_id}")

        # 查看任务
        task = queue.get_task(task_id)
        print(f"Task: {task}")
        print(f"Task args: {task.args}")
        print(f"Task func: {task.task_func}")

        # 直接执行测试
        print("\n直接执行任务:")
        result = queue.execute_task(task)
        print(f"Result: {result}")

        print(f"Queue.get_result返回: {result}")

    finally:
        try:
            os.unlink(db_path)
        except:
            pass


if __name__ == '__main__':
    test_simple()
