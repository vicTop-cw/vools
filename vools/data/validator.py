"""
vools.data.validator - 数据验证模块

提供常用的数据验证函数和字符串工具函数，正则模式源自 VB6 Vfx.cls。

验证函数：
    - is_email(value): 验证邮箱格式
    - is_mobile(value): 验证手机号码格式
    - is_id_card_15(value): 验证15位身份证格式
    - is_id_card_18(value): 验证18位身份证格式
    - is_plate_number(value): 验证车牌格式
    - is_url(value): 验证URL格式
    - is_username(value): 验证用户名格式
    - is_password(value): 验证密码格式（字母+数字，6-18位）
    - is_chinese_name(value): 验证中文姓名格式
    - is_phone_with_area(value): 验证带区号电话号码格式
    - is_phone_without_area(value): 验证不带区号电话号码格式

字符串工具函数：
    - is_all_chinese(value): 判断是否全部为中文字符
    - contains_chinese(value): 判断是否包含中文字符
    - starts_with(long_text, short_text): 判断长字符串是否以短字符串开头
    - ends_with(long_text, short_text): 判断长字符串是否以短字符串结尾
"""

import re

__all__ = [
    'is_email',
    'is_mobile',
    'is_id_card_15',
    'is_id_card_18',
    'is_plate_number',
    'is_url',
    'is_username',
    'is_password',
    'is_chinese_name',
    'is_phone_with_area',
    'is_phone_without_area',
    'is_all_chinese',
    'contains_chinese',
    'starts_with',
    'ends_with',
]

_PATTERN_EMAIL = r'\w[-\w.+]*@([A-Za-z0-9][-A-Za-z0-9]*\.)+[A-Za-z]{2,14}'
_PATTERN_MOBILE = r'^(((13[0-9]{1})|(15[0-9]{1})|(17[0-9]{1})|(18[0-9]{1}))+\d{8})$'
_PATTERN_ID_CARD_15 = r'^[1-9]\d{7}((0\d)|(1[0-2]))(([0|1|2]\d)|3[0-1])\d{3}$'
_PATTERN_ID_CARD_18 = r'^[1-9]\d{5}[1-9]\d{3}((0\d)|(1[0-2]))(([0|1|2]\d)|3[0-1])((\d{4})|\d{3}[A-Z])$'
_PATTERN_PLATE_NUMBER = r'^[\u4e00-\u9fa5]{1}[A-Z]{1}[A-Z_0-9]{5}$'
_PATTERN_URL = r'((http|https|ftp):(\/\/|\\\\)((\w)+[.]){1,}(net|com|cn|org|cc|tv|[0-9]{1,3})(((\/[\~]*|\\[\~]*)(\w)+)|[.](\w)+)*(((([?](\w)+){1}[=]*))*((\w)+){1}([\&](\w)+[\=](\w)+)*)*)'
_PATTERN_USERNAME = r'^\w+$'
_PATTERN_PASSWORD = r'^(?=.*?[a-zA-Z])(?=.*?[0-9])[a-zA-Z0-9]{6,18}$'
_PATTERN_CHINESE_NAME = r'^[\u4E00-\u9FA5\uf900-\ufa2d]{2,6}$'
_PATTERN_PHONE_WITH_AREA = r'^0[1-9]\d{1,2}-[0-9]{5,10}$'
_PATTERN_PHONE_WITHOUT_AREA = r'^[1-9]{1}[0-9]{5,8}$'
_PATTERN_CHINESE = r'[\u4E00-\u9FA5\uf900-\ufa2d]'


def is_email(value):
    """验证邮箱格式

    Args:
        value: 待验证的字符串

    Returns:
        bool: 验证通过返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.match(_PATTERN_EMAIL, str(value)))


def is_mobile(value):
    """验证手机号码格式

    Args:
        value: 待验证的字符串

    Returns:
        bool: 验证通过返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.match(_PATTERN_MOBILE, str(value)))


def is_id_card_15(value):
    """验证15位身份证格式

    Args:
        value: 待验证的字符串

    Returns:
        bool: 验证通过返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.match(_PATTERN_ID_CARD_15, str(value)))


def is_id_card_18(value):
    """验证18位身份证格式

    Args:
        value: 待验证的字符串

    Returns:
        bool: 验证通过返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.match(_PATTERN_ID_CARD_18, str(value)))


def is_plate_number(value):
    """验证车牌格式

    Args:
        value: 待验证的字符串

    Returns:
        bool: 验证通过返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.match(_PATTERN_PLATE_NUMBER, str(value)))


def is_url(value):
    """验证URL格式

    Args:
        value: 待验证的字符串

    Returns:
        bool: 验证通过返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.match(_PATTERN_URL, str(value)))


def is_username(value):
    """验证用户名格式（26个英文字母、数字及下划线）

    Args:
        value: 待验证的字符串

    Returns:
        bool: 验证通过返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.match(_PATTERN_USERNAME, str(value)))


def is_password(value):
    """验证密码格式（字母+数字，6-18位）

    Args:
        value: 待验证的字符串

    Returns:
        bool: 验证通过返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.match(_PATTERN_PASSWORD, str(value)))


def is_chinese_name(value):
    """验证中文姓名格式（2-5个汉字）

    Args:
        value: 待验证的字符串

    Returns:
        bool: 验证通过返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.match(_PATTERN_CHINESE_NAME, str(value)))


def is_phone_with_area(value):
    """验证带区号电话号码格式

    Args:
        value: 待验证的字符串

    Returns:
        bool: 验证通过返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.match(_PATTERN_PHONE_WITH_AREA, str(value)))


def is_phone_without_area(value):
    """验证不带区号电话号码格式

    Args:
        value: 待验证的字符串

    Returns:
        bool: 验证通过返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.match(_PATTERN_PHONE_WITHOUT_AREA, str(value)))


def is_all_chinese(value):
    """判断是否全部为中文字符

    Args:
        value: 待判断的字符串

    Returns:
        bool: 全部为中文返回 True，否则返回 False
    """
    if not value:
        return False
    value = str(value)
    if len(value) == 0:
        return False
    for char in value:
        if not re.match(_PATTERN_CHINESE, char):
            return False
    return True


def contains_chinese(value):
    """判断是否包含中文字符

    Args:
        value: 待判断的字符串

    Returns:
        bool: 包含中文返回 True，否则返回 False
    """
    if not value:
        return False
    return bool(re.search(_PATTERN_CHINESE, str(value)))


def starts_with(long_text, short_text):
    """判断长字符串是否以短字符串开头

    Args:
        long_text: 长字符串
        short_text: 短字符串（前缀）

    Returns:
        bool: long_text 以 short_text 开头返回 True，否则返回 False
    """
    if not long_text or not short_text:
        return False
    long_text = str(long_text)
    short_text = str(short_text)
    if len(long_text) < len(short_text):
        return False
    return long_text.startswith(short_text)


def ends_with(long_text, short_text):
    """判断长字符串是否以短字符串结尾

    Args:
        long_text: 长字符串
        short_text: 短字符串（后缀）

    Returns:
        bool: long_text 以 short_text 结尾返回 True，否则返回 False
    """
    if not long_text or not short_text:
        return False
    long_text = str(long_text)
    short_text = str(short_text)
    if len(long_text) < len(short_text):
        return False
    return long_text.endswith(short_text)
