from typing import Any, Callable, Dict, List, Tuple, Union, Optional
import re
from functools import update_wrapper
from ..functional.arrow_func import g,_eval_expr_with_semicolon,arrow_func
__all__ = ['clone','g','arrow_func']




def clone(cls=None, *args, **kwargs):
    """
    快速clone一个类，可批量修改方法属性成员变量等
    :param cls: 被clone的类
    :param args: 传递给被clone的类的参数, 全部是 str 类型，表示要修改的成员变量 或属性变量 以 : 分割 或 => 分割
            如"name:张三" 表示修改 name 属性为 "张三"
            如"age:18" 表示修改 age 属性为 18
            如"full_name => '张' + self.name"  表示 full_name 属性为 "张" + self.name 属性值 带 =>  表示 需要执行eval表达式
            如"cls.count => cls.count + 1 " 表示执行 cls.count += 1 语句  带 =>  表示 需要执行eval表达式
            如"name => super().name.replace('张','李') "
            注意： args 必须是 str 类型，若要覆盖 原有属性请用 super().xxx = xxx 方式
                  只能是属性和变量，不能是方法
    :param kwargs: 传递给被clone的类的关键字参数
        env: dict 类型，表示环境变量，若有需要执行eval表达式，则需要提供环境变量，默认有 cls,self,super 三个变量, 若有需要用到其他变量，请在 env 中添加 
        reuslt_shell : 函数类型：签名 func(result,/,*,dir_filter=None) 
                        作用：对已有的方法返回结果进行处理，
                        result: 1、str表达式 必须是"=> " 开头，表示需要执行eval表达式，如"=> self.count + 1" 则会执行 return self.count = 1 语句 在当前方法作用域，env 中 有result,self,cls,super 等变量，可以直接表达使用
                                2、单参函数类型，表示对已有的方法返回结果进行处理，如 lambda result: "=> self" if result is None else result 
                        dir_filter ：1、 单参函数 是对 原有继承的方法 dir() 结果的过滤，默认不过滤,即筛选出需要的方法进行套壳处理
                                     2、 tuple<str> 或 list<str> 类型，表示要套壳的方法名，如 ('sort','append') 等 , 注意 若提供的 方法名 如：add 不存在 会忽略，不会创建新的方法
        
        reuslt_shell1 : 等同reuslt_shell ，批量处理 一批 方法。提供的 方法名是在 dir() 中 将 已经提供的 自定义 方法  和  reuslt_shell   套了壳的自定义方法 去掉后 的 filtered_dir1 结果； 提供 的dir_filter 函数    再对   filtered_dir1 过滤，只保留需要套壳的方法名
        reuslt_shell2 : 等同reuslt_shell ，批量处理 一批 方法。提供的 方法名是在 dir() 中 将 已经提供的 自定义 方法  和  reuslt_shell,result_shel1     套了壳的自定义方法 去掉后 的 filtered_dir2 结果； 提供 的dir_filter 函数    再对   filtered_dir2 过滤，只保留需要套壳的方法名
        reuslt_shell3 : 等同reuslt_shell ，批量处理 一批 方法。提供的 方法名是在 dir() 中 将 已经提供的 自定义 方法  和  reuslt_shell,result_shel1,result_shel2     套了壳的自定义方法 去掉后 的 filtered_dir3 结果； 提供 的dir_filter 函数    再对   filtered_dir3 过滤，只保留需要套壳的方法名
        ...
        -------------------
        copy_from : 从某个类 或类实例  方法中 扩展出单个方法，格式为： copy_from = (类或实例,方法名,init_args=None,init_kwargs=None,result_shell=None)  
                        如 copy_from = (list,'append',init_args="=> list(self.data)") 表示从 list 类中 扩展 append 方法
                            ,获取到了 result_shell 等同 关键字 result_shell 参数处理
        copy_from1 : 等同 copy_from
        copy_from2 : 等同 copy_from
        copy_from3 : 等同 copy_from
        ...
        -------------------
        copy_list_from ： 从某个类 或类实例  方法中 扩展出多个方法，
            格式为： copy_list_from = (类或实例,方法名列表或过滤dir 的单参函数 ,init_args=None,init_kwargs=None,result_shell=None,deco=None ) 
                            如 copy_list_from = (list,method_names_or_dir_filter,init_args="=> list(self.data)",return_result = "=> self") 
                                    表示从 list 类中 扩展 append 和 extend 方法，过滤掉 私有方法，获取到了 result_shell 等同 关键字 result_shell 参数处理
                                    ,deco 等同 关键字 deco 参数处理，表示对方法进行装饰器处理，如 @deco 等
        copy_list_from1 : 等同 copy_list_from
        copy_list_from2 : 等同 copy_list_from
        copy_list_from3 : 等同 copy_list_from
        ...
        -------------------
        其他关键字参数，表示要修改的自定义方法，格式为：
        1、字典类型，表示要添加的自定义方法，格式为：
        方法名 = {"args":(参数1,参数2), "kwargs":{参数名1:值1,参数名2:值2}, "return": 返回值,"deco":需要套壳的装饰器函数《必须是返回函数的函数类型》}  一定是个字典类型
                可以提供 args,kwargs,return,deco 任意多个，至少提供其中一个 除了 deco ，其他 均支持 "=> ???"  表达形成 的无参函数 ，其他类型 均是 变量本身 
        2、函数类型，第一个参数 必须是 self  该方式属于直接扩展 : 方法名 = func_xxx
        3、string类型 ，且必须是 形如  方法名 =  "x,y => x + y " ,其实 是  lambda self,x,y: x + y  形式的字符串，表示直接扩展方法，该方式属于直接扩展 : 方法名 = "x,y => x + y "
        
        
    :return: 继承后的新的类
    
    示例：
    
    @clone(None,"name:vicList","sep:-*-","tuple_value => self.join(self.sep)"
        ,join = {"args":("self.sep",), "kwargs":{}, "return": "self.sep.join(self)"}  # 自定义方法，需要添加到被clone的类中
        ,append = {"return": "self"} # 原来已有的方法，只提供"return" ,表示运行原来的方法后再返回结果
        ,sort = {"kwargs":{"reverse":True}, "return": "self"}  # 原来已有的方法，只提供"args" 和 "kwargs" ,表示固定参数和关键字参数，注意参数个数 会减掉，若必参全部填充，则变成无参方法
        ,result_shell = (lambda result: "=> self" if result is None else result ,dir_filter=lambda x:x.startswith('__') == False ) # 对已有的方法返回结果进行处理，这里将返回值全部大写 已经 排掉了 append 和 sort 方法的 dir() 结果,因为已经提供了自定义方法 append 和 sort 了
        )
    class vList(list):
        pass
    
    """
    def wrapper(target_cls):
        # 基础环境变量
        base_env = {
            'cls': target_cls,
            'super': super,
        }
        # 合并用户提供的环境变量
        env = kwargs.pop('env', {})
        base_env.update(env)
        
        # 创建新类
        class_name = f"Cloned{target_cls.__name__}"
        new_cls = type(class_name, (target_cls,), {})
        setattr(new_cls, 'env', env)
        
        # 处理位置参数（属性修改）
        for arg in args:
            _process_args((arg,), new_cls, base_env)
        
        # 分类处理关键字参数
        custom_methods = {}
        shell_configs = {}
        copy_from_configs = {}
        copy_list_from_configs = {}
        
        for key, value in kwargs.items():
            if key.startswith('result_shell'):
                shell_configs[key] = value
            elif key.startswith('copy_from'):
                copy_from_configs[key] = value
            elif key.startswith('copy_list_from'):
                copy_list_from_configs[key] = value
            else:
                custom_methods[key] = value
        
        # 处理copy_from配置
        _process_copy_from(copy_from_configs, new_cls, base_env)
        
        # 处理copy_list_from配置
        _process_copy_list_from(copy_list_from_configs, new_cls, base_env)
        
        # 添加自定义方法
        _add_custom_methods(custom_methods, new_cls, base_env)
        
        # 批量处理方法套壳
        _process_result_shells(shell_configs, new_cls, base_env, custom_methods.keys())
        
        return new_cls
    
    if cls is None:
        return wrapper
    return wrapper(cls)

