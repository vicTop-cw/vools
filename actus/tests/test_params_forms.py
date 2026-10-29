# -*- coding: utf-8 -*-
"""阶段1：入参七形态的验收（ACTUS_REFACTOR_PLAN §3.2）。

支持：JSON 字面量 / @file / stdin / @url / @action:<id>。
本轮修掉两处安全缺陷并锁定：
  - 白名单语义反了：`if allow_hosts:` 把空列表当成「不校验」⇒ 任何 URL 都能
    下载（与文档『空列表表示禁止所有远程』相反，SSRF 风险）
  - SSL 证书校验被禁用（CERT_NONE + check_hostname=False）⇒ 动作源可被
    中间人替换（供应链风险，计划 §六.3）
"""
import io
import json

import pytest

from vools.actus.resolver import resolve_params_extended


def test_params_json_literal():
    assert resolve_params_extended('{"a": 1}') == {"a": 1}


def test_params_empty():
    assert resolve_params_extended("") == {}
    assert resolve_params_extended("{}") == {}


def test_params_at_file(tmp_path):
    f = tmp_path / "args.json"
    f.write_text(json.dumps({"from_file": True}), encoding="utf-8")
    assert resolve_params_extended("@" + str(f)) == {"from_file": True}


def test_params_at_file_not_json(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        resolve_params_extended("@" + str(f))


# --------------------------------------------------------------------------
# 安全门禁：URL 默认拒绝
# --------------------------------------------------------------------------
def test_params_url_without_whitelist_is_denied():
    """未配置白名单时必须拒（此前会直接去下载）。"""
    with pytest.raises(Exception) as exc:
        resolve_params_extended("@https://example.invalid/a.json")
    assert getattr(exc.value, "code", "") == "remote_host_denied", exc.value


def test_params_bare_url_without_whitelist_is_denied():
    with pytest.raises(Exception) as exc:
        resolve_params_extended("https://example.invalid/a.json")
    assert getattr(exc.value, "code", "") == "remote_host_denied", exc.value


def test_params_url_outside_whitelist_is_denied():
    with pytest.raises(Exception) as exc:
        resolve_params_extended("@https://evil.invalid/a.json",
                                allow_hosts=["example.invalid"])
    assert getattr(exc.value, "code", "") == "remote_host_denied", exc.value


def test_params_url_inside_whitelist_attempts_download():
    """白名单内应放行到下载阶段（本环境 DNS 不通 ⇒ remote_download_failed）。"""
    with pytest.raises(Exception) as exc:
        resolve_params_extended("@https://example.invalid/a.json",
                                allow_hosts=["example.invalid"])
    code = getattr(exc.value, "code", "")
    assert code != "remote_host_denied", "白名单内的主机不应被白名单门禁拦下"
    assert code in ("remote_download_failed", "remote_too_large"), code


# --------------------------------------------------------------------------
# SSL 校验不得被禁用（负向源码断言 + 真实 TLS 行为对照）
# --------------------------------------------------------------------------
def test_download_helpers_do_not_disable_ssl_verification():
    """负向安全断言保留（防"未来有人加回 CERT_NONE"——这是静态约束）。

    ⚠️ 为什么这条**保留静态**：它防的是"未来某个 PR 重新引入危险写法"，
    不是当前行为；行为层的对照见下一条
    `test_https_self_signed_certificate_is_rejected`（真正起一个自签 TLS 服务，
    证明校验没被绕过）。
    """
    import inspect
    from vools.actus import resolver as r
    for fn in (r._download_url, r._download_json_url):
        src = inspect.getsource(fn)
        assert "CERT_NONE" not in src, "%s 仍在禁用 SSL 证书校验" % fn.__name__
        assert "check_hostname = False" not in src, "%s 仍在禁用主机名校验" % fn.__name__


@pytest.mark.timeout(90)
def test_https_self_signed_certificate_is_rejected(tmp_path):
    """行为对照：CERT_NONE 若被启用，自签证书会被静默接受；现在必须拒绝。

    起一个本地 HTTPS 服务（自签证书），让 `_download_url` 去下载 ——
    预期 fail（remote_download_failed + 证书错误）；若 SSL 校验被关，
    下载会成功、断言立刻红。
    """
    import datetime
    import ipaddress
    import ssl
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:  # pragma: no cover —— 环境缺 crypto 时跳过（不是产品缺陷）
        pytest.skip("cryptography 不可用，无法构造自签证书")

    from vools.actus import resolver as r

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"127.0.0.1")])
    now = datetime.datetime.utcnow()
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(minutes=5))
            .add_extension(x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address(u"127.0.0.1"))]),
                critical=False)
            .sign(key, hashes.SHA256()))
    pem = tmp_path / "server.pem"
    pem.write_bytes(
        key.private_bytes(serialization.Encoding.PEM,
                          serialization.PrivateFormat.TraditionalOpenSSL,
                          serialization.NoEncryption())
        + cert.public_bytes(serialization.Encoding.PEM))

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"---\nid: r20.selfsigned\n---\n"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(pem))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = "https://127.0.0.1:%d/a.actus.md" % httpd.server_port
        with pytest.raises(Exception) as exc:
            r._download_url(url, allow_hosts=["127.0.0.1"])
        assert getattr(exc.value, "code", "") == "remote_download_failed", exc.value
        text = str(exc.value).lower()
        assert "certificate" in text or "ssl" in text or "tls" in text, exc.value
    finally:
        httpd.shutdown()
