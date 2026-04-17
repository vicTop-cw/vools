from itertools import chain,zip_longest,groupby
import itertools
from sys import maxsize as maxint
from typing import Iterable
from functools import reduce,wraps
from inspect import isgeneratorfunction,signature
from collections import deque
from operator import itemgetter
from ..functional.placeholder import _
from ..config import config

__all__ = ['Seq','NONE']
_expr = _.__expr__
_NONE_is_None = config.other['NONE_is_None']

class _NONE:
    __slots__ = ()
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __eq__(self, other):
        if other is None:
            return _NONE_is_None
        return other is NONE
    
    def __bool__(self):
        return False
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __repr__(self):
        return "NONE"


NONE = _NONE()



class SeqBase:
    __slots__ = ['_last','_collection','_origin','_current']
    
    class _SeqIterator:
        __slots__ = ['_seq','_position']
        
        def __init__(self,it):
            self._seq = it
            self._position = -1
            
        
        def __next__(self):
            self._position += 1
            if (len(self._seq._collection) > self._position or
                self._seq._fill_to(self._position)):
                return self._seq._collection[self._position]
            raise StopIteration()
            
    def __init__(self,*origins):
        self._collection = []
        self._last = -1
        self._current = -1
        l = len(origins)
        if l == 1:
            if hasattr(origins[0],"collect"):
                self._origin = iter(origins[0].collect())
            else:
                self._origin = iter(origins[0]) if origins[0] else iter([])
        elif l == 0:
            self._origin = iter([])
        else:
            self._origin = iter(origins)

    def __lshift__(self,rv):
        if callable(rv):
            cnt= len(signature(rv).parameters)
            if cnt ==0:
                it = rv()
                self._origin = chain(self._origin,it)
                return self
            return self.__class__(rv(i) for i in self._evaluate())
        self._origin = chain(self._origin,rv)
        return self
    
    def cursor(self):
        return self._last + 1
    
    def _fill_to(self,ix):
        if self._last >= ix:
            return True
        
        while self._last < ix:
            try:
                n = next(self._origin)
            except StopIteration:
                return False
            self._last += 1
            self._collection.append(n)
        
        return True
    
    def __iter__(self):
        return self._SeqIterator(self)
    
    def __next__(self):
        self._current += 1
        if not self._fill_to(self._current):
            raise StopIteration()
        return self._collection[self._current]   
    
    def __getitem__(self,ix):
        if isinstance(ix,int):
            if ix < 0 : raise TypeError("invalid argument negative value")
            self._fill_to(ix)
        elif isinstance(ix,slice):
            l,h,s = ix.indices(maxint)
            if s == 0 :raise ValueError('Step must not be 0')
            return self.__class__() << map(self.__getitem__,range(l,h,s or 1))
        else:
            raise TypeError('invalid argument type')
        
        return self._collection.__getitem__(ix)
    
    @classmethod    
    def of(cls,*args):
        if len(args) == 1:
            return cls.from_callable(lambda:args[0],stop_func=lambda x:x is not NONE)
        return cls(*args)
    
    @classmethod
    def range(cls,start,stop=None,step=1):
        if stop is None:
            stop = start
            start = 0
        return cls(range(start,stop,step))
    @classmethod
    def cycle(cls,func,times=None):
        if isgeneratorfunction(func):
            return cls(func())
        if times is None:
            times = float('inf')
        else:
            times = int(times)
            if times < 0:
                raise ValueError('times must be non-negative')
        def gen():
            nonlocal times
            while True:
                yield func()
                times -= 1
                if times == 0:
                    break
        return cls(gen())
    
        
    @classmethod
    def from_callable(cls,gen,*args,stop_func=None,**kwargs):
        stop = lambda x : x is NONE if stop_func is None else stop_func(x)
        if isgeneratorfunction(gen):
            def g():
                for v in gen(*args,**kwargs):
                    yield v
                    if stop(v):
                        break
            return cls(g())
        init_value = args[0] if args else NONE
        if init_value is NONE:
            if not callable(gen):
                raise TypeError('invalid argument Type,must callable or gen ')
            def g():
                while True:
                    v = gen()
                    yield v
                    if stop(v):
                        break
            return cls(g())
        params = signature(gen).parameters
        if len(params) == 0:
            def g():
                nonlocal init_value
                yield init_value
                while True:
                    init_value = gen()
                    if stop(init_value):
                        break
                    yield init_value
            return cls(g())
        elif len(params) == 1:
            def g():
                nonlocal init_value
                yield init_value
                while True:
                    init_value = gen(init_value)
                    if stop(init_value):
                        break
                    yield init_value
            return cls(g())
        else:
            def g():
                nonlocal init_value
                yield init_value
                while True:
                    init_value = gen(init_value,*args[1:],**kwargs)
                    if stop(init_value):
                        break
                    yield init_value
            return cls(g())
    