def _process_args(args: Tuple[str], new_cls: type, env: Dict, deco: Callable = property):
    """处理位置参数，设置属性"""
    for arg in args:
        if not isinstance(arg, str):
            continue
        
        tp = None
        # 判断分隔符类型
        if '=>' in arg:
            parts = arg.split('=>', 1)
            attr_name = parts[0].strip()
            if ':' in attr_name:
                attr_name, tp = attr_name.split(':', 1)
                try:
                    tp = eval(tp.strip())
                    tp = tp if isinstance(tp, type) else None
                except Exception as e:
                    print(f"Warning: Failed to evaluate type for attribute '{attr_name}': {tp} ,error: {e}")
                    tp = None
            expr = parts[1].strip()
            # print(f'{attr_name}=>{expr}')
            is_expr = True
        elif ':' in arg:
            parts = arg.split(':', 1)
            attr_name = parts[0].strip()
            expr = parts[1].strip()
            is_expr = False
        else:
            continue
            
        # 设置属性
        if is_expr:
            # 执行表达式（支持分号）
            def attr_proxy(self):
                local_env = env.copy()
                local_env.update({
                    'self': self,
                    'cls': type(self),
                    'super': super(type(self), self),
                })
                temp = _eval_expr_with_semicolon(expr, local_env)
                if tp and not isinstance(temp, tp):
                    temp = tp(temp)
                return temp
            try:
                setattr(new_cls, attr_name, deco(attr_proxy))
            except TypeError: 
                try:
                    setattr(new_cls, attr_name, attr_proxy)
                except Exception as e:
                    print(f"Warning: Failed to set attribute '{attr_name}': {e}")
            except Exception as e:
                print(f"Warning: Failed to evaluate expression '{expr}' for attribute '{attr_name}': {e}")
        else:
            # 直接设置值（尝试自动转换类型）
            setattr(new_cls, attr_name, _auto_convert_type(expr))

