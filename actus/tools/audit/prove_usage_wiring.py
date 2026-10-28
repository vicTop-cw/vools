# -*- coding: utf-8 -*-
"""只读验证：AI 调用收口接线后，成本账本从 0 行变 >0 行，且 cost_usd 口径诚实。

不联网：把 provider 的 urllib.request.urlopen 换成返回固定 JSON 的桩。
"""
import json, os, sys, tempfile
from datetime import datetime
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import _ai_local_bootstrap; _ai_local_bootstrap.install()

from vools.actus import cost
from vools.actus.ai import usage_record_stats
from vools.actus.ai.base import LLMResponse, Message
from vools.actus.ai.providers import openai_compat, anthropic

cost.COSTS_DIR = tempfile.mkdtemp()
month = datetime.now().strftime('%Y-%m')
LEDGER = os.path.join(cost.COSTS_DIR, month + '.jsonl')

def ledger_lines():
    if not os.path.exists(LEDGER):
        return []
    return [l for l in open(LEDGER, encoding='utf-8').read().splitlines() if l.strip()]

def show_summary(tag):
    s = cost.get_cost_summary(month)
    print('   [%s] calls=%d total_usd=%s tokens_total=%s unknown_cost=%s/%s ledger_complete=%s'
          % (tag, s['calls'], s['total_usd'], s['tokens_total'],
             s['calls_unknown_cost'], s['tokens_unknown_cost'], s['ledger_complete']))
    return s


class _FakeHTTP(object):
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode('utf-8')
    def read(self):
        return self._raw
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def stub_openai(payload):
    openai_compat.urllib.request.urlopen = lambda req, timeout=None: _FakeHTTP(payload)

def stub_anthropic(payload):
    anthropic.urllib.request.urlopen = lambda req, timeout=None: _FakeHTTP(payload)


print('### 0) 前置：账本行数 =', len(ledger_lines()), '| summary =', show_summary('before'))

print('\n### 1) OpenAI 兼容端点成功调用（gpt-4o-mini 在价格表里）')
stub_openai({
    'model': 'gpt-4o-mini',
    'choices': [{'message': {'content': '你好'}, 'finish_reason': 'stop'}],
    'usage': {'prompt_tokens': 700, 'completion_tokens': 40},
})
client = openai_compat.OpenAICompatClient(
    base_url='http://stub.local/v1', model='gpt-4o-mini', env_name='')
resp = client.complete([Message(role='user', content='hi')])
print('   AI 返回: stop_reason=%r content=%r total_tokens=%s'
      % (resp.stop_reason, resp.content, resp.total_tokens))
lines = ledger_lines()
print('   账本行数 =', len(lines))
row = json.loads(lines[-1])
print('   新增账本行:', json.dumps({k: row.get(k) for k in
      ('action_id','provider','model','cost_usd','tokens','cost_source','price_per_1k','prompt_tokens','completion_tokens')},
      ensure_ascii=False))
expected = round(740 / 1000.0 * 0.0005, 8)
print('   期望成本 740/1000*0.0005 =', expected, '| 实得 =', row['cost_usd'],
      '| 一致' if row['cost_usd'] == expected else '| 不一致')
show_summary('after openai')

print('\n### 2) Anthropic 成功调用（claude-3-5-sonnet-latest，在价格表里）')
stub_anthropic({
    'model': 'claude-3-5-sonnet-latest',
    'content': [{'type': 'text', 'text': 'hi'}],
    'usage': {'input_tokens': 200, 'output_tokens': 100},
})
a = anthropic.AnthropicClient(api_key='x', base_url='http://stub.local/v1',
                              model='claude-3-5-sonnet-latest')
r2 = a.complete([Message(role='user', content='hi')])
row2 = json.loads(ledger_lines()[-1])
print('   AI 返回 stop_reason=%r total_tokens=%s' % (r2.stop_reason, r2.total_tokens))
print('   账本行:', json.dumps({k: row2.get(k) for k in
      ('provider','model','cost_usd','tokens','cost_source','price_per_1k')}, ensure_ascii=False))
show_summary('after anthropic')

print('\n### 3) 模型不在价格表 → cost_usd=null（不编数字）')
stub_openai({
    'model': 'totally-unlisted-model-9x',
    'choices': [{'message': {'content': 'x'}, 'finish_reason': 'stop'}],
    'usage': {'prompt_tokens': 300, 'completion_tokens': 50},
})
c3 = openai_compat.OpenAICompatClient(
    base_url='http://stub.local/v1', model='totally-unlisted-model-9x', env_name='')
r3 = c3.complete([Message(role='user', content='hi')])
row3 = json.loads(ledger_lines()[-1])
print('   账本行:', json.dumps({k: row3.get(k) for k in
      ('model','cost_usd','tokens','cost_source','price_per_1k')}, ensure_ascii=False))
s3 = show_summary('after unknown-price')
print('   incomplete_reasons =', s3['incomplete_reasons'],
      '| calls_unknown_cost =', s3['calls_unknown_cost'])

print('\n### 4) 失败响应不记账（无密钥 auth 错误）')
before = len(ledger_lines())
bad = openai_compat.OpenAICompatClient(base_url='http://stub.local/v1',
                                       model='gpt-4o-mini', env_name='NO_SUCH_KEY')
rb = bad.complete([Message(role='user', content='hi')])
after = len(ledger_lines())
print('   stop_reason=%r failed=%s | 账本行数 %d -> %d（应不变）'
      % (rb.stop_reason, rb.failed, before, after))

print('\n### 5) 记账通道炸掉时，AI 调用仍必须成功')
import vools.actus.cost as cost_mod
orig_write = cost_mod.record_cost
cost_mod.record_cost = lambda *a, **k: (_ for _ in ()).throw(OSError('disk full (stub)'))
try:
    stub_openai({
        'model': 'gpt-4o-mini',
        'choices': [{'message': {'content': 'survived'}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
    })
    r5 = openai_compat.OpenAICompatClient(
        base_url='http://stub.local/v1', model='gpt-4o-mini', env_name='').complete(
            [Message(role='user', content='hi')])
    print('   AI 返回 content=%r stop_reason=%r（未被记账故障影响）'
          % (r5.content, r5.stop_reason))
finally:
    cost_mod.record_cost = orig_write
print('   usage_record_stats() =', usage_record_stats())

print('\n### 6) check_budget 现在能反映真实调用')
print('   ', json.dumps(cost.check_budget(10.0), ensure_ascii=False, sort_keys=True))
print('\n### 7) 最终账本（%d 行）' % len(ledger_lines()))
for line in ledger_lines():
    d = json.loads(line)
    print('   ', json.dumps({k: d.get(k) for k in ('provider','model','cost_usd','tokens','cost_source')}, ensure_ascii=False))