_yib = lambda x:isinstance(x, Iterable) and not isinstance(x, (str,bytes,bytearray))
_identify = lambda x : x
_compact = lambda x : x is not None
def _pipe(*funcs):
    def _inn(source):
        return reduce(lambda x,f:f(x),funcs,source)
    return _inn

def _compose(*funcs):
    return _pipe(*funcs[::-1])

class Seq(SeqBase):
    def __init__(self,*origins):
        super().__init__(*origins)
        self._ops = []
        self._active_op = _identify
    def _add_op(self,op,is_filter=False):
        self._ops.append((op,is_filter))
        o = (lambda x: x if op(x) else NONE ) if is_filter else op
        self._active_op = o if not self._active_op else _pipe(self._active_op,o)
        return self
    
    @property
    def unique(self):
        rs = []
        d = rs.append
        for i in self._evaluate():
            if i not in s:
                d(i)
                rs.append(i)
        return rs
    
    def distinct(self,key=None):
        if key is None:
            key = _identify
        def gen():
            s = set()
            d =s.add
            for i in self._evaluate():
                k = key(i)
                if k not in s:
                    d(k)
                    yield i
                    
        return self.__class__(gen())
    
    def group_by(self,key=None):
        if key is None:
            key = _identify
        def gen():
            for k,g in groupby(sorted(self._evaluate(),key=key),key=key):
                yield k,list(map(itemgetter(1),g))
        return self.__class__(gen())
    
    def grouper(self,n,fillvalue=None):
        def gen():
            args = [iter(self._evaluate())] * n
            for i in zip_longest(*args,fillvalue=fillvalue):
                yield i
        return self.__class__(gen())
    
    
    def prepend(self,*args):
        return self.__class__(chain(*[iter(a) if isinstance(a,Iterable) else [a] for a in args],self._evaluate()))
    
    def extend(self,*args):
        return self.__class__(chain(self._evaluate(),*[iter(a) if isinstance(a,Iterable) else [a] for a in args]))
    
    def add(self,*args,**kwargs):
        return self.__class__(chain(self._evaluate(),args,kwargs.values()))
    
    def add_reversed(self,*args,**kwargs):
        return self.__class__(chain(args,kwargs.values(),self._evaluate()))
    
    def sort_by(self,key=None,reverse=False):
        return self.__class__(sorted(self._evaluate(),key=key,reverse=reverse))
    
    def reverse(self):
        return self.__class__(reversed(list(self._evaluate())))
    
    def sorted(self,key=None,reverse=False):
        return list(sorted(self._evaluate(),key=key,reverse=reverse))
    
    def count_by(self,key=None):
        if key is None:
            key = _identify
        def gen():
            for k,g in groupby(sorted(self._evaluate(),key=key),key=key):
                yield k,len(list(g))
        return self.__class__(gen())
    
    def reduce_by(self,key=None,func=None):
        if key is None:
            key = _identify
        if func is None:
            func = lambda x,y:x+y
        def gen():
            for k,g in groupby(sorted(self._evaluate(),key=key),key=key):
                yield k,reduce(func,g)
        return self.__class__(gen())
    
    def any(self,func=None):
        if func is None:
            func = _compact
        return any(func(i) for i in self._evaluate())
    
    def all(self,func=None):
        if func is None:
            func = _compact
        return all(func(i) for i in self._evaluate())
    
    def find(self,func=None):
        if func is None:
            func = _compact
        for i in self._evaluate():
            if func(i):
                return i
        return NONE
    
    def find_index(self,func=None):
        if func is None:
            func = _compact
        for i,v in enumerate(self._evaluate()):
            if func(v):
                return i
        return NONE
    
    def accum(self,func,initial=None):
        if initial is None:
            return self.__class__(itertools.accumulate(self._evaluate(),func))
        else:
            return self.__class__(itertools.accumulate(self._evaluate(),func,initial))
    def __iadd__(self,other):
        return self.add(other)
    
    def __rshift__(self, func):
        return self.map(func)
    
    def __or__(self, other):
        if not callable(other):
            raise TypeError('unsupported operand type(s) for |: \'{}\' and \'{}\''.format(type(self).__name__,type(other).__name__))
        return other(self._evaluate())
    
    def run(self,func):
        if not callable(func):
            raise TypeError('func must be callable')
        return func(self)
    
    def __add__(self,other):
        return self.add(other)
    def __radd__(self,other):
        return self.add_reversed(other)
    
    def __len__(self):
        return sum(1 for _ in self._evaluate())
    
    def __bool__(self):
        return any(True for _ in self._evaluate())
    
    def __repr__(self):
        s =self.take(21,True)
        if len(s) == 21:
            s.append('...')
        return f"Seq({s})"
    
    def __str__(self):
        s =self.take(21,True)
        if len(s) == 21:
            s.append('...')
        return f"Seq({s})"
    
    def _evaluate(self):
        op = self._active_op
        for i in self:
            x = op(i)
            if x is not NONE:
                yield x

    def map(self,*funcs):
        for m in funcs:
            f = lambda x:NONE if x is NONE else m(x)
            self._add_op(f)
        return self
    
    def filter(self,*funcs):
        for m in funcs:
            f = lambda x:NONE if x is NONE or not m(x) else x
            self._add_op(f,True)
        return self
    
    def filterfalse(self,*funcs):
        for m in funcs:
            f = lambda x:NONE if x is NONE or m(x) else x
            self._add_op(f,True)
        return self
    
    filter_not = filternot = filter_false = filterfalse


    def _starmap(self,*funcs):
        funcs = list(funcs)
        while funcs:
            k = funcs.pop(0)
            f = lambda x:NONE if x is NONE else (k(*x) if _yib(x) else k(x))
            self._add_op(f)
        return self
        
    def _mapmap(self,*funcs):
        if len(funcs) == 1:
            func = funcs[0]
            f = lambda x:NONE if x is NONE else ([NONE if i is NONE else func(i) for i in x] if _yib(x) else func(x))
            self._add_op(f)
            return self
        elif len(funcs) == 0:
            return self
        
        def _inner(x):
            nonlocal funcs
            if _yib(x):
                it = zip_longest(x,funcs,fillvalue=NONE)
                return [NONE if i is NONE or f is NONE else f(i) for i,f in it]
            return [f(x) for x in funcs]
        self._add_op(_inner)
        return self

    def where(self,*funcs,mode='single', func_type='lambda'):
        f = lambda ff : _expr(ff,mode,func_type)
        return self.filter(*map(f,funcs))
    
    def wherenot(self,*funcs,mode='single', func_type='lambda'):
        f = lambda ff : _expr(ff,mode,func_type)
        return self.filterfalse(*map(f,funcs))

    def select(self,*funcs,mode='single', func_type='lambda'):
        f = lambda ff : _expr(ff,mode,func_type)
        return self.map(*map(f,funcs))

    def starmap(self,*funcs,mode='single', func_type='lambda'):
        f = lambda ff : _expr(ff,mode,func_type)
        return self._starmap(*map(f,funcs))

    def mapmap(self,*funcs,mode='single', func_type='lambda'):
        f = lambda ff : _expr(ff,mode,func_type)
        return self._mapmap(*map(f,funcs))

    def collect(self):
        return list(self._evaluate())
    
    def reduce(self,func,init=None):
        if init is None:
            return reduce(func,self._evaluate())
        else:
            return reduce(func,self._evaluate(),init)
    def take_while(self,func):
        # def gen():
        #     for i in self._evaluate():
        #         if func(i):
        #             yield i
        #         else:
        #             break
        # return   self.__class__(gen())
        return self.__class__(itertools.takewhile(func,self._evaluate()))
    
    def drop_while(self,func):
        # def gen():
        #     for i in self._evaluate():
        #         if not func(i):
        #             yield i
        #             break
        # return   self.__class__(gen()) 
        return self.__class__(itertools.dropwhile(func,self._evaluate()))
    def take(self,n,action=False):
        if action:
            rs = []
            d = rs.append
            for i,v in enumerate(self._evaluate()):
                if i<n:
                    d(v)
                else:
                    break
            return rs

        def gen():
            for i,v in enumerate(self._evaluate()):
                if i<n:
                    yield v
                else:
                    break
        return   self.__class__(gen())

    def tee(self,n=2,fillvalue=None):
        def gen():
            q = deque(maxlen=n)
            d = q.append
            for i in self._evaluate():
                d(i)
                if len(q) == n:
                    yield tuple(q)
            else:
                for i in range(n-1):
                    d(fillvalue)
                    yield tuple(q)
                    
        return self.__class__(gen())
    def skip(self,n):
        def gen():
            for i,v in enumerate(self._evaluate()):
                if i >= n:
                    yield v
        return   self.__class__(gen())  

    def enumerate(self,n=0):
        def gen():
            for i,v in enumerate(self._evaluate(),n):
                yield i,v
        return   self.__class__(gen())  
    
    def zip(self,*its):
        def gen():
            for i in zip(self._evaluate(),*its):
                yield i
        return   self.__class__(gen())  
    
    def zip_longest(self,*its,fillvalue=None):
        def gen():
            for i in zip_longest(self._evaluate(),*its,fillvalue=fillvalue):
                yield i
        return self.__class__(gen())
    def flatten(self):
        def gen():
            for i in self._evaluate():
                if _yib(i):
                    for j in i:
                        yield j
                else:
                    yield i
        return self.__class__(gen())
                
    def as_list(self):
        return list(self._evaluate())
    
    def flatmap(self,func = _identify,mode='before' ):
        def gen():
            if mode == 'before':
                for i in self._evaluate():
                    i = func(i)
                    if _yib(i):
                        for j in i:
                            yield j
                    else:
                        yield i
            elif mode == 'after':
                for i in self._evaluate():
                    if _yib(i):
                        for j in i:
                            yield func(j)
                    else:
                        yield func(i)
            else:
                raise ValueError('mode must be <before> or <after> ')
        return self.__class__(gen())
        

    def flatmap_ex1(self,map_before = _identify,
                  map_after= _identify
                  ,filter_before_before =_compact
                  ,filter_before_after =_compact
                  ,filter_after_before =_compact
                  ,filter_after_after =_compact):
        """auto filter None value"""
        def _before(i):
            if filter_before_before(i):
                i = map_before(i)
                if filter_before_after(i):
                    return True,i
            return False,None
        
        def _after(j):
            if filter_after_before(j):
                j = map_after(j)
                if filter_after_after(j):
                    return True,j
            return False,None
        
        def gen():
            for i in self._evaluate():
                p,i = _before(i)
                if p:
                    if _yib(i):
                        for j in i:
                            p1,j = _after(j)
                            if p1 : yield j
                    else:
                        if p1 : yield i
        return self.__class__(gen())
    
    def flatmap_ex(self,before_func=None,after_func=None):
        """
        before_func :单参函数 并返回 一个 tuple2(bool p,value v)，对每个元素迭代形成的值
                p为假 丢弃，为真 保留 v
        after_func : 单参函数 并返回 一个 tuple2(bool p,value v)，对 步骤一保留下来的值进行处理
                p为假 丢弃，为真 保留 v
        """
        before_func = (lambda x: (x is not None,x) ) if before_func is None else before_func
        after_func = (lambda x: (x is not None,x) ) if after_func is None else after_func
        def gen():
            for i in self._evaluate():
                p,i = before_func(i)
                if p:
                    if _yib(i):
                        for j in i:
                            p1,j = after_func(j)
                            if p1 : yield j
                    else:
                        if p1 : yield i
        return self.__class__(gen())    
    @property
    def size(self):
        return sum(1 for _ in self._evaluate())
    
    def join (self,sep=','):
        return sep.join(str(i) for i in self._evaluate())
    @classmethod 
    def ensure_seq(cls,func):
        """ ensure func is a generator function ,then return a Seq result """
        if not callable(func):
            raise TypeError('func must be callable or generator function')
        @wraps(func)
        def _inner(*args,**kwargs):
            return cls(func(*args,**kwargs))
        return _inner
            
    def register(self,func):
        """ register a function to Seq instance """
        if not callable(func):
            @property
            def _prop(self):
                return func
            setattr(self,func.__name__ or str(func) ,_prop)
            return _prop
        @wraps(func)
        def _inner(self,*args,**kwargs):
            return func(self,*args,**kwargs)
        setattr(self,func.__name__,_inner)
        


