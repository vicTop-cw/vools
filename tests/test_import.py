
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from vools import *
import vools 
from vools.oop import *
from vools.functional import *
from vools.utils import * 
from vools.data import *
from vools.config import *
from vools.datetime import *
from vools.utils import *
from vools.functional import *
from vools.shotcut import *
print(vools.__all__)
print(vools.functional.__all__)
print(vools.oop.__all__)
print(vools.data.__all__)
print(vools.datetime.__all__)
print(vools.utils.__all__)
print(vools.functional.__all__)
