# 键鼠操作录制与回放模块 (Recorder & Player)

## Why
需要一套完整的键鼠操作录制与回放系统，能够记录用户在屏幕上的操作（键盘输入、鼠标点击/移动/滚动），并支持回放这些操作。参考 Quicker InputScript 的命令格式，提供一套 Pythonic 的录制脚本格式和回放引擎。

## What Changes

### 新增子包
- `vools.recorder` - 录制与回放核心模块
- `vools.recorder.recorder` - 操作录制器
- `vools.recorder.player` - 操作回放器
- `vools.recorder.actions` - 操作动作定义
- `vools.recorder.script` - 录制脚本解析与生成
- `vools.recorder.typedefs` - 类型定义

### 核心功能
1. **操作录制** - 监听键盘、鼠标、剪贴板事件，记录为结构化数据
2. **操作回放** - 将录制数据转换为系统 API 调用，按时间顺序执行
3. **脚本格式** - 定义可序列化的操作脚本格式（YAML/JSON）
4. **脚本命令** - 参考 Quicker InputScript，支持以下命令：
   - 键盘：`keydown`、`keyup`、`keypress`、`type`、`hotkey`、`delay`
   - 鼠标：`moveto`、`move`、`click`、`dbclick`、`down`、`up`、`wheel`、`hwheel`
   - 剪贴板：`setclip`、`paste`
   - 组合：`repeat`

## Impact

### Affected specs
- `keyboard_mouse` - 提供键鼠事件监听和模拟能力
- `clipboard` - 提供剪贴板监听和设置能力
- `reactive.operators` - 提供响应式操作符

### Affected code
- 新增 `vools/recorder/` 目录
- 新增 `vools/__init__.py` 导出

## ADDED Requirements

### Requirement: 操作动作基类
系统 SHALL 提供 `Action` 基类，定义所有操作动作的统一接口。

#### Scenario: 基础动作
- **WHEN** 创建 `KeyAction(key='a', action_type='keypress')`
- **THEN** action 可序列化到字典，可延迟执行

### Requirement: 录制器 (Recorder)
系统 SHALL 提供 `Recorder` 类，能够同时监听键盘、鼠标、剪贴板事件。

#### Scenario: 开始录制
- **WHEN** 调用 `recorder.start()`
- **THEN** 开始监听所有输入设备，记录时间戳

#### Scenario: 停止录制
- **WHEN** 调用 `recorder.stop()`
- **THEN** 返回录制结果 `Recording` 对象，包含所有动作列表

### Requirement: 录制结果 (Recording)
系统 SHALL 提供 `Recording` 数据类，包含录制元数据和动作列表。

#### Scenario: 保存录制
- **WHEN** 调用 `recording.to_yaml('output.yaml')`
- **THEN** 生成 YAML 格式脚本文件

#### Scenario: 加载录制
- **WHEN** 调用 `Recording.from_yaml('output.yaml')`
- **THEN** 返回包含所有动作的 Recording 对象

### Requirement: 回放器 (Player)
系统 SHALL 提供 `Player` 类，能够回放录制操作。

#### Scenario: 回放录制
- **WHEN** 调用 `player.play(recording, speed=1.0)`
- **THEN** 按时间顺序执行所有动作，支持速度调节

#### Scenario: 暂停/恢复回放
- **WHEN** 调用 `player.pause()` / `player.resume()`
- **THEN** 回放暂停或继续

#### Scenario: 停止回放
- **WHEN** 调用 `player.stop()`
- **THEN** 回放立即停止

### Requirement: 脚本命令解析
系统 SHALL 提供脚本解析器，支持从 Quicker InputScript 格式导入动作。

#### Scenario: 解析 Quicker 脚本
- **WHEN** 解析 Quicker InputScript 格式字符串
- **THEN** 返回对应的 Action 列表

#### Scenario: 生成 Quicker 脚本
- **WHEN** 调用 `recording.to_quicker_script()`
- **THEN** 生成 Quicker InputScript 兼容的脚本字符串

### Requirement: 支持的操作命令

#### Scenario: 键盘命令
- **WHEN** 解析 `keydown:A`、`keyup:A`、`keypress:A`、`type:hello`、`hotkey:Ctrl+S`、`delay:1000`
- **THEN** 创建对应的 Action 对象

