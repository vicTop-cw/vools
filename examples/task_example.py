"""
任务队列系统示例

注意：在Windows上使用多进程时，任务函数需要放在可导入的模块中，
不能直接在__main__模块中定义。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from vools.task import TaskQueue, WorkerPool


def example_function(a: int, b: int) -> int:
    """示例任务函数"""
    time.sleep(0.5)  # 模拟耗时操作
    return a + b


def main():
    print("任务队列系统示例")
    print("=" * 40)

    # 使用本地数据库文件
    db_path = "example_tasks.db"

    # 创建队列
    queue = TaskQueue(db_path)
    print(f"已创建任务队列，数据库: {db_path}")

    # 提交几个示例任务
    print("\n正在提交任务...")
    task_ids = []
    for i in range(5):
        task_id = queue.submit(example_function, i, i * 2, priority=i)
        task_ids.append(task_id)
        print(f"  已提交任务 {task_id}: {i} + {i*2}")

    # 启动Worker处理
    print(f"\n启动2个Worker进程...")
    pool = WorkerPool(num_workers=2, db_path=db_path, poll_interval=0.2)
    pool.start()

    # 等待任务完成并获取结果
    print("\n等待任务完成...")
    results = []
    for task_id in task_ids:
        try:
            result = queue.get_result(task_id, timeout=30)
            results.append(result)
            print(f"  任务 {task_id} 完成，结果: {result}")
        except Exception as e:
            print(f"  任务 {task_id} 失败: {e}")

    # 停止Worker
    pool.stop()
    print("\nWorker已停止")

    # 清理数据库
    print("\n清理数据库...")
    try:
        os.unlink(db_path)
        os.unlink(db_path + "-wal")
        os.unlink(db_path + "-shm")
        print("数据库已清理")
    except:
        pass

    print("\n示例完成!")


if __name__ == "__main__":
    main()
