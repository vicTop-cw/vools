"""
MouseObserver �?MouseSubject 集成测试

测试方案:
1. 部署两个独立进程：监控程�?+ 鼠标模拟程序
2. 禁用自过滤机制，确保所有鼠标事件完整传�?3. 覆盖各类鼠标操作场景（移动、点击、拖拽、滚轮等�?4. 生成详细的事件日志记录（事件类型、触发时间、坐标、事件传递路径）
"""

import os
import sys
import time
import json
import subprocess
import psutil
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.reactive.monitoring.mouse import (
    MouseSubject, MouseObserver, MouseData, MouseEventType
)


def log_event(log_file: str, event_type: str, **data) -> None:
    """记录测试事件"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        **data
    }
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def write_control(control_file: str, action: str, **kwargs) -> None:
    """写入控制指令"""
    with open(control_file, "w", encoding="utf-8") as f:
        json.dump({"action": action, "timestamp": datetime.now().isoformat(), **kwargs}, f)


def read_control(control_file: str) -> Dict | None:
    """读取控制指令"""
    if not os.path.exists(control_file):
        return None
    try:
        with open(control_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def monitor_process(control_file: str, log_file: str, disable_filter: bool = True):
    """监控程序进程"""
    import logging
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
    
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024
    
    log_event(log_file, "monitor_start", pid=os.getpid())
    
    events_received: List[Dict] = []
    
    def on_mouse_event(md: MouseData):
        ts = time.time()
        evt_data = {
            "x": md.x,
            "y": md.y,
            "event_type": MouseEventType(md.event_type).name,
            "button": md.button,
            "delta": md.delta,
            "timestamp": md.timestamp.isoformat(),
            "time_ms": ts,
            "sequence": md.sequence,
        }
        events_received.append(evt_data)
        
        log_event(log_file, "mouse_event",
                  x=md.x,
                  y=md.y,
                  mouse_event_type=MouseEventType(md.event_type).name,
                  path="backend -> _on_change -> subject -> observer -> callback")
        print(f"[监控] 收到鼠标事件: {MouseEventType(md.event_type).name} ({md.x},{md.y}) - seq={md.sequence}")
    
    filter_self = not disable_filter
    
    print(f"[监控] filter_self={filter_self} (自过滤已禁用)")
    
    ms = MouseSubject(
        backend="polling",
        filter_self=filter_self,
    )
    
    ms.subscribe(on_next=on_mouse_event)
    ms.start()
    
    current_memory = process.memory_info().rss / 1024 / 1024
    
    print(f"[监控] 启动成功，后�? {ms.backend_name}")
    print(f"[监控] filter_self: {ms.dispatcher._filter_self}")
    print(f"[监控] 初始内存: {initial_memory:.2f}MB, 当前内存: {current_memory:.2f}MB")
    
    log_event(log_file, "monitor_config",
              backend=ms.backend_name,
              filter_self=ms.dispatcher._filter_self,
              initial_memory_mb=initial_memory,
              current_memory_mb=current_memory)
    
    write_control(control_file, "ready",
                  pid=os.getpid(),
                  backend=ms.backend_name,
                  filter_self=ms.dispatcher._filter_self)
    
    while True:
        control = read_control(control_file)
        if control and control.get("action") == "stop":
            break
        time.sleep(0.05)
    
    time.sleep(0.5)
    
    ms.stop()
    
    final_memory = process.memory_info().rss / 1024 / 1024
    
    log_event(log_file, "monitor_stop",
              events_received=len(events_received),
              final_memory_mb=final_memory,
              memory_delta_mb=final_memory - initial_memory)
    
    results = {
        "events_received": events_received,
        "dispatch_count": ms.dispatch_count,
        "filtered_count": ms.self_filtered_count,
        "initial_memory_mb": initial_memory,
        "final_memory_mb": final_memory,
        "memory_delta_mb": final_memory - initial_memory,
        "backend": ms.backend_name,
        "filter_self": ms.dispatcher._filter_self,
    }
    
    results_path = os.path.join(os.path.dirname(control_file) or os.path.expanduser("~"), "_mouse_monitor_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"[监控] 停止，收�?{len(events_received)} 个鼠标事�?)


def simulator_process(control_file: str, log_file: str):
    """鼠标模拟程序进程"""
    from vools.reactive.monitoring.mouse import _move_to, _click, _scroll, _move_relative
    
    log_event(log_file, "simulator_start", pid=os.getpid())
    
    while True:
        control = read_control(control_file)
        if control and control.get("action") == "ready":
            break
        time.sleep(0.1)
    
    time.sleep(0.5)
    
    operations: List[Dict] = []
    
    def op(name: str, action: str, **kwargs):
        ts = time.time()
        operations.append({
            "name": name,
            "action": action,
            "timestamp": datetime.now().isoformat(),
            "time_ms": ts,
            **kwargs
        })
        log_event(log_file, "mouse_operation",
                  name=name,
                  action=action,
                  **kwargs)
        print(f"[模拟] {name}: {action}")
    
    scenarios = [
        ("move_center", "移动到屏幕中�?, {"x": 960, "y": 540}),
        ("move_top_left", "移动到左上角", {"x": 100, "y": 100}),
        ("move_top_right", "移动到右上角", {"x": 1820, "y": 100}),
        ("move_bottom_left", "移动到左下角", {"x": 100, "y": 1060}),
        ("move_bottom_right", "移动到右下角", {"x": 1820, "y": 1060}),
        
        ("left_click_center", "左键点击中心", {"x": 960, "y": 540, "button": "left"}),
        ("left_double_click", "左键双击", {"x": 960, "y": 540, "button": "left", "double": True}),
        ("right_click", "右键点击", {"x": 960, "y": 540, "button": "right"}),
        ("middle_click", "中键点击", {"x": 960, "y": 540, "button": "middle"}),
        
        ("scroll_up_small", "滚轮向上小幅�?, {"delta": 1}),
        ("scroll_down_small", "滚轮向下小幅�?, {"delta": -1}),
        ("scroll_up_large", "滚轮向上大幅�?, {"delta": 3}),
        ("scroll_down_large", "滚轮向下大幅�?, {"delta": -3}),
        
        ("rapid_moves", "快速连续移�?, {"points": [(200, 200), (400, 200), (600, 200), (800, 200)]}),
        ("zigzag_moves", "之字形移�?, {"points": [(500, 300), (600, 400), (500, 500), (600, 600)]}),
        
        ("rapid_clicks", "快速连续点�?, {"count": 5, "x": 960, "y": 540}),
    ]
    
    print(f"\n[模拟] 开始执�?{len(scenarios)} 个测试场�?..")
    
    for i, scenario in enumerate(scenarios):
        name, action, params = scenario[0], scenario[1], scenario[2]
        
        try:
            if "x" in params and "y" in params and "button" not in params:
                _move_to(params["x"], params["y"])
                op(name, action, x=params["x"], y=params["y"])
            
            elif "button" in params:
                _move_to(params["x"], params["y"])
                time.sleep(0.05)
                if params.get("double"):
                    _click(params["button"])
                    time.sleep(0.05)
                    _click(params["button"])
                else:
                    _click(params["button"])
                op(name, action, x=params["x"], y=params["y"], button=params["button"])
            
            elif "delta" in params:
                _scroll(params["delta"])
                op(name, action, delta=params["delta"])
            
            elif "points" in params:
                for px, py in params["points"]:
                    _move_to(px, py)
                    time.sleep(0.02)
                op(name, action, points=params["points"])
            
            elif "count" in params:
                _move_to(params["x"], params["y"])
                time.sleep(0.05)
                for _ in range(params["count"]):
                    _click("left")
                    time.sleep(0.02)
                op(name, action, count=params["count"], x=params["x"], y=params["y"])
            
        except Exception as e:
            log_event(log_file, "simulator_error", name=name, error=str(e))
            print(f"[模拟] 错误: {e}")
        
        time.sleep(0.15)
        
        if (i + 1) % 5 == 0:
            print(f"[模拟] 已完�?{i+1}/{len(scenarios)} 个场�?)
    
    ops_path = os.path.join(os.path.dirname(control_file) or os.path.expanduser("~"), "_mouse_operations.json")
    with open(ops_path, "w", encoding="utf-8") as f:
        json.dump({"operations": operations}, f, ensure_ascii=False, indent=2)
    
    time.sleep(1)
    
    write_control(control_file, "stop")
    
    log_event(log_file, "simulator_stop", operations=len(operations))
    print(f"[模拟] 完成 {len(operations)} 个鼠标操�?)


def run_integration_test():
    """运行集成测试"""
    import tempfile
    
    control_file = os.path.join(tempfile.gettempdir(), f"vools_mouse_control_{os.getpid()}.json")
    log_file = os.path.join(tempfile.gettempdir(), f"vools_mouse_test_log_{os.getpid()}.json")
    
    print("=" * 80)
    print("MouseObserver/MouseSubject 集成测试")
    print("自过滤状�? 已禁用（确保所有鼠标事件完整传递）")
    print("=" * 80)
    
    if os.path.exists(log_file):
        os.remove(log_file)
    if os.path.exists(control_file):
        os.remove(control_file)
    
    monitor_proc = subprocess.Popen(
        [sys.executable, __file__, "--monitor", control_file, log_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    time.sleep(0.5)
    
    simulator_proc = subprocess.Popen(
        [sys.executable, __file__, "--simulator", control_file, log_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    try:
        simulator_stdout, simulator_stderr = simulator_proc.communicate(timeout=60)
        monitor_stdout, monitor_stderr = monitor_proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        simulator_proc.kill()
        monitor_proc.kill()
        simulator_stdout, simulator_stderr = simulator_proc.communicate()
        monitor_stdout, monitor_stderr = monitor_proc.communicate()
    
    print("\n" + "=" * 80)
    print("监控程序输出:")
    print("-" * 40)
    print(monitor_stdout[-2000:] if monitor_stdout else "")
    if monitor_stderr:
        print("错误:")
        print(monitor_stderr[-500:] if monitor_stderr else "")
    
    print("\n" + "=" * 80)
    print("模拟程序输出:")
    print("-" * 40)
    print(simulator_stdout[-2000:] if simulator_stdout else "")
    if simulator_stderr:
        print("错误:")
        print(simulator_stderr[-500:] if simulator_stderr else "")
    
    results_path = os.path.join(os.path.dirname(control_file) or os.path.expanduser("~"), "_mouse_monitor_results.json")
    ops_path = os.path.join(os.path.dirname(control_file) or os.path.expanduser("~"), "_mouse_operations.json")
    
    print("\n" + "=" * 80)
    print("测试结果分析:")
    print("-" * 40)
    
    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            results = json.load(f)
        
        print(f"收到鼠标事件�? {len(results['events_received'])}")
        print(f"分发计数: {results['dispatch_count']}")
        print(f"过滤计数: {results['filtered_count']}")
        print(f"后端: {results['backend']}")
        print(f"filter_self: {results['filter_self']}")
        print(f"初始内存: {results['initial_memory_mb']:.2f}MB")
        print(f"最终内�? {results['final_memory_mb']:.2f}MB")
        print(f"内存增量: {results['memory_delta_mb']:.2f}MB")
        
        print("\n鼠标事件类型统计:")
        type_counts: Dict[str, int] = {}
        for evt in results['events_received']:
            ct = evt['event_type']
            type_counts[ct] = type_counts.get(ct, 0) + 1
        for ct, count in sorted(type_counts.items()):
            print(f"  - {ct}: {count} �?)
    
    if os.path.exists(ops_path):
        with open(ops_path, "r", encoding="utf-8") as f:
            ops = json.load(f)
        print(f"\n执行的鼠标操作数: {len(ops['operations'])}")
    
    print("\n" + "=" * 80)
    print("测试验证总结:")
    print("-" * 40)
    
    if os.path.exists(results_path):
        results = json.load(open(results_path, "r", encoding="utf-8"))
        events = results['events_received']
        
        print(f"�?事件接收�? {len(events)} �?)
        print(f"�?过滤计数: {results['filtered_count']} �?(应为0)")
        
        if results['filter_self'] == False and results['filtered_count'] == 0:
            print("✓✓�?自过滤功能已正确禁用")
        else:
            print("�?自过滤状态需要检�?)
        
        memory_stable = results['memory_delta_mb'] < 10
        print(f"�?内存稳定�? {'通过' if memory_stable else '警告'} (增量: {results['memory_delta_mb']:.2f}MB)")
        
        print("\n事件覆盖情况:")
        type_counts = {}
        for evt in events:
            ct = evt['event_type']
            type_counts[ct] = type_counts.get(ct, 0) + 1
        
        print(f"  - MOVE: {type_counts.get('MOVE', 0)} �?)
        print(f"  - LEFT_DOWN: {type_counts.get('LEFT_DOWN', 0)} �?)
        print(f"  - LEFT_UP: {type_counts.get('LEFT_UP', 0)} �?)
        print(f"  - RIGHT_DOWN: {type_counts.get('RIGHT_DOWN', 0)} �?)
        print(f"  - RIGHT_UP: {type_counts.get('RIGHT_UP', 0)} �?)
        print(f"  - SCROLL: {type_counts.get('SCROLL', 0)} �?)
        print(f"  - DRAG: {type_counts.get('DRAG', 0)} �?)
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--monitor":
            monitor_process(sys.argv[2], sys.argv[3])
        elif sys.argv[1] == "--simulator":
            simulator_process(sys.argv[2], sys.argv[3])
    else:
        run_integration_test()