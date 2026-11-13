"""Google sign-in: id_token verification with cached certificates.

auth_google decodes the token via google.auth.jwt.decode with certificates from _google_certs() (cached for an hour), so a sign-in does not fetch them every time. The signature, audience and expiry are still verified.
"""

import datetime as dt
import time

import pytest

crypto = pytest.importorskip("cryptography")
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402
from google.auth import crypt, jwt  # noqa: E402

import jumpsight_coach.api as api  # noqa: E402

CID = "test-client.apps.googleusercontent.com"


def _key_and_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem_key = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return pem_key, cert.public_bytes(serialization.Encoding.PEM).decode()


def _token(pem_key, aud=CID, exp_in=600):
    signer = crypt.RSASigner.from_string(pem_key, key_id="k1")
    now = int(time.time())
    return jwt.encode(
        signer,
        {
            "iss": "https://accounts.google.com",
            "sub": "123",
            "aud": aud,
            "iat": now,
            "exp": now + exp_in,
            "email": "a@b.c",
        },
    ).decode()


def test_valid_token_decodes_with_cached_certs(monkeypatch):
    pem_key, cert = _key_and_cert()
    monkeypatch.setattr(api, "_google_certs", lambda: {"k1": cert})
    info = jwt.decode(_token(pem_key), certs=api._google_certs(), audience=CID, clock_skew_in_seconds=10)
    assert info["sub"] == "123"


@pytest.mark.parametrize("kw", [{"aud": "someone-else"}, {"exp_in": -3600}])
def test_wrong_audience_or_expired_token_is_rejected(monkeypatch, kw):
    pem_key, cert = _key_and_cert()
    with pytest.raises(ValueError):
        jwt.decode(_token(pem_key, **kw), certs={"k1": cert}, audience=CID, clock_skew_in_seconds=10)


def test_token_signed_by_another_key_is_rejected():
    pem_key, _ = _key_and_cert()
    _, other_cert = _key_and_cert()
    with pytest.raises(ValueError):
        jwt.decode(_token(pem_key), certs={"k1": other_cert}, audience=CID, clock_skew_in_seconds=10)
