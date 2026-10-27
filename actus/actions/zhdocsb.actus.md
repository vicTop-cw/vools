---

AIGC:

    Label: "1"

    ContentProducer: 001191440300708461136T1XGW3

    ProduceID: 9f2a11add43fbf12a546606fb2b962ab_bf0c3c41af4411f18f50525400aeaaa3

    ReservedCode1: PLACEHOLDER

    ContentPropagator: 001191440300708461136T1XGW3

    PropagateID: 9f2a11add43fbf12a546606fb2b962ab_bf0c3c41af4411f18f50525400aeaaa3

    ReservedCode2: PLACEHOLDER

---



# monitor-folder



```json #!cfg

{

  "id": "actus.generated.zhdocsb",

  "name": "Zhdocsb",

  "version": "1.0.0",

  "trust": "trusted",

  "kind": "template",

  "platform": [

    "windows"

  ],

  "deps": [],

  "entry": "main",

  "description": "文件夹监控动作模板（docs/10 §B）：监听文件夹变化并触发回调动作",

  "usage": "\u8c03\u7528\u793a\u4f8b: actus_generated_zhdocsb({\"param\": \"value\"});\n\u8fd4\u56de: {\"status\": \"ok\"}",

  "author": "ai-scaffold",
  "platform": ["desktop"],
  "tests": ["tests/test_zhdocsb.py"],

  "permissions": [

    "files:read"

  ],

  "triggers": [

    {

      "type": "watch",

      "path": "${watch_path}",

      "events": [

        "create",

        "modify"

      ],

      "recursive": true,

      "debounce_ms": 500

    }

  ],

  "args": {

    "type": "object",

    "properties": {

      "watch_path": {

        "type": "string",

        "description": "要监控的文件夹路径"

      },

      "on_change_action": {

        "type": "string",

        "description": "变化时触发的动作 id"

      }

    },

    "required": [

      "watch_path"

    ]

  }

}
```



```python #!run tag=main

"""

文件夹监控入口（trusted Python 模板）。



入参:

    watch_path (str): 要监控的文件夹路径。

    on_change_action (str): 变化时触发的动作 id。

返回:

    dict: {status, watch_path, events}

"""



import json, os

def main(params: dict) -> dict:

    watch_path = params.get('watch_path')

    on_change_action = params.get('on_change_action', '')

    import os



    if not os.path.isdir(watch_path):

        return {"status": "failed", "error": f"not a directory: {watch_path}"}



    # 触发器引擎在 trigger.py 中解析 triggers 字段并启动监控

    # 此入口仅作为备用（当 action 被直接调用时）

    return {

        "status": "ok",

        "watch_path": os.path.abspath(watch_path),

        "on_change_action": on_change_action,

        "message": "watcher dispatched by trigger engine", "data": None}



# 入口自调用协议：读 ACTUS_PARAMS → 调 main(params) → 打印

params = json.loads(os.environ.get('ACTUS_PARAMS') or '{}')

print(json.dumps(main(params), ensure_ascii=False))







# 引擎契约：调用必须在模块级，见 docs/38 §1
import inspect as _zinspect, json as _zjson, os as _zos
_zparams = _zjson.loads(_zos.environ.get('ACTUS_PARAMS') or '{}')
if __name__ != "__main__" or _zparams:
    _zsig = _zinspect.signature(main).parameters
    _zhas_var_kw = any(p.kind is _zinspect.Parameter.VAR_KEYWORD
                       for p in _zsig.values())
    _zrequired_pos = [n for n, p in _zsig.items()
                      if p.kind in (_zinspect.Parameter.POSITIONAL_ONLY,
                                    _zinspect.Parameter.POSITIONAL_OR_KEYWORD)
                      and p.default is _zinspect.Parameter.empty]
    if _zhas_var_kw:
        # main(**kwargs) 形态：原样展开
        print(_zjson.dumps(main(**_zparams), ensure_ascii=False))
    elif _zrequired_pos and any(n not in _zparams for n in _zrequired_pos):
        # 有"ACTUS_PARAMS 满足不了的必需位置参数"（如外部模板的 main(params: dict)，
        # 而 ACTUS_PARAMS 给的是 {'param': ...}）：回退成位置调用 main(_zparams)。
        # 否则 main(**_zparams) 会 TypeError: missing 1 required positional argument，
        # 整个块 rc=1（实测 tests/actus/test_scaffold.py 端到端用例钉此）。
        print(_zjson.dumps(main(_zparams), ensure_ascii=False))
    else:
        # 命名参数形态：过滤掉 main 不认识的键后展开
        print(_zjson.dumps(main(**{k: v for k, v in _zparams.items()
                                   if k in _zsig}), ensure_ascii=False))

if __name__ == "__main__":
    import json, sys
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(main(**params), ensure_ascii=False, indent=2))
```

