from vools.bridge.freebasic import fbc
from vools.bridge.freebasic.modules import get_module

hash_code = get_module('hash_wrapper')

@fbc(module_code=hash_code)
def hash_string(input_str: str) -> str:
    '''
    dim as zstring * 1024 out_str
    dim as long result = fb_hash_md5(input_str, @out_str, 1024)
    return @out_str
    '''

result = hash_string('')
print('MD5 of empty:', result)

import hashlib
expected = hashlib.md5(b'').hexdigest()
print('Expected:', expected)
print('Match:', result == expected)

print()
result = hash_string('test')
print('MD5 of test:', result)
expected = hashlib.md5(b'test').hexdigest()
print('Expected:', expected)
print('Match:', result == expected)