def _auto_convert_type(value_str: str) -> Any:
    """自动转换字符串类型"""
    # 尝试转换为int
    if value_str.isdigit():
        return int(value_str)
    if value_str.count('.') == 1 and value_str.replace('.', '').isdigit():
        return float(value_str)
    
    if value_str.startswith('0x') and value_str[2:].isdigit():
        return int(value_str, 16)
    if value_str.startswith('0b') and value_str[2:].isdigit():
        return int(value_str, 2)
    if value_str.startswith('0o') and value_str[2:].isdigit():
        return int(value_str, 8)
    # 尝试转换为bool
    if value_str.lower() in ('true', 'false'):
        return value_str.lower() == 'true'
    
    # 移除字符串可能的引号
    quotes = ('"""', "'''", '"', "'", "`")
    lst = [i for i, q in enumerate(quotes) if value_str.startswith(q) and value_str.endswith(q)]
    if lst:
        i = lst[0]
        i = 3 if i <= 1 else 1
        return value_str[i:-i] 
    if value_str.startswith('[') and value_str.endswith(']'):
        return [_auto_convert_type(v.strip()) for v in value_str[1:-1].split(',')]
            
    if value_str.startswith('{') and value_str.endswith('}'):
        try:
            return {_auto_convert_type(k.strip()): _auto_convert_type(v.strip()) 
                   for k, v in [item.split(':') for item in value_str[1:-1].split(',')]}
        except:
            pass
    if value_str.startswith('(') and value_str.endswith(')'):
        values_str = value_str[1:-1].split(',')
        if len(values_str) == 1:
            return _auto_convert_type(values_str[0].strip())
        else:
            return tuple(_auto_convert_type(v.strip()) for v in values_str)
    return value_str

