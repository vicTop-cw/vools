---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: PLACEHOLDER
    ReservedCode1: PLACEHOLDER
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: PLACEHOLDER
    ReservedCode2: PLACEHOLDER
---

# Zh

```json #!cfg
{
  "id": "actus.generated.zh",
  "name": "Zh",
  "version": "1.0.0",
  "trust": "sandbox",
  "deps": [],
  "entry": "main",
  "description": "做一个计算器",
  "usage": "\u8c03\u7528\u793a\u4f8b: actus_generated_zh({\"param\": \"value\"});\n\u8fd4\u56de: {\"status\": \"ok\"}",
  "author": "ai-scaffold",
  "platform": ["desktop"],
  "permissions": ["files:read"],
  "args": {
    "type": "object",
    "properties": {
      "param": { "type": "string", "description": "参数说明" }
    },
    "required": ["param"]
  },
  "ai": { "generated": true, "author": "ai-scaffold", "evolve_policy": "confirm" }
}
```

```python #!run tag=main
"""
动作入口函数（内联模板）。

入参:
    param (str): 从 args 传入的参数。
返回:
    dict: 执行结果。
"""

def main(param: str) -> dict:
    # TODO: 实现动作逻辑
    return {"status": "ok", "result": param}


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
