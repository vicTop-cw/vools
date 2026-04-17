from .curry_core import curry, is_curried

__all__ = ['overloads','Overloads','Selector']

_is_curried = lambda f : isinstance(f,(Selector,Overloads)) or is_curried(f)


class Selector:
    def __init__(self,*funcs):
        if not funcs:
            raise ValueError("At least one function is required")
        def gen(fs):
            for f in fs :
                if _is_curried(f):
                    f.delaied = True
                    f.is_strict = True
                    yield f
                elif callable(f):
                    yield curry(f,delaied=True,is_strict=True)
                # 如果 f 不是可调用的对象，直接 yield 它
                else:
                    yield f
                    
        self.funcs = list(gen(funcs))
        self._is_init = True
    
    def first_result(self,*args,**kwargs):
        result = self(*args,**kwargs)[0]
        if result.is_ready:
            return result()
        return result
    
    def get_result(self,shoud_full=False):
        if not self.funcs:
            raise ValueError("No function is registered")
        b = lambda f :  f.is_full if shoud_full else f.is_ready
        if all(b(f) for f in self.funcs):
            return tuple(f() for f in self.funcs)
        raise TypeError(f"Not all functions are {'ready' if not shoud_full else 'full'}")
    
    
    def __str__(self):
        return "Selector(" + '\n==========================\n'.join(map(str,self.funcs)) + ")"
    
    @staticmethod
    def _try_bound(curried_func,args,kwargs):
        try:
            return curried_func(*args,**kwargs)
        except TypeError:
            return None
    
    def register(self,func=None,returnCurried=False):
        if not self._is_init:
            raise ValueError("Selector is already used")
        if func is None:
            return lambda f : self.register(f,returnCurried)
        # 检查函数是否已经被柯里化
        if not is_curried(func):
            # 对函数进行 curry 处理
            curried_func = curry(func, delaied=True, is_strict=True)
            self.funcs.append(curried_func)
            if returnCurried:
                return curry(func)
        else:
            # 函数已经被柯里化，直接添加到列表中
            self.funcs.append(func)
            if returnCurried:
                return func
        return func
    
    def add(self,*funcs):
        for f in funcs:
            self.register(f,returnCurried=False)
        return self
    
    @property
    def size(self):
        return len(self.funcs)
    
    def __call__(self,*args,**kwargs):
        self._is_init = False
        cls = self.__class__
        
        def gen():
            for f in self.funcs:
                result = cls._try_bound(f,args,kwargs)
                if result is not None:
                    yield result
        rs = list(gen())
        
        l = len(rs)
        if l == 0:
            raise TypeError("No function can handle the arguments")
        
        # 处理只有一个结果的情况
        if l == 1:
            # 检查结果是否是 Curried 或 CurryDescriptor 对象
            if is_curried(rs[0]):
                # 检查是否已经有足够的参数（is_ready 为 True）
                is_ready = getattr(rs[0], 'is_ready', False)
                if is_ready:
                    # 如果已经有足够的参数，执行函数并返回结果
                    return rs[0]()
                else:
                    # 如果没有足够的参数，将结果包装在一个新的 cls 对象中返回
                    return cls(*rs)
            else:
                # 如果结果不是 Curried 或 CurryDescriptor 对象，直接返回结果
                return rs[0]
        
        # 否则，将结果包装在一个新的 cls 对象中返回
        return cls(*rs)
    
    def __getitem__(self,index):
        return self.funcs[index]
    
    def __len__(self):
        return len(self.funcs)
    
    def __iter__(self):
        return iter(self.funcs)
    
    def __repr__(self):
        return str(self)
    
    def __eq__(self,other):
        if not isinstance(other,Selector):
            return False
        return self.funcs == other.funcs
    
    def __hash__(self):
        return hash(tuple(self.funcs))
    
    def __add__(self,other):
        if not isinstance(other,Selector):
            return NotImplemented
        return self.__class__(*self.funcs,*other.funcs)
    
    def __radd__(self,other):
        if not isinstance(other,Selector):
            return NotImplemented
        return self.__class__(*other.funcs,*self.funcs)
    
    def __mul__(self,other):
        if not isinstance(other,int):
            return NotImplemented
        return self.__class__(*self.funcs*other)


    def toOverloads(self,delaied=False):
        return Overloads(*self.funcs,delaied=delaied)

# fs = Selector(lambda x : x+1,lambda x : x*2,lambda x ,y=2: x**2 + 2*y)
# print(fs(7).get_result(0,1))


class Overloads(Selector):

    def __init__(self, *funcs,delaied=False):
        
        super().__init__(*funcs)
        self.delaied = delaied
    def register(self, func=None, returnOverload=False):
        if func is None:
            return lambda f: self.register(f, returnOverload)
        cls = self.__class__
        result = super().register(func, returnCurried=returnOverload)
        if returnOverload:
            return cls(result)
        return result
    def __str__(self):
        return "Overloads(" + '\n==========================\n'.join(map(str,self.funcs)) + ")"
    
    def __call__(self, *args, **kwargs):
        cls = self.__class__
        if self.delaied:
            if any([args,kwargs]):
                result = super().__call__(*args, **kwargs)
                # 检查 result 是否是 Overloads 对象
                if isinstance(result, cls):
                    # print('-----------',len(result))
                    return cls(*result.funcs,delaied=True)
                else:
                    # 如果 result 不是 Overloads 对象，直接返回它
                    return result
            else:
                funcs = [f for f in self.funcs if hasattr(f, 'is_ready') and f.is_ready]
                if len(funcs) > 1:
                    raise TypeError("Multiple functions can handle the arguments")
                elif len(funcs) == 0:
                    # no one can handle the arguments
                    raise TypeError("No function can handle the arguments")
                return  funcs[0]()
        else:
            result = super().__call__(*args, **kwargs)
            # 检查 result 是否是 Overloads 对象
            if isinstance(result, cls):
                if len(result.funcs) >  1:
                    funcs = [f for f in result.funcs if hasattr(f, 'is_ready') and f.is_ready]
                    if len(funcs) > 1:
                        raise TypeError("Multiple functions can handle the arguments")
                    elif len(funcs) == 0:
                        # no one can handle the arguments
                        return cls(*result.funcs)
                    result = funcs[0]
                else:
                    result = result.funcs[0]
                
                if is_curried(result):
                    return result() if result.is_ready else result
                return result
            else:
                # 如果 result 不是 Overloads 对象，直接返回它
                return result

    def toSelector(self):
        return Selector(*self.funcs)
    
    

def overloads(*funcs,delaied=False):
    if not funcs:
        return lambda f: overloads(f,delaied=delaied)
    return Overloads(*funcs,delaied=delaied)


if __name__ == '__main__':
    @overloads
    def add(x,y):
        
        return x+y

    @add.register(returnOverload=1)
    def _x(x,y,z):
        return x+y+z

    @add.register
    def _y(x:int,y:int):
        return x*y

    @_x.register
    def _k(a,b,c,d):
        return a*b - c*d

    print(add(1,2,3))

    print(_x(1,2,3,4),_x(1,23.4,4),_x(1)(2)(3))

    _x.delaied = True
    t = _x(1,2,3)

    print(type(t),t.delaied,t(),t(4)(),'-------------------------------')
    
    x = _x.toSelector() * 3
    print(x(1,2,3,4).get_result())