def _process_copy_from(copy_from_configs: Dict[str, Any], new_cls: type, env: Dict):
    """处理copy_from配置，从其他类或实例复制方法"""
    # 按顺序处理copy_from配置
    copy_keys = sorted(copy_from_configs.keys(), 
                      key=lambda x: int(x[9:]) if x[9:].isdigit() else (0 if x == 'copy_from' else 999))
    
    for copy_key in copy_keys:
        config = copy_from_configs[copy_key]
        
        if not isinstance(config, (tuple, list,dict)) or len(config) < 2:
            continue
        if isinstance(config, dict):
            source = config['source',None]
            method_name = config['method',None]
            init_args = config.get('init_args',None) #must be a list
            init_kwargs = config.get('init_kwargs',None) #must be a dict
            return_result = config.get('return_result',{})
        else:    
            source, method_name = config[0], config[1]
            init_args = config[2] if len(config) > 2 else None
            init_kwargs = config[3] if len(config) > 3 else None
            return_result = config[4] if len(config) > 4 else {}
        if source is None or method_name is None:
            continue
        
        # 校验参数
        if not isinstance(method_name, str): # 必须是字符串
            raise ValueError(f"Invalid method_name for {copy_key}: {method_name}")
        if not isinstance(source, (type, object)): # 必须是类或实例
            raise ValueError(f"Invalid source for {copy_key}: {source}")
        if not isinstance(init_args, (str, list, tuple, type(None))): # 必须是字符串或列表或元组或None
            raise ValueError(f"Invalid init_args for {copy_key}: {init_args}")
        if not isinstance(init_kwargs, (str, dict, type(None))): # 必须是字符串或字典或None
            raise ValueError(f"Invalid init_kwargs for {copy_key}: {init_kwargs}")
       
        # 创建源实例（如果需要）
        if isinstance(source, type):
            # 是类，需要实例化
            if init_args is not None or init_kwargs is not None:
                # 处理初始化参数
                local_env = env.copy()
                local_env.update({'cls': new_cls})
                
                args_val = ()
                if init_args is not None:
                    if isinstance(init_args, str) and init_args.startswith('=>'):
                        try:
                            args_val = _eval_expr_with_semicolon(init_args[2:].strip(), local_env)
                        except Exception as e:
                            print(f"Warning: Failed to evaluate init_args for {method_name}: {e}")
                    else:
                        args_val = init_args
                
                kwargs_val = {}
                if init_kwargs is not None:
                    if isinstance(init_kwargs, str) and init_kwargs.startswith('=>'):
                        try:
                            kwargs_val = _eval_expr_with_semicolon(init_kwargs[2:].strip(), local_env)
                        except Exception as e:
                            print(f"Warning: Failed to evaluate init_kwargs for {method_name}: {e}")
                    else:
                        kwargs_val = init_kwargs
                
                source_instance = source(*args_val) if isinstance(args_val, tuple) else source(args_val)
                if kwargs_val:
                    for k, v in kwargs_val.items():
                        setattr(source_instance, k, v)
            else:
                source_instance = source()
        else:
            # 已经是实例
            source_instance = source
        
        # 获取方法
        if hasattr(source_instance, method_name):
            original_method = getattr(source_instance, method_name)
            
            # 创建包装方法
            def create_copied_method(orig_method, name, return_result=None):
                def copied_method(self, *args, **kwargs):
                    # 调用原始方法
                    result = orig_method(*args, **kwargs)
                    
                    # 处理返回值
                    if return_result is not None:
                        local_env = env.copy()
                        local_env.update({
                            'self': self,
                            'cls': type(self),
                            'super': super(type(self), self),
                            'args': args,
                            'kwargs': kwargs,
                            'result': result
                        })
                        
                        if isinstance(return_result, str):
                            if return_result.startswith('=>'):
                                try:
                                    result = _eval_expr_with_semicolon(return_result[2:].strip(), local_env)
                                except Exception as e:
                                    print(f"Warning: Failed to evaluate return_result for {name}: {e}")
                            else:
                                result = return_result
                        elif callable(return_result):
                            result = return_result(result)
                    
                    return result
                
                copied_method.__name__ = name
                return copied_method
            
            copied_method = create_copied_method(original_method, method_name, return_result)
            
            # 设置方法
            setattr(new_cls, method_name, copied_method)