if __name__ == '__main__':      
    s = Seq(range(10)) 
    for i in s[3:7]:
        print(i,end=',')
    else:
        print()
    from random import randint
    
    s1 = Seq.from_callable(lambda : randint(1, 3),lambda x : x == 2)
    print(s.take(4),s.take(7))
    print(list(s.skip(3)))
    z = Seq(s.zip_longest(range(3),fillvalue = randint(1, 100)))
    print(list(z.flatten()))
    print(list(s.flatmap_ex(lambda x : ( x % 2,(x,randint(1,10))))))
    
    print(_pipe(lambda x:x+1,lambda x:x*2)(3))
    
    k = s.map(lambda x:x+1).filter(lambda x:x%2==0).map(lambda x:x*2)
    print(k.collect(),k.reduce(lambda x,y:x+y,0))
    
    data = [1,2,3,4,5,6,7,8,9,10]
    data = zip_longest(data,data[::-1],data,data[::-2],fillvalue=0)
    data = Seq(data).flatmap_ex(lambda x : (1,[*x,randint(1,10)])).reduce_by(None,lambda x,y:x+y - x*y)
    d = data.take_while(lambda x:x[1]<5).collect()
    print(d)
    
    
    print(Seq(range(10)).grouper(3,'c').collect())
    
    
    def gen():
        if not hasattr(gen,'n'):
            gen.n = -1
        gen.n += 1
        return gen.n
    

    def join(s):
        return ','.join(str(i) for i in s)
    
    c = Seq.cycle(gen,10) >> (lambda x:x*2 ) >> (lambda x:x+1 if x > 5 else NONE) 
    print(c.collect(),c.tee(3).collect())
    
    print(c | join)
    # print(c.tee(3) | Seq.flatmap | join)

    class A:
        def __init__(self,x):
            self.x = x
        @Seq.ensure_seq
        def gen(self):
            while True:
                self.x += 1
                yield randint(1, 100) + self.x
    
        def register(self, func):
            @wraps(func)
            def _inner(self,*args, **kwargs):
                return func(self,*args, **kwargs)
            setattr(self,func.__name__,_inner)
            return _inner
    a = A(0)
    print(a.gen().take(5,True))
    
    def f(x):
        print(x,'registeed')
    
    a.register(f)
    a.f('sd')
    
    s = Seq.from_callable(_+1,0)

    s = s.take_while(_<=10)
    # s = s.take(30)
    print(s)

    # s = Seq(f()).take_while(_>3)
    # print(s.collect())

