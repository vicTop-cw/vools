
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
print(sys.path[0])
# from vools.recorder import RecorderGUI

# gui = RecorderGUI()
# gui.run()

import time
from vools.reactive import Observable, ops, Subject

# ===== interval (sync context) =====

def test_interval_take():
    """interval 在同步上下文中正常工�?""
    result = []
    sub = Observable.interval(0.02).pipe(ops.take(3)).subscribe(on_next=lambda x: result.append(x))
    time.sleep(0.1)
    sub.dispose()
    # assert result == [0, 1, 2], f"Got {result}"
    print(result)



# test_interval_take()