#### Scenario: 鼠标命令
- **WHEN** 解析 `moveto:100,200`、`click:left`、`wheel:3`、`hwheel:-2`
- **THEN** 创建对应的 Action 对象

#### Scenario: 剪贴板命令
- **WHEN** 解析 `setclip:hello world`、`paste`
- **THEN** 创建对应的 Action 对象

## Supported Commands (参考 Quicker InputScript)

### 键盘命令
| 命令 | 格式 | 说明 |
|------|------|------|
| keydown | `keydown:KeyName` | 按下按键 |
| keyup | `keyup:KeyName` | 抬起按键 |
| keypress | `keypress:KeyName` | 点击按键 |
| type | `type:text` | 输入文本 |
| hotkey | `hotkey:Ctrl+C` | 发送快捷键 |
| delay | `delay:1000` | 等待（毫秒） |

### 鼠标命令
| 命令 | 格式 | 说明 |
|------|------|------|
| moveto | `moveto:x,y` 或 `moveto:50%,50%` | 移动到绝对坐标 |
| move | `move:dx,dy` | 相对移动 |
| click | `click:left` / `click:right` / `click:middle` | 点击 |
| dbclick | `dbclick:left` | 双击 |
| down | `down:left` | 按下鼠标键 |
| up | `up:left` | 抬起鼠标键 |
| wheel | `wheel:3` | 垂直滚动（正值向上） |
| hwheel | `hwheel:-2` | 水平滚动 |

### 剪贴板命令
| 命令 | 格式 | 说明 |
|------|------|------|
| setclip | `setclip:text` | 设置剪贴板内容 |
| paste | `paste` | 粘贴 |

## Design

### 模块结构
```
vools/recorder/
├── __init__.py           # 导出主要类和函数
├── typedefs.py           # 类型定义 (Action, Recording, ActionType 等)
├── actions.py            # 动作类定义
├── recorder.py           # 录制器
├── player.py             # 回放器
├── parser.py             # 脚本解析器
└── script.py            # 脚本生成器
```

### 核心类

```python
# typedefs.py
class ActionType(Enum):
    KEY_DOWN = "keydown"
    KEY_UP = "keyup"
    KEY_PRESS = "keypress"
    TYPE = "type"
    HOTKEY = "hotkey"
    MOVE_TO = "moveto"
    MOVE_REL = "move"
    CLICK = "click"
    DBCLICK = "dbclick"
    MOUSE_DOWN = "down"
    MOUSE_UP = "up"
    WHEEL = "wheel"
    HWHEEL = "hwheel"
    SET_CLIP = "setclip"
    PASTE = "paste"
    DELAY = "delay"

@dataclass
class Action:
    action_type: ActionType
    timestamp: float  # 相对于录制开始的时间（毫秒）
    params: Dict[str, Any]
    
@dataclass 
class Recording:
    start_time: datetime
    end_time: datetime
    actions: List[Action]
    tags: Dict[str, Any]

# recorder.py
class Recorder:
    def __init__(
        self,
        record_keyboard: bool = True,
        record_mouse: bool = True,
        record_clipboard: bool = True,
        deduplicate_interval: float = 0.05,  # 相同事件去重间隔
    )
    def start(self) -> None
    def stop(self) -> Recording
    def is_recording(self) -> bool

# player.py  
class Player:
    def __init__(
        self,
        keyboard_dispatcher: KeyboardDispatcher,
        mouse_dispatcher: MouseDispatcher,
        clipboard_subject: ClipboardSubject,
    )
    def play(self, recording: Recording, speed: float = 1.0) -> None
    def pause(self) -> None
    def resume(self) -> None
    def stop(self) -> None
    @property
    def is_playing(self) -> bool
```

## Non-Functional Requirements

### NFR-1: 性能
- 回放延迟 < 10ms（不含用户指定的 delay）
- 录制 CPU 使用率 < 5%

### NFR-2: 准确性
- 鼠标移动精度 ±1 像素
- 时间戳精度 ±10ms

### NFR-3: 兼容性
- 生成的脚本兼容 Quicker InputScript 格式
- 支持导出/导入 JSON 和 YAML 格式

## Open Questions
- [ ] 是否需要支持屏幕坐标的百分比形式？（Quicker 支持 `moveto:50%,50%`）
- [ ] 是否需要支持动作重复 (`repeat:3`)？
- [ ] 是否需要支持条件执行？
- [ ] 录制时是否需要可选排除特定区域/窗口？
