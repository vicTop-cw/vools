"""
vools-recorder æµè¯
"""
import sys
import os
import pytest
import json
import yaml
from datetime import datetime
from typing import List
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# æµè¯ç±»åå®ä¹
from vools.recorder import Action, Recording, ActionType, Parser
from vools.recorder.typedefs import MouseButton, MOD_SHIFT, MOD_CTRL, MOD_ALT, MOD_WIN


class TestAction:
    """Action æµè¯"""
    
    def test_create_key_action(self):
        action = Action(ActionType.KEY_DOWN, 100.0, {'key': 'A'})
        assert action.action_type == ActionType.KEY_DOWN
        assert action.timestamp == 100.0
        assert action.params == {'key': 'A'}
    
    def test_create_mouse_action(self):
        action = Action(ActionType.CLICK, 200.0, {'button': 'left'})
        assert action.action_type == ActionType.CLICK
        assert action.timestamp == 200.0
        assert action.params == {'button': 'left'}
    
    def test_to_dict(self):
        action = Action(ActionType.TYPE, 150.0, {'text': 'hello'})
        d = action.to_dict()
        assert d['action_type'] == 'type'
        assert d['timestamp'] == 150.0
        assert d['params'] == {'text': 'hello'}
    
    def test_from_dict(self):
        d = {'action_type': 'delay', 'timestamp': 500.0, 'params': {'ms': 1000}}
        action = Action.from_dict(d)
        assert action.action_type == ActionType.DELAY
        assert action.timestamp == 500.0
        assert action.params == {'ms': 1000}
    
    def test_serialization_roundtrip(self):
        action = Action(ActionType.HOTKEY, 300.0, {'keys': ['Ctrl', 'S']})
        json_str = action.to_json()
        restored = Action.from_json(json_str)
        assert restored.action_type == action.action_type
        assert restored.timestamp == action.timestamp
        assert restored.params == action.params
    
    def test_repr(self):
        action = Action(ActionType.MOVE_TO, 100.0, {'x': 100, 'y': 200})
        r = repr(action)
        assert 'moveto' in r
        assert '100.0ms' in r


class TestRecording:
    """Recording æµè¯"""
    
    def test_create_recording(self):
        now = datetime.now()
        actions = [
            Action(ActionType.KEY_DOWN, 0.0, {'key': 'A'}),
            Action(ActionType.KEY_UP, 100.0, {'key': 'A'}),
        ]
        recording = Recording(start_time=now, end_time=now, actions=actions)
        assert len(recording) == 2
        assert recording.duration == 100.0
    
    def test_duration_empty(self):
        recording = Recording(start_time=datetime.now(), end_time=datetime.now())
        assert recording.duration == 0.0
    
    def test_to_dict(self):
        now = datetime.now()
        actions = [Action(ActionType.CLICK, 50.0, {'button': 'right'})]
        recording = Recording(start_time=now, end_time=now, actions=actions, tags={'app': 'test'})
        d = recording.to_dict()
        assert 'start_time' in d
        assert 'end_time' in d
        assert len(d['actions']) == 1
        assert d['tags'] == {'app': 'test'}
    
    def test_json_roundtrip(self):
        now = datetime.now()
        actions = [
            Action(ActionType.TYPE, 0.0, {'text': 'hello'}),
            Action(ActionType.DELAY, 100.0, {'ms': 500}),
        ]
        recording = Recording(start_time=now, end_time=now, actions=actions)
        json_str = recording.to_json()
        restored = Recording.from_json(json_str)
        assert len(restored) == 2
        assert restored.actions[0].params['text'] == 'hello'
    
    def test_yaml_roundtrip(self):
        now = datetime.now()
        actions = [Action(ActionType.MOVE_TO, 0.0, {'x': 100, 'y': 200})]
        recording = Recording(start_time=now, end_time=now, actions=actions)
        yaml_str = recording.to_yaml()
        restored = Recording.from_yaml(yaml_str)
        assert len(restored) == 1
        assert restored.actions[0].params['x'] == 100


class TestParser:
    """Parser æµè¯"""
    
    def test_parse_key_commands(self):
        parser = Parser()
        script = '''
keydown:A
keyup:A
keypress:B
'''
        actions = parser.parse(script)
        assert len(actions) == 3
        assert actions[0].action_type == ActionType.KEY_DOWN
        assert actions[1].action_type == ActionType.KEY_UP
        assert actions[2].action_type == ActionType.KEY_PRESS
    
    def test_parse_type_command(self):
        parser = Parser()
        actions = parser.parse('type:hello world')
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.TYPE
        assert actions[0].params['text'] == 'hello world'
    
    def test_parse_delay_command(self):
        parser = Parser()
        actions = parser.parse('delay:1000')
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.DELAY
        assert actions[0].params['ms'] == 1000
    
    def test_parse_hotkey(self):
        parser = Parser()
        actions = parser.parse('hotkey:Ctrl+C')
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.HOTKEY
        assert 'Ctrl' in actions[0].params['keys']
        assert 'C' in actions[0].params['keys']
    
    def test_parse_moveto(self):
        parser = Parser()
        actions = parser.parse('moveto:100,200')
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.MOVE_TO
        assert actions[0].params['x'] == 100
        assert actions[0].params['y'] == 200
    
    def test_parse_moveto_percent(self):
        parser = Parser()
        actions = parser.parse('moveto:50%,50%')
        assert len(actions) == 1
        assert actions[0].params['is_percent'] == True
    
    def test_parse_click(self):
        parser = Parser()
        actions = parser.parse('click:left')
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.CLICK
        assert actions[0].params['button'] == 'left'
    
    def test_parse_wheel(self):
        parser = Parser()
        actions = parser.parse('wheel:3')
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.WHEEL
        assert actions[0].params['delta'] == 3
    
    def test_parse_setclip(self):
        parser = Parser()
        actions = parser.parse('setclip:hello')
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.SET_CLIP
        assert actions[0].params['text'] == 'hello'
    
    def test_parse_paste(self):
        parser = Parser()
        actions = parser.parse('paste')
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.PASTE
    
    def test_skip_comments(self):
        parser = Parser()
        script = '''// comment
keydown:A
# another comment
type:hello
'''
        actions = parser.parse(script)
        assert len(actions) == 2
    
    def test_to_script(self):
        parser = Parser()
        actions = [
            Action(ActionType.MOVE_TO, 0.0, {'x': 100, 'y': 200}),
            Action(ActionType.CLICK, 0.0, {'button': 'left'}),
            Action(ActionType.TYPE, 0.0, {'text': 'test'}),
        ]
        script = parser.to_script(actions)
        assert 'moveto:100,200' in script
        assert 'click:left' in script
        assert 'type:test' in script
    
    def test_recording_to_script(self):
        parser = Parser()
        now = datetime.now()
        actions = [
            Action(ActionType.DELAY, 0.0, {'ms': 500}),
            Action(ActionType.KEY_PRESS, 0.0, {'key': 'Enter'}),
        ]
        recording = Recording(start_time=now, end_time=now, actions=actions)
        script = parser.recording_to_script(recording)
        assert 'delay:500' in script
        assert 'keypress:Enter' in script


class TestConstants:
    """å¸¸éæµè¯"""
    
    def test_modifier_constants(self):
        assert MOD_SHIFT == 1
        assert MOD_CTRL == 2
        assert MOD_ALT == 4
        assert MOD_WIN == 8
    
    def test_mouse_button_enum(self):
        assert MouseButton.LEFT.value == 'left'
        assert MouseButton.RIGHT.value == 'right'
        assert MouseButton.MIDDLE.value == 'middle'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
