"""
测试 vools.data.validator 模块

验证函数测试用例覆盖：有效、无效、边界场景
"""

import pytest
from vools.data import (
    is_email, is_mobile, is_id_card_15, is_id_card_18,
    is_plate_number, is_url, is_username, is_password,
    is_chinese_name, is_phone_with_area, is_phone_without_area,
    is_all_chinese, contains_chinese, starts_with, ends_with,
)


class TestEmailValidation:
    """邮箱验证测试"""

    def test_valid_email(self):
        assert is_email('test@example.com') is True
        assert is_email('user.name@domain.org') is True
        assert is_email('user+tag@mail.cn') is True
        assert is_email('admin@company.tv') is True

    def test_invalid_email(self):
        assert is_email('invalid') is False
        assert is_email('@nodomain.com') is False
        assert is_email('no@domain') is False
        assert is_email('no@.com') is False

    def test_boundary_email(self):
        assert is_email('') is False
        assert is_email(None) is False
        assert is_email('a@b.co') is True


class TestMobileValidation:
    """手机号码验证测试"""

    def test_valid_mobile(self):
        assert is_mobile('13812345678') is True
        assert is_mobile('15987654321') is True
        assert is_mobile('17012345678') is True
        assert is_mobile('18087654321') is True

    def test_invalid_mobile(self):
        assert is_mobile('12345678901') is False
        assert is_mobile('1381234567') is False
        assert is_mobile('138123456789') is False
        assert is_mobile('11912345678') is False

    def test_boundary_mobile(self):
        assert is_mobile('') is False
        assert is_mobile(None) is False


class TestIdCardValidation:
    """身份证验证测试"""

    def test_valid_id_card_15(self):
        assert is_id_card_15('110101800101123') is True
        assert is_id_card_15('320102901212001') is True

    def test_invalid_id_card_15(self):
        assert is_id_card_15('110101800101') is False
        assert is_id_card_15('010101800101123') is False
        assert is_id_card_15('110101801301123') is False

    def test_valid_id_card_18(self):
        assert is_id_card_18('110101198001011234') is True
        assert is_id_card_18('32010219901212001X') is True

    def test_invalid_id_card_18(self):
        assert is_id_card_18('11010119800101') is False
        assert is_id_card_18('010101198001011234') is False
        assert is_id_card_18('110101198013011234') is False

    def test_boundary_id_card(self):
        assert is_id_card_15('') is False
        assert is_id_card_15(None) is False
        assert is_id_card_18('') is False
        assert is_id_card_18(None) is False


class TestPlateNumberValidation:
    """车牌验证测试"""

    def test_valid_plate_number(self):
        assert is_plate_number('京A12345') is True
        assert is_plate_number('粤B88888') is True
        assert is_plate_number('浙C123A5') is True

    def test_invalid_plate_number(self):
        assert is_plate_number('京12345') is False
        assert is_plate_number('A12345') is False
        assert is_plate_number('京AA12345') is False

    def test_boundary_plate_number(self):
        assert is_plate_number('') is False
        assert is_plate_number(None) is False


class TestUrlValidation:
    """URL验证测试"""

    def test_valid_url(self):
        assert is_url('http://www.example.com') is True
        assert is_url('https://www.example.com/path') is True
        assert is_url('ftp://ftp.example.net') is True
        assert is_url('http://example.cn/page?id=1') is True

    def test_invalid_url(self):
        assert is_url('not a url') is False
        assert is_url('www.example.com') is False
        assert is_url('http://') is False

    def test_boundary_url(self):
        assert is_url('') is False
        assert is_url(None) is False


class TestUsernameValidation:
    """用户名验证测试"""

    def test_valid_username(self):
        assert is_username('user') is True
        assert is_username('user123') is True
        assert is_username('user_name') is True

    def test_invalid_username(self):
        assert is_username('user name') is False
        assert is_username('user@name') is False
        assert is_username('user#name') is False

    def test_boundary_username(self):
        assert is_username('') is False
        assert is_username(None) is False


class TestPasswordValidation:
    """密码验证测试"""

    def test_valid_password(self):
        assert is_password('abc123') is True
        assert is_password('Password1') is True
        assert is_password('a1b2c3d4') is True

    def test_invalid_password(self):
        assert is_password('abc') is False
        assert is_password('123456') is False
        assert is_password('abcdef') is False
        assert is_password('toolongpassword123456789') is False

    def test_boundary_password(self):
        assert is_password('') is False
        assert is_password(None) is False


class TestChineseNameValidation:
    """中文姓名验证测试"""

    def test_valid_chinese_name(self):
        assert is_chinese_name('张三') is True
        assert is_chinese_name('李四') is True
        assert is_chinese_name('欧阳明') is True

    def test_invalid_chinese_name(self):
        assert is_chinese_name('张') is False
        assert is_chinese_name('张三四五六七八') is False
        assert is_chinese_name('zhangsan') is False

    def test_boundary_chinese_name(self):
        assert is_chinese_name('') is False
        assert is_chinese_name(None) is False


class TestPhoneValidation:
    """电话号码验证测试"""

    def test_valid_phone_with_area(self):
        assert is_phone_with_area('010-12345678') is True
        assert is_phone_with_area('021-87654321') is True
        assert is_phone_with_area('0755-1234567') is True

    def test_invalid_phone_with_area(self):
        assert is_phone_with_area('10-12345678') is False
        assert is_phone_with_area('01012345678') is False

    def test_valid_phone_without_area(self):
        assert is_phone_without_area('12345678') is True
        assert is_phone_without_area('87654321') is True

    def test_invalid_phone_without_area(self):
        assert is_phone_without_area('01234567') is False
        assert is_phone_without_area('1234') is False

    def test_boundary_phone(self):
        assert is_phone_with_area('') is False
        assert is_phone_with_area(None) is False
        assert is_phone_without_area('') is False
        assert is_phone_without_area(None) is False


class TestStringUtils:
    """字符串工具函数测试"""

    def test_is_all_chinese(self):
        assert is_all_chinese('中文') is True
        assert is_all_chinese('中文测试') is True
        assert is_all_chinese('中文123') is False
        assert is_all_chinese('chinese') is False
        assert is_all_chinese('') is False
        assert is_all_chinese(None) is False

    def test_contains_chinese(self):
        assert contains_chinese('中文') is True
        assert contains_chinese('中文test') is True
        assert contains_chinese('test中文') is True
        assert contains_chinese('chinese') is False
        assert contains_chinese('12345') is False
        assert contains_chinese('') is False
        assert contains_chinese(None) is False

    def test_starts_with(self):
        assert starts_with('hello world', 'hello') is True
        assert starts_with('hello world', 'world') is False
        assert starts_with('hello', 'hello world') is False
        assert starts_with('', 'hello') is False
        assert starts_with('hello', '') is False
        assert starts_with(None, 'hello') is False
        assert starts_with('hello', None) is False

    def test_ends_with(self):
        assert ends_with('hello world', 'world') is True
        assert ends_with('hello world', 'hello') is False
        assert ends_with('world', 'hello world') is False
        assert ends_with('', 'world') is False
        assert ends_with('world', '') is False
        assert ends_with(None, 'world') is False
        assert ends_with('world', None) is False
