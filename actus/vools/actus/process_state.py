"""进程级全局状态的**唯一**互斥锁（BUG-0023）。

放在这个叶子模块里，是因为有两条互不相干的入口都在改同一份进程全局：

  * `executor._run_blocks` —— 在「注入 ACTUS_PARAMS / secrets / sandbox env → 启动子进程」
    期间逐键写 `os.environ`，退出时整份快照回写；
  * `runtimes.PythonRuntime.execute` —— **进程内 exec**，除 `os.environ` 外还换绑
    `sys.{stdout,stderr,stdin,argv}`。

修 BUG-0018 时给后者加了一把锁，但它和 executor 那把 `_ENV_LOCK` 是**两个对象**：
各自闭合自己的窗口，交叉起来环境照样互串 —— 缺口只是从「一条路没锁」缩成「两条路各锁各的」。
锁要有单一归属者，而这个归属者不能由任何一方持有（那会逼出反向依赖），所以放这里。

用 RLock 而不是 Lock：被 exec 的动作代码可能再进来一次 `execute_block` 或嵌套执行，
同线程宁可重入也不要自死锁。
"""
import threading

__all__ = ['PROCESS_STATE_LOCK']

PROCESS_STATE_LOCK = threading.RLock()