def _process_copy_list_from(copy_list_from_configs: Dict[str, Any], new_cls: type, env: Dict):
    """处理copy_list_from配置，从其他类或实例复制多个方法"""
    # 按顺序处理copy_list_from配置
    copy_keys = sorted(copy_list_from_configs.keys(), 
                      key=lambda x: int(x[14:]) if x[14:].isdigit() else (0 if x == 'copy_list_from' else 999))
    
    for copy_key in copy_keys:
        config = copy_list_from_configs[copy_key]
        
        if not isinstance(config, (tuple, list,dict)) or len(config) < 2:
            continue
        if isinstance(config, dict):
            source = config['source']
            method_names = config["methods"]
            if not isinstance(method_names, (list, tuple)) and method_names is not None:
                if isinstance(method_names, str):
                    if "," in method_names:
                        method_names = [m.strip() for m in method_names.split(",")]
                    else:
                        method_names = [method_names.strip()]
                raise ValueError(f"Invalid method_names for {copy_key}: {method_names}")
            dir_filter = config.get('dir_filter',lambda x:True)
            init_args = config.get('init_args',None) #must be a list
            init_kwargs = config.get('init_kwargs',None) #must be a dict
            return_result = config.get('return_result',{})
            deco = config.get('deco',None)
        else:    
            source, method_names_or_dir_filter = config[0], config[1]
            init_args = config[2] if len(config) > 2 else None
            init_kwargs = config[3] if len(config) > 3 else None
            return_result = config[4] if len(config) > 4 else {}
            deco = config[5] if len(config) > 5 else None
            if callable(method_names_or_dir_filter):
                dir_filter = method_names_or_dir_filter
                method_names = None
            elif isinstance(method_names_or_dir_filter, (list, tuple)):
                dir_filter = None
                method_names = method_names_or_dir_filter
            elif isinstance(method_names_or_dir_filter, str):
                if "=>" in method_names_or_dir_filter:
                    dir_filter = arrow_func(method_names_or_dir_filter)
                    method_names = None
                elif "," in method_names_or_dir_filter :
                    method_names = [m.strip() for m in method_names_or_dir_filter.split(",")]
                    dir_filter = None
                else:
                    method_names = [method_names_or_dir_filter.strip()]
                    dir_filter = None
            else:
                dir_filter = None
                method_names = method_names_or_dir_filter
        if deco and not callable(deco):
            print("Warning: Invalid deco for {copy_key}: {deco}, ignored.  deco must be a callable<func(...)->func>.")
            deco = None
        # 获取所有方法名
        all_methods = [method for method in dir(source) 
                        if callable(getattr(source, method)) and not method.startswith('_')]        
        # 应用目录过滤器
        if dir_filter is not None:
            all_methods = [method for method in all_methods if dir_filter(method)]
        # 如果method_names是字符串，尝试从源获取所有方法
        
        if method_names is None:
            method_names = all_methods
        elif isinstance(method_names, (list, tuple)):
            method_names = [m for m in method_names if m in all_methods]
        elif isinstance(method_names, str):
            if "," in method_names:
                method_names = [m.strip() for m in method_names.split(",")]
            else:
                method_names = [method_names.strip()]
            method_names = [m for m in method_names if m in all_methods]
        else:
            raise ValueError(f"Invalid method_names for {copy_key}: {method_names}")
        
        if not method_names:
            continue # 没有可用的方法名，跳过
        
        
        
        
        
        
        # 复制每个方法
        for method_name in method_names:
            
            orig_method = None
            def copied_method(self, *args, **kwargs):
                # 调用原始方法
                # 创建源实例（如果需要）
                nonlocal orig_method
                if isinstance(source, type):
                    # 是类，需要实例化
                    local_env = env.copy()
                    local_env.update({'cls': new_cls,"self":self,"super":super(type(self), self)})
                    if init_args is not None or init_kwargs is not None:
                        # 处理初始化参数
                        args_val = ()
                        def _convert_args(x):
                            if isinstance(x, str) :  # 必须生成无参函数 
                                try:
                                    if (x.startswith('=>') or x.startswith('self') or x.startswith('cls') 
                                        or x.startswith('lambda ') or x.startswith('def ') or x.startswith('class ')
                                        or x.startswith('super') or re.match(r'(?<!\w)_(?!\w)',x)
                                        or x.match(r'(?<!\w)_(0*[1-9]\d*)(?!\w)',x)
                                        ):
                                        return g(x, local_env)
                                    else:
                                        return x
                                except Exception as e:
                                    print(f"Warning: Failed to evaluate init_args: {e}")
                                    return None
                            if isinstance(x, (list, tuple)):
                                return [_convert_args(i) for i in x]
                            if isinstance(x, dict):
                                return {str(k):_convert_args(v) for k,v in x.items()} # 字典的key必须是字符串
                            return x
                        if init_args is not None:
                            args_val = _convert_args(init_args)
                            if not isinstance(args_val, (list, tuple)):
                                args_val = ()
                        
                        kwargs_val = {}
                        if init_kwargs is not None:
                            kwargs_val = _convert_args(init_kwargs)
                            if not isinstance(kwargs_val, dict):
                                kwargs_val = {}
                        
                        if args_val and kwargs_val:
                            source_instance = source(*args_val, **kwargs_val)
                        elif args_val:
                            source_instance = source(*args_val)
                        elif kwargs_val:
                            source_instance = source(**kwargs_val)
                        else:
                            source_instance = source()
                    else:
                        source_instance = source()
                elif callable(source) and not isinstance(source, object):
                    #是函数，不是实例，直接调用
                    # func_name = source.__name__ if hasattr(source, '__name__') else source.__qualname__ if hasattr(source, '__qualname__') else '_invalid_method_name'
                    rs = source(*args, **kwargs)
                    source_instance = None
                else:
                    # 已经是实例
                    source_instance = source
                if source_instance :
                    orig_method =   getattr(source_instance, method_name)  
                    rs = orig_method(*args, **kwargs)
                else:
                    orig_method = source
                # 处理返回值
                if return_result is not None:
                    # local_env = env.copy()
                    env.update({
                        'self': self,
                        'cls': type(self),
                        'super': super(type(self), self),
                        'args': args,
                        'kwargs': kwargs,
                        'result': rs
                    })
                    
                    if isinstance(return_result, str):
                        if return_result.startswith('=>'):
                            try:
                                rs = _eval_expr_with_semicolon(return_result[2:].strip(), env)
                            except Exception as e:
                                print(f"Warning: Failed to evaluate return_result for {method_name}: {e}")
                        else:
                            rs = return_result
                    elif callable(return_result):
                        rs = return_result(rs)
                
                return rs
            copied_method.__name__ = method_name
            update_wrapper(copied_method, orig_method)
            if deco:
                copied_method = deco(copied_method)
                # 设置方法
            setattr(new_cls, method_name, copied_method)

def _add_custom_methods(custom_methods: Dict[str, Any], new_cls: type, env: Dict):
    """添加自定义方法，支持三种类型：字典、函数、字符串"""
    for method_name, config in custom_methods.items():
        # 1. 字典类型：原有逻辑
        if isinstance(config, dict):
            _add_dict_method(method_name, config, new_cls, env)
        
        # 2. 函数类型：直接添加
        elif callable(config):
            # 检查是否是绑定方法（第一个参数是self）
            import inspect
            sig = inspect.signature(config)
            params = list(sig.parameters.values())
            if params and params[0].name == 'self':
                setattr(new_cls, method_name, config)
            else:
                # 包装成实例方法
                def create_method(func, name):
                    def method(self, *args, **kwargs):
                        return func(*args, **kwargs)
                    method.__name__ = name
                    return method
                
                setattr(new_cls, method_name, create_method(config, method_name))
        
        # 3. 字符串类型：lambda表达式
        elif isinstance(config, str):
            _add_string_method(method_name, config, new_cls, env)

def _add_dict_method(method_name: str, config: Dict, new_cls: type, env: Dict):
    """添加字典类型的自定义方法"""
    # 获取原始方法（如果存在）
    original_method = getattr(new_cls, method_name, None) if hasattr(new_cls, method_name) else None
    
    def create_wrapped_method(orig_method, conf, name):
        def wrapped_method(self, *args, **kwargs):
            # 准备执行环境
            local_env = env.copy()
            local_env.update({
                'self': self,
                'cls': type(self),
                'super': super(type(self), self),
                'args': args,
                'kwargs': kwargs,
                'result': None
            })
            
            # 处理固定参数
            call_args = args
            call_kwargs = kwargs.copy()
            
            if 'args' in conf:
                fixed_args = conf['args']
                if isinstance(fixed_args, str) and fixed_args.startswith('=>'):
                    # 执行表达式获取参数
                    try:
                        fixed_args = _eval_expr_with_semicolon(fixed_args[2:].strip(), local_env)
                    except Exception as e:
                        print(f"Warning: Failed to evaluate args expression for {name}: {e}")
                call_args = fixed_args
            
            if 'kwargs' in conf:
                fixed_kwargs = conf['kwargs']
                if isinstance(fixed_kwargs, str) and fixed_kwargs.startswith('=>'):
                    try:
                        fixed_kwargs = _eval_expr_with_semicolon(fixed_kwargs[2:].strip(), local_env)
                    except Exception as e:
                        print(f"Warning: Failed to evaluate kwargs expression for {name}: {e}")
                call_kwargs.update(fixed_kwargs)
            
            # 调用原始方法
            if orig_method:
                local_env['result'] = orig_method(self, *call_args, **call_kwargs)
            else:
                local_env['result'] = None
            
            # 处理返回值
            return_value = local_env['result']
            if 'return' in conf:
                return_conf = conf['return']
                if isinstance(return_conf, str):
                    if return_conf.startswith('=>'):
                        # 执行表达式
                        try:
                            return_value = _eval_expr_with_semicolon(return_conf[2:].strip(), local_env)
                        except Exception as e:
                            print(f"Warning: Failed to evaluate return expression for {name}: {e}")
                    else:
                        return_value = return_conf
            
            return return_value
        
        return wrapped_method
    
    # 创建新方法
    new_method = create_wrapped_method(original_method, config, method_name)
    
    # 应用装饰器
    if 'deco' in config and callable(config['deco']):
        new_method = config['deco'](new_method)
    
    # 设置方法
    setattr(new_cls, method_name, new_method)

