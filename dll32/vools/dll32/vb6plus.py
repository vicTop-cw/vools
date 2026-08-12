"""
VB6Plus.dll 包装模块

提供便捷的 VB6Plus.dll 函数调用。
"""
from .dll import dll32


class VB6Plus:
    """VB6Plus DLL 函数集合"""

    # ===== Base64 编解码 =====
    @dll32('VB6Plus.dll::Base64Encode_GB')
    def base64_encode_gb(self, input_str: str) -> str:
        """Base64 编码 (GB 编码)"""
        pass

    @dll32('VB6Plus.dll::Base64Decode_GB')
    def base64_decode_gb(self, input_str: str) -> str:
        """Base64 解码 (GB 编码)"""
        pass

    @dll32('VB6Plus.dll::Base64Encode_UTF8')
    def base64_encode_utf8(self, input_str: str) -> str:
        """Base64 编码 (UTF-8 编码)"""
        pass

    @dll32('VB6Plus.dll::Base64Decode_UTF8')
    def base64_decode_utf8(self, input_str: str) -> str:
        """Base64 解码 (UTF-8 编码)"""
        pass

    # ===== MD5 哈希 =====
    @dll32('VB6Plus.dll::MD516_GB')
    def md5_16_gb(self, input_str: str) -> str:
        """MD5 16位 (GB 编码)"""
        pass

    @dll32('VB6Plus.dll::MD532_GB')
    def md5_32_gb(self, input_str: str) -> str:
        """MD5 32位 (GB 编码)"""
        pass

    @dll32('VB6Plus.dll::MD516_UTF8')
    def md5_16_utf8(self, input_str: str) -> str:
        """MD5 16位 (UTF-8 编码)"""
        pass

    @dll32('VB6Plus.dll::MD532_UTF8')
    def md5_32_utf8(self, input_str: str) -> str:
        """MD5 32位 (UTF-8 编码)"""
        pass

    # ===== HTML 编解码 =====
    @dll32('VB6Plus.dll::NoHTML')
    def no_html(self, input_str: str, no_html_more: int = 0) -> str:
        """去除 HTML 标签

        Args:
            input_str: 输入字符串
            no_html_more: 更多选项 (位标志)
                0 - 无
                1 - 去除 Style 代码
                2 - 去除 JS 代码
                4 - HTML 解码
                8 - 去除多余空格、换行等
                15 - 全部 (不支持累加)
        """
        pass

    @dll32('VB6Plus.dll::HTMLEncode')
    def html_encode(self, input_str: str) -> str:
        """HTML 编码"""
        pass

    @dll32('VB6Plus.dll::HTMLDecode')
    def html_decode(self, input_str: str) -> str:
        """HTML 解码"""
        pass

    # ===== URL 编解码 =====
    @dll32('VB6Plus.dll::UrlEncode_GB')
    def url_encode_gb(self, input_str: str) -> str:
        """URL 编码 (GB 编码)"""
        pass

    @dll32('VB6Plus.dll::UrlDecode_GB')
    def url_decode_gb(self, input_str: str) -> str:
        """URL 解码 (GB 编码)"""
        pass

    @dll32('VB6Plus.dll::UrlEncode_UTF8')
    def url_encode_utf8(self, input_str: str) -> str:
        """URL 编码 (UTF-8 编码)"""
        pass

    @dll32('VB6Plus.dll::UrlDecode_UTF8')
    def url_decode_utf8(self, input_str: str) -> str:
        """URL 解码 (UTF-8 编码)"""
        pass

    # ===== Unicode 编解码 =====
    @dll32('VB6Plus.dll::UnicodeEncode')
    def unicode_encode(self, input_str: str) -> str:
        """Unicode 编码 (\\uXXXX 格式)"""
        pass

    @dll32('VB6Plus.dll::UnicodeDecode')
    def unicode_decode(self, input_str: str) -> str:
        """Unicode 解码"""
        pass

    # ===== Hex 编解码 =====
    @dll32('VB6Plus.dll::StrToHex_GB')
    def str_to_hex_gb(self, input_str: str, is_upper: int = 1) -> str:
        """字符串转十六进制 (GB 编码)

        Args:
            input_str: 输入字符串
            is_upper: 0-小写, 1-大写 (默认1)
        """
        pass

    @dll32('VB6Plus.dll::StrToHex_UTF8')
    def str_to_hex_utf8(self, input_str: str, is_upper: int = 1) -> str:
        """字符串转十六进制 (UTF-8 编码)

        Args:
            input_str: 输入字符串
            is_upper: 0-小写, 1-大写 (默认1)
        """
        pass

    @dll32('VB6Plus.dll::HexToStr_GB')
    def hex_to_str_gb(self, input_str: str) -> str:
        """十六进制转字符串 (GB 编码)"""
        pass

    @dll32('VB6Plus.dll::HexToStr_UTF8')
    def hex_to_str_utf8(self, input_str: str) -> str:
        """十六进制转字符串 (UTF-8 编码)"""
        pass

    # ===== 字符串操作 =====
    @dll32('VB6Plus.dll::StrCompare')
    def str_compare(self, str_a: str, str_b: str) -> float:
        """字符串相似度比较

        Returns:
            相似度 (0-1)
        """
        pass

    @dll32('VB6Plus.dll::Permutation')
    def permutation(self, input_str: str, separator: str = ',', result_total: int = 0) -> str:
        """字符串全排列

        Args:
            input_str: 输入字符串 (最多10个字符)
            separator: 分隔符
            result_total: 结果数量限制 (0-不限制)
        """
        pass

    @dll32('VB6Plus.dll::Combination')
    def combination(self, input_str: str, separator: str = ',', result_total: int = 0) -> str:
        """字符串组合

        Args:
            input_str: 输入字符串 (最多23个字符)
            separator: 分隔符
            result_total: 结果数量限制 (0-不限制)
        """
        pass

    @dll32('VB6Plus.dll::ExplodeData')
    def explode_data(self, input_str: str, start_str: str, end_str: str) -> str:
        """字符串分割提取

        从输入字符串中提取 start_str 和 end_str 之间的内容。

        Args:
            input_str: 输入字符串
            start_str: 起始标记
            end_str: 结束标记

        Returns:
            提取的内容
        """
        pass

    @dll32('VB6Plus.dll::Regex_Replace')
    def regex_replace(self, input_str: str, pattern: str, replacement: str) -> str:
        """正则表达式替换

        Args:
            input_str: 输入字符串
            pattern: 正则表达式模式
            replacement: 替换文本

        Returns:
            替换后的字符串
        """
        pass

    # ===== INI 文件操作 =====
    @dll32('VB6Plus.dll::ReadINIValue')
    def read_ini_value(self, section_name: str, key_name: str,
                       default_value: str = '', ini_file: str = 'Config.ini') -> str:
        """读取 INI 文件值

        Args:
            section_name: 节名
            key_name: 键名
            default_value: 默认值
            ini_file: INI 文件路径
        """
        pass

    @dll32('VB6Plus.dll::WriteINIValue')
    def write_ini_value(self, section_name: str, key_name: str,
                        value: str, ini_file: str = 'Config.ini') -> bool:
        """写入 INI 文件值

        Returns:
            True-成功, False-失败
        """
        pass

    # ===== AES 加密 =====
    @dll32('VB6Plus.dll::AESEncrypt_GB')
    def aes_encrypt_gb(self, input_str: str, password: str = '',
                       iv: str = 'gfdertfghjkuyrtg', mode: int = 0,
                       padding: int = 0, out_type: int = 0) -> str:
        """AES 加密 (GB 编码)

        Args:
            input_str: 输入字符串
            password: 密码
            iv: 初始向量 (16字节)
            mode: 模式 (0-ECB, 1-CBC, 2-CFB)
            padding: 填充方式 (0-不填充, 1-PKCS7)
            out_type: 输出类型 (0-Base64, 1-Hex)
        """
        pass

    @dll32('VB6Plus.dll::AESDecrypt_GB')
    def aes_decrypt_gb(self, input_str: str, password: str = '',
                       iv: str = 'gfdertfghjkuyrtg', mode: int = 0,
                       padding: int = 0, in_type: int = 0) -> str:
        """AES 解密 (GB 编码)

        Args:
            input_str: 输入字符串
            password: 密码
            iv: 初始向量 (16字节)
            mode: 模式 (0-ECB, 1-CBC, 2-CFB)
            padding: 填充方式 (0-不填充, 1-PKCS7)
            in_type: 输入类型 (0-Base64, 1-Hex)
        """
        pass

    @dll32('VB6Plus.dll::AESEncrypt_UTF8')
    def aes_encrypt_utf8(self, input_str: str, password: str = '',
                         iv: str = 'gfdertfghjkuyrtg', mode: int = 0,
                         padding: int = 0, out_type: int = 0) -> str:
        """AES 加密 (UTF-8 编码)

        Args:
            input_str: 输入字符串
            password: 密码
            iv: 初始向量 (16字节)
            mode: 模式 (0-ECB, 1-CBC, 2-CFB)
            padding: 填充方式 (0-不填充, 1-PKCS7)
            out_type: 输出类型 (0-Base64, 1-Hex)
        """
        pass

    @dll32('VB6Plus.dll::AESDecrypt_UTF8')
    def aes_decrypt_utf8(self, input_str: str, password: str = '',
                         iv: str = 'gfdertfghjkuyrtg', mode: int = 0,
                         padding: int = 0, in_type: int = 0) -> str:
        """AES 解密 (UTF-8 编码)

        Args:
            input_str: 输入字符串
            password: 密码
            iv: 初始向量 (16字节)
            mode: 模式 (0-ECB, 1-CBC, 2-CFB)
            padding: 填充方式 (0-不填充, 1-PKCS7)
            in_type: 输入类型 (0-Base64, 1-Hex)
        """
        pass

    # ===== HTTP 请求 =====
    @dll32('VB6Plus.dll::XMLHTTP_Get')
    def xmlhttp_get(self, url: str, request_headers: str = '',
                    response_headers: str = '', is_utf8: int = 1,
                    xml_type: int = 0) -> str:
        """XMLHTTP GET 请求

        Args:
            url: URL 地址
            request_headers: 请求头
            response_headers: 响应头 (输出)
            is_utf8: 是否 UTF-8 编码
            xml_type: XMLHTTP 类型 (0-Microsoft_XMLHTTP, 1-MSXML2_ServerXMLHTTP, 2-Msxml2_XMLHTTP_6_0)
        """
        pass

    @dll32('VB6Plus.dll::XMLHTTP_Post')
    def xmlhttp_post(self, url: str, post_data: str,
                     request_headers: str = 'Content-Type:application/x-www-form-urlencoded',
                     response_headers: str = '', is_utf8: int = 1,
                     xml_type: int = 0) -> str:
        """XMLHTTP POST 请求

        Args:
            url: URL 地址
            post_data: POST 数据
            request_headers: 请求头
            response_headers: 响应头 (输出)
            is_utf8: 是否 UTF-8 编码
            xml_type: XMLHTTP 类型
        """
        pass

    # ===== Windows 工具 =====
    @dll32('VB6Plus.dll::Win_CopyFileToClipBoard')
    def win_copy_file_to_clipboard(self, file_or_dir: str) -> int:
        """复制文件到剪贴板

        Returns:
            非0-成功, 0-失败
        """
        pass

    @dll32('VB6Plus.dll::RunVBScript')
    def run_vbscript(self, vbscript: str, error_msg: str) -> int:
        """执行 VBScript

        Args:
            vbscript: VBScript 代码
            error_msg: 错误信息 (输出)

        Returns:
            0-失败, 1-成功
        """
        pass

    # ===== 对话框 =====
    @dll32('VB6Plus.dll::ShowOpenFile')
    def show_open_file(self, hwnd: int = 0, filter_str: str = '全部|*.*|文本文件|*.TXT|图像文件|*.BMP;*.PNG;*.JPG|',
                       init_dir: str = '', title: str = '打开',
                       file_join_str: str = '\r\n', multi_sel: int = 0) -> str:
        """显示打开文件对话框

        Args:
            hwnd: 窗口句柄
            filter_str: 文件过滤器
            init_dir: 初始目录
            title: 对话框标题
            file_join_str: 多文件时的连接符
            multi_sel: 是否多选 (0-单选, 1-多选)
        """
        pass

    @dll32('VB6Plus.dll::ShowSaveFile')
    def show_save_file(self, hwnd: int = 0, filter_str: str = 'TXT文件|*.TXT|LOG文件|*.LOG|',
                       init_dir: str = '', title: str = '另存为',
                       def_ext: str = 'TXT') -> str:
        """显示保存文件对话框

        Args:
            hwnd: 窗口句柄
            filter_str: 文件过滤器
            init_dir: 初始目录
            title: 对话框标题
            def_ext: 默认扩展名
        """
        pass

    @dll32('VB6Plus.dll::ShowBrowserFolder')
    def show_browser_folder(self, hwnd: int = 0, init_dir: str = '', title: str = '选择') -> str:
        """显示浏览文件夹对话框

        Args:
            hwnd: 窗口句柄
            init_dir: 初始目录
            title: 对话框标题
        """
        pass

    # ===== 二维码 =====
    @dll32('VB6Plus.dll::MakeQRCode')
    def make_qrcode(self, qr_text: str, img_file_path: str,
                    size: int = 0, err_rate_level: int = 3, quality: int = 100) -> str:
        """生成二维码图片

        Args:
            qr_text: 二维码文本
            img_file_path: 图片保存路径 (BMP/JPG)
            size: 尺寸 (0-自动, 1-40)
            err_rate_level: 容错等级 (0-L, 1-M, 2-Q, 3-H)
            quality: JPG 质量 (1-100)
        """
        pass

    @dll32('VB6Plus.dll::ScanQRImage')
    def scan_qr_image(self, img_file_path: str, hybrid: int = 0,
                      err_text: str = '', qr_text_is_utf8: int = 0) -> str:
        """扫描二维码图片

        Args:
            img_file_path: 图片路径 (JPG/PNG)
            hybrid: 是否使用混合算法 (0-否, 1-是)
            err_text: 错误信息 (输出)
            qr_text_is_utf8: 二维码文本是否 UTF-8 编码

        Returns:
            二维码内容
        """
        pass

    # ===== 图片转换 =====
    @dll32('VB6Plus.dll::ImageToJPG')
    def image_to_jpg(self, img_file_path: str, jpg_file_path: str, quality: int = 95) -> str:
        """图片转 JPG

        Args:
            img_file_path: 源图片路径 (BMP/JPG/PNG/TIF)
            jpg_file_path: 目标 JPG 路径
            quality: 质量 (1-100)

        Returns:
            "OK"-成功, 其他-错误信息
        """
        pass

    @dll32('VB6Plus.dll::ImageToBMP')
    def image_to_bmp(self, img_file_path: str, bmp_file_path: str) -> str:
        """图片转 BMP

        Args:
            img_file_path: 源图片路径 (BMP/JPG/PNG/TIF)
            bmp_file_path: 目标 BMP 路径

        Returns:
            "OK"-成功, 其他-错误信息
        """
        pass

    # ===== SQLite =====
    @dll32('VB6Plus.dll::SQLite_Open')
    def sqlite_open(self, db_file_name: str = 'DB.DB', str_err: str = '') -> int:
        """打开 SQLite 数据库

        Args:
            db_file_name: 数据库文件路径
            str_err: 错误信息 (输出)

        Returns:
            数据库句柄 (0-失败)
        """
        pass

    @dll32('VB6Plus.dll::SQLite_Close')
    def sqlite_close(self, sqlite_db: int) -> int:
        """关闭 SQLite 数据库

        Args:
            sqlite_db: 数据库句柄

        Returns:
            1-成功, 其他-失败
        """
        pass

    @dll32('VB6Plus.dll::SQLite_Execute')
    def sqlite_execute(self, sqlite_db: int, exe_sql: str, str_err: str = '') -> int:
        """执行 SQL 语句

        Args:
            sqlite_db: 数据库句柄
            exe_sql: SQL 语句
            str_err: 错误信息 (输出)

        Returns:
            1-成功, 其他-失败
        """
        pass


# 全局实例
vb6plus = VB6Plus()
