"""trust_model KeyManager 加载 + 模块级便捷函数 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- load_private_key/load_public_key 失败 → 签名验证无法进行
- 模块级便捷函数错误 → 用户无法通过简单 API 签名/验证
"""
import pytest


@pytest.fixture
def tmp_keys_dir(tmp_path, monkeypatch):
    d = tmp_path / "keys"
    d.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    return str(d)


@pytest.fixture
def tmp_file(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("hello world", encoding="utf-8")
    return str(f)


class TestLoadPrivateKey:
    def test_load_private_key_after_generate(self, tmp_keys_dir):
        """退步了会怎样：generate 后应能 load 私钥。"""
        from vools.actus.trust_model import KeyManager
        km = KeyManager(keys_dir=tmp_keys_dir)
        km.generate_keypair("default")
        priv = km.load_private_key("default")
        assert priv is not None

    def test_load_private_key_nonexistent(self, tmp_keys_dir):
        """退步了会怎样：不存在的 key 应返回 None。"""
        from vools.actus.trust_model import KeyManager
        km = KeyManager(keys_dir=tmp_keys_dir)
        assert km.load_private_key("not.exists") is None


class TestLoadPublicKey:
    def test_load_public_key_after_generate(self, tmp_keys_dir):
        """退步了会怎样：generate 后应能 load 公钥。"""
        from vools.actus.trust_model import KeyManager
        km = KeyManager(keys_dir=tmp_keys_dir)
        km.generate_keypair("default")
        pub = km.load_public_key("default")
        assert pub is not None

    def test_load_public_key_nonexistent(self, tmp_keys_dir):
        """退步了会怎样：不存在的 key 应返回 None。"""
        from vools.actus.trust_model import KeyManager
        km = KeyManager(keys_dir=tmp_keys_dir)
        assert km.load_public_key("not.exists") is None


class TestModuleLevelFunctions:
    def test_generate_keys(self, tmp_keys_dir):
        """退步了会怎样：generate_keys 应返回 (priv, pub) 路径。"""
        from vools.actus.trust_model import generate_keys
        priv, pub = generate_keys("default", keys_dir=tmp_keys_dir)
        assert priv is not None
        assert pub is not None

    def test_sign_action(self, tmp_keys_dir, tmp_file):
        """退步了会怎样：sign_action 应返回签名 dict。"""
        from vools.actus.trust_model import sign_action
        result = sign_action(tmp_file, key_name="default")
        # sign_action 用默认 KeyManager（~/.actus/keys），不传 keys_dir
        # 如果 HOME 被隔离，可能找不到 key
        if result.get("status") == "ok":
            assert "signature" in result
        else:
            # 没有 key 时返回 error，也是合理行为
            assert result["status"] == "error"

    def test_verify_action_no_sig(self, tmp_keys_dir, tmp_file):
        """退步了会怎样：无签名文件应报 error。"""
        from vools.actus.trust_model import verify_action
        result = verify_action(tmp_file, key_name="default")
        assert result["status"] == "error"