def _add_string_method(method_name: str, config: str, new_cls: type, env: Dict):
    """添加字符串类型的自定义方法（lambda表达式）"""
    if not "=>" in config:
        def _creat_holder_func(self,*args,**kwargs ):
            f = g(config,env={"self":self,"cls":type(self),"super":super(type(self),self)})
            return f(*args,**kwargs)
            
        setattr(new_cls,method_name,_creat_holder_func)    
        return
    # 解析字符串：格式为 "x,y => x + y"
    parts = config.split('=>', 1)
    if len(parts) != 2:
        return
    
    params_str = parts[0].strip()
    expr = parts[1].strip()
    
    # 解析参数
    param_names = [p.strip() for p in params_str.split(',')]
    
    # 创建lambda函数（支持分号）
    def create_lambda_method(param_names, expr, name):
        def lambda_method(self, *args, **kwargs):
            # 准备执行环境
            local_env = env.copy()
            local_env.update({
                'self': self,
                'cls': type(self),
                'super': super(type(self), self),
            })
            
            # 绑定参数
            for i, param in enumerate(param_names):
                if param != 'self' and i < len(args):
                    local_env[param] = args[i]
            
            local_env.update(kwargs)
            
            # 执行表达式（支持分号）
            try:
                return _eval_expr_with_semicolon(expr, local_env)
            except Exception as e:
                print(f"Warning: Failed to evaluate lambda expression for {name}: {e}")
                return None
        
        lambda_method.__name__ = name
        return lambda_method
    
    lambda_method = create_lambda_method(param_names, expr, method_name)
    setattr(new_cls, method_name, lambda_method)

def _process_result_shells(shell_configs: Dict[str, Any], new_cls: type, env: Dict, custom_method_names: set):
    """批量处理方法套壳"""
    # 按顺序处理result_shell配置
    shell_keys = sorted(shell_configs.keys(), 
                       key=lambda x: int(x[12:]) if x[12:].isdigit() else (0 if x == 'result_shell' else 999))
    
    processed_methods = set(custom_method_names)
    
    for shell_key in shell_keys:
        config = shell_configs[shell_key]
        
        if isinstance(config, (tuple, list)) and len(config) == 2:
            shell_func, dir_filter = config
        elif callable(config):
            shell_func = config
            dir_filter = None
        else:
            continue
        
        # 获取当前可处理的方法列表
        all_methods = set(dir(new_cls))
        available_methods = all_methods - processed_methods
        
        # 应用目录过滤器
        if dir_filter is not None:
            if callable(dir_filter):
                available_methods = {m for m in available_methods if dir_filter(m)}
            elif isinstance(dir_filter, (list, tuple)):
                available_methods = available_methods.intersection(set(dir_filter))
        
        # 对每个方法应用套壳
        for method_name in available_methods:
            # 跳过特殊方法（可选，根据需求调整）
            if method_name.startswith('__') and method_name.endswith('__'):
                continue
                
            original_method = getattr(new_cls, method_name)
            if not callable(original_method):
                continue
                
            def create_shelled_method(orig_method, name, shell_func):
                def shelled_method(self, *args, **kwargs):
                    # 准备环境
                    local_env = env.copy()
                    local_env.update({
                        'self': self,
                        'cls': type(self),
                        'super': super(type(self), self),
                        'args': args,
                        'kwargs': kwargs
                    })
                    
                    # 调用原始方法
                    original_result = orig_method(self, *args, **kwargs)
                    local_env['result'] = original_result
                    
                    # 应用shell函数
                    if callable(shell_func):
                        try:
                            # 如果shell_func接受dir_filter参数
                            import inspect
                            sig = inspect.signature(shell_func)
                            if 'dir_filter' in sig.parameters:
                                new_result = shell_func(original_result, dir_filter=dir_filter)
                            else:
                                new_result = shell_func(original_result)
                        except Exception as e:
                            print(f"Warning: Shell function failed for {name}: {e}")
                            new_result = original_result
                    else:
                        new_result = original_result
                    
                    # 处理返回值为表达式的情况（支持分号）
                    if isinstance(new_result, str) and new_result.startswith('=>'):
                        try:
                            new_result = _eval_expr_with_semicolon(new_result[2:].strip(), local_env)
                        except Exception as e:
                            print(f"Warning: Failed to evaluate shell result expression for {name}: {e}")
                    
                    return new_result
                
                return shelled_method
            
            # 替换方法
            shelled_method = create_shelled_method(original_method, method_name, shell_func)
            setattr(new_cls, method_name, shelled_method)
            processed_methods.add(method_name)

