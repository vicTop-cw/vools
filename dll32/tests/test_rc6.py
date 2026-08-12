"""测试 RC6 COM 组件"""
print("=== 测试 DirectCOM 免注册加载 ===")

try:
    from vools.dll32._lib.com.directcom import DirectCOM

    # 创建 DirectCOM 实例
    dc = DirectCOM()
    print("DirectCOM 实例创建成功")

    # 免注册创建 vbRichClient5 对象
    constructor = dc.create_object("vbRichClient5.dll", "cConstructor")
    print("cConstructor 创建成功:", constructor)

    # 测试基本功能
    print("\n=== 测试 cConstructor 基本方法 ===")

    # 获取版本
    try:
        version = constructor.Version
        print(f"RC6 版本: {version}")
    except Exception as e:
        print(f"获取版本失败: {e}")

    # 测试系统检测
    try:
        is_win7 = constructor.IsWin7Plus()
        print(f"IsWin7Plus: {is_win7}")
    except Exception as e:
        print(f"系统检测失败: {e}")

    # 测试 CPU 核心数
    try:
        cores = constructor.GetCPUCoresCount()
        print(f"CPU 核心数: {cores}")
    except Exception as e:
        print(f"获取核心数失败: {e}")

    # 测试 cCrypt
    print("\n=== 测试 cCrypt ===")
    try:
        crypt = constructor.Crypt()
        print("cCrypt 创建成功")

        # Base64
        encoded = crypt.Base64Enc("Hello World")
        print(f"Base64 编码: 'Hello World' -> '{encoded}'")

        decoded = crypt.Base64Dec(encoded)
        print(f"Base64 解码: '{encoded}' -> '{decoded}'")

        # MD5
        md5_hash = crypt.MD5("test")
        print(f"MD5: 'test' -> '{md5_hash}'")

        # SHA256
        sha256_hash = crypt.SHA256("test")
        print(f"SHA256: 'test' -> '{sha256_hash}'")

    except Exception as e:
        print(f"cCrypt 测试失败: {e}")

    # 测试 cFSO
    print("\n=== 测试 cFSO ===")
    try:
        fso = constructor.FSO()
        print("cFSO 创建成功")

        # 获取特殊文件夹
        temp_path = fso.GetSpecialFolder(2)  # 2 = Windows Temp
        print(f"临时文件夹: {temp_path}")

    except Exception as e:
        print(f"cFSO 测试失败: {e}")

    print("\n=== RC6 DirectCOM 测试完成 ===")

except Exception as e:
    import traceback
    print(f"测试失败: {e}")
    traceback.print_exc()
