"""Debug curry issue"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.decorators import curry as curry_decorator

@curry_decorator
def process(a, b, c):
    return a + b + c

try:
    r = process(1)
    print(f"process(1) OK, type={type(r).__name__}")
    r2 = r(2)
    print(f"r(2) OK, type={type(r2).__name__}")
    r3 = r2(3)
    print(f"r2(3) = {r3}")
    assert r3 == 6
    print("ALL OK")
except Exception as e:
    import traceback
    traceback.print_exc()

# Check signature
from vools.cache import cache_info
print(f"sig cache: {cache_info()}")