# 示例使用
if __name__ == "__main__":
    # 测试copy_from功能
    class MathUtils:
        def add(self, a, b):
            return a + b
        
        def multiply(self, a, b):
            return a * b
    
    class A:
        def __init__(self,x,y,*args, **kwargs):
            self.name = x
            self.version = y
            self.data = args
            self.config = kwargs
        def get_info(self):
            return f"{self.name} v{self.version}"
        
        def show(self, sep):
            print(sep.join(map(str, self.data)))
            
        def update_version(self, a, b):

            return a * b
    
    # 测试字符串类型的方法
    def custom_print(self, message):
        print(f"Custom: {message}")
        return self
    
    # 综合测试（包含分号表达式）
    @clone(None,
           "name:TestClass",
           "version:1.0",
           # 测试分号表达式：多个语句，返回最后一个
           "description => self.name + ' v' + str(self.version); 'Description: ' + self.name",
           # 测试以分号结尾：返回None
           "none_attr => self.name;",
           # 字典类型方法
           "get_info => f'{self.name} v{self.version}'",
           # 函数类型方法
           custom_print=custom_print,
           append = (lambda self, x: self.data.append(x)),
           
           # 测试分号在lambda表达式中
           __add__ = " other => self.data.extend(list(other) if isinstance(other, (list, tuple)) else [other]); self",
           
           __mul__ = " other => temp = self.data * other if isinstance(other, int) else self.data * len(other); temp",

           show = " x = _.join(map(str, self.data)) ; print(x);",
           
           
           # 字符串类型方法（带分号）
           add_numbers="a,b => x = a + b; y = x + self.version; y",
           # copy_from功能（带分号）
           copy_from=(MathUtils, 'multiply', None, None,  '=>  result *= 2; result + 10'),
           
        #    copy_from1 = (A, 'update_version',("=> self.name","=> self.version"),{"header":"true","sep":","},"=> print(f'update_version result: {result}');self"),
           # copy_list_from功能（带分号）
           copy_list_from=(MathUtils, ['add'], lambda x: True, None, None,  '=> temp = result + 10; temp * 2'),
           copy_list_from1=(A, None, ("vic"," => 1.0","=> self.data"),None, '=> print(f"result: {result}");self'),
           # result_shell功能（带分号）
           result_shell=(lambda result: f">>>{result}<<<" if result is not None else ">>>None<<<", 
                        lambda x: x.startswith('get_'))
    )
    class TestClass:
        def __init__(self):
            self.data = []
        
        def get_data(self):
            return self.data
    
    # 测试
    obj = TestClass()
    print("Description:", obj.description)  # Description: TestClass v1.0 -> 'Description: TestClass'
    print("Info:", obj.get_info)
    print(f"Name:{obj.name}")
    print(f"Version:{obj.version}")
    print("None attr:", obj.none_attr)  # None
    
    result = obj.add_numbers(5, 3)
    print("Add numbers:", result)  # 5 + 3 + 1.0 = 9.0
    
    result = obj.multiply(4, 5)
    print("Multiply:", result)  # 4 * 5 * 2 = 40 -> 40 + 10 = 50
    
    result = obj.add(2, 3)
    print("Add:", result)  # 2 + 3 + 10 = 15 -> 15 * 2 = 30
    
    obj.custom_print("Hello World")  # Custom: Hello World
    
    print("Get data:", obj.get_data())  # >>>[]<<< (被result_shell处理过)

    obj.append(1)
    print("After append:", obj.get_data())  # >>>[1]<<< (被result_shell处理过)
    
    obj2 = obj + [2, 3]  # 使用__add__，返回self
    print("After add:", obj2.get_data())  # [1, 2, 3]
    
    result = obj * 3
    print("Multiply list:", result)  # [1, 2, 3, 1, 2, 3, 1, 2, 3]
    
    obj.show(',')

    obj.show("|")
    print(dir(obj))
    obj.update_version(5, 3)


# 测试代码
if __name__ == "__main__":
    # 测试分号支持
    f6 = g('x = _1 + _2; y = x * 2; y')
    print(f6(3, 4))  # 应该输出 14
    
    f7 = g('a = _; b = a * 2; b + 1')
    print(f7(5))  # 应该输出 11
    
    # 测试以分号结尾的情况
    f8 = g('x = _1 + _2;')
    result = f8(3, 4)
    print(f"Result: {result}")  # 应该输出 None
    
    # 使用自定义环境变量
    custom_env = {'multiplier': 3, 'adder': 5}
    f9 = g('_1 * multiplier + adder', env=custom_env)
    print(f9(5))  # 应该输出 20 (5 * 3+5)
    
    # 原来的功能仍然正常工作
    f1 = g('_ + 2 * _')
    print(f1(3, 4))  # 11

    k = g('x = _1 + _2; y = x * 2; y')
    print(k(3, 4))

    k = g("x,y => x += y ; x * 2")
    print(k(3, 4))

    lst = [1,2,3]

    k = g("v => x.append(v);",{'x':lst})
    print(k(2),lst)