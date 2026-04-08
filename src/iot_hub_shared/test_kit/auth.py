"""
Auth kit test helpers and fixtures.

Provides:
    make_test_rsa_key_pair()    — generates a throwaway RSA key pair (no files, no disk).
    make_test_jwt()             — signs a JWT with the test private key.
    mock_jwks_server()          — context manager that patches _fetch_jwks without HTTP.
    auth_kit_rsa_key_pair       — session-scoped pytest fixture (key pair).
    auth_kit_jwt_factory        — function-scoped fixture returning a JWT builder callable.

These fixtures are NOT registered in the pytest11 plugin automatically because they
require PyJWT + cryptography (optional deps). To use them, import explicitly in
your service's conftest.py:

    from iot_hub_shared.test_kit.auth import auth_kit_rsa_key_pair, auth_kit_jwt_factory
"""

from __future__ import annotations

import base64
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def make_test_rsa_key_pair() -> tuple[str, str]:
    """
    Generate a throwaway 2048-bit RSA key pair in memory.
    Returns (private_pem, public_pem) as strings.
    Never touches the filesystem.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return private_pem, public_pem


def make_test_jwt(
    payload: dict[str, Any],
    private_key: str,
    *,
    kid: str = "test-key",
) -> str:
    """Sign and return an RS256 JWT using the given PEM private key."""
    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


@contextmanager
def mock_jwks_server(public_key_pem: str, *, kid: str = "test-key"):
    """
    Context manager that patches JWTValidator._fetch_jwks to return a JWKS
    built from the given PEM public key. No HTTP calls are made.

    Usage:
        private_pem, public_pem = make_test_rsa_key_pair()
        token = make_test_jwt({"sub": "1", "role": "admin", ...}, private_pem)
        with mock_jwks_server(public_pem):
            payload = validator.validate(token)
    """
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    def _b64url(n: int) -> str:
        byte_len = (n.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(n.to_bytes(byte_len, "big")).rstrip(b"=").decode()

    pub_key = load_pem_public_key(public_key_pem.encode())
    numbers = pub_key.public_numbers()
    jwks = {
        "keys": [{
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": kid,
            "n": _b64url(numbers.n),
            "e": _b64url(numbers.e),
        }]
    }

    with patch(
        "iot_hub_shared.auth_kit.validator.JWTValidator._fetch_jwks",
        return_value=jwks,
    ):
        yield


# ── Pytest fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def auth_kit_rsa_key_pair() -> tuple[str, str]:
    """Session-scoped throwaway RSA key pair. Returns (private_pem, public_pem)."""
    return make_test_rsa_key_pair()


@pytest.fixture
def auth_kit_jwt_factory(auth_kit_rsa_key_pair):
    """
    Function-scoped fixture returning a callable that builds signed JWTs.
    Adds sane defaults for iat, exp, jti if not supplied.

    Usage:
        def test_something(auth_kit_jwt_factory):
            token = auth_kit_jwt_factory({"sub": "123", "role": "admin"})
    """
    private_key, _ = auth_kit_rsa_key_pair

    def _factory(payload: dict[str, Any], *, kid: str = "test-key") -> str:
        now = datetime.now(timezone.utc)
        defaults: dict[str, Any] = {
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "jti": str(uuid.uuid4()),
        }
        merged = {**defaults, **payload}
        # JWT "sub" must be a string; accept int IDs and coerce automatically.
        if "sub" in merged:
            merged["sub"] = str(merged["sub"])
        return make_test_jwt(merged, private_key, kid=kid)

    return _factory
