# vools.recorder

录制回放模块，提供屏幕录制和操作回放功能。

## 主要功能

- **录制**: `Recorder` - 录制用户操作
- **回放**: `Player` - 回放录制的操作
- **解析**: `Parser` - 解析录制数据
- **GUI**: 图形界面支持

## 核心类

| 名称 | 说明 |
|------|------|
| `Recorder` | 录制器 |
| `Player` | 播放器 |
| `Parser` | 解析器 |
| `Action` | 操作对象 |

## 使用示例

```python
from vools.recorder import Recorder, Player

# 录制
recorder = Recorder()
recorder.start()
# ... 执行操作 ...
recorder.stop()
recorder.save('recording.json')

# 回放
player = Player()
player.load('recording.json')
player.play()
```

## 注意事项

- 需要 `pywin32` 依赖（Windows）