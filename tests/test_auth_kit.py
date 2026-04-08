"""
Tests for iot_hub_shared.auth_kit.

Covers:
  - JWTValidator: valid token, expired, tampered, unknown kid, JWKS fetch failure, caching.
  - JWTAuthMiddleware: sets request.user on success, None on failure/missing header.
  - login_required decorator: 401 when no user.
  - role_required decorator: 401 when no user, 403 on wrong role, passes on correct role.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from iot_hub_shared.auth_kit.exceptions import TokenExpiredError, TokenInvalidError
from iot_hub_shared.auth_kit.middleware import JWTAuthMiddleware, login_required, role_required
from iot_hub_shared.auth_kit.models import AuthenticatedUser
from iot_hub_shared.auth_kit.validator import JWTValidator
from iot_hub_shared.test_kit.auth import (
    auth_kit_jwt_factory,
    auth_kit_rsa_key_pair,
    make_test_jwt,
    make_test_rsa_key_pair,
    mock_jwks_server,
)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _valid_payload(sub: str = "1", role: str = "client") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "sub": sub,  # JWT sub is always a string; middleware casts to int
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "jti": str(uuid.uuid4()),
    }


def _expired_payload(sub: str = "1", role: str = "client") -> dict:
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    return {
        "sub": sub,
        "role": role,
        "iat": int(past.timestamp()),
        "exp": int((past + timedelta(hours=1)).timestamp()),
        "jti": str(uuid.uuid4()),
    }


# ── JWTValidator ─────────────────────────────────────────────────────────────

class TestJWTValidator:
    def setup_method(self):
        self.private_pem, self.public_pem = make_test_rsa_key_pair()
        self.validator = JWTValidator(jwks_uri="http://mock-jwks/", cache_ttl=3600)

    def test_valid_token_returns_payload(self):
        token = make_test_jwt(_valid_payload(), self.private_pem)
        with mock_jwks_server(self.public_pem):
            payload = self.validator.validate(token)
        assert payload["sub"] == "1"
        assert payload["role"] == "client"

    def test_expired_token_raises_token_expired_error(self):
        token = make_test_jwt(_expired_payload(), self.private_pem)
        with mock_jwks_server(self.public_pem):
            with pytest.raises(TokenExpiredError):
                self.validator.validate(token)

    def test_tampered_token_raises_token_invalid_error(self):
        token = make_test_jwt(_valid_payload(), self.private_pem)
        tampered = token[:-6] + "XXXXXX"
        with mock_jwks_server(self.public_pem):
            with pytest.raises(TokenInvalidError):
                self.validator.validate(token=tampered)

    def test_unknown_kid_raises_token_invalid_error(self):
        token = make_test_jwt(_valid_payload(), self.private_pem, kid="unknown-kid")
        with mock_jwks_server(self.public_pem, kid="test-key"):  # different kid
            with pytest.raises(TokenInvalidError, match="Unknown key ID"):
                self.validator.validate(token)

    def test_jwks_fetch_failure_raises_token_invalid_error(self):
        token = make_test_jwt(_valid_payload(), self.private_pem)
        with patch(
            "iot_hub_shared.auth_kit.validator.JWTValidator._fetch_jwks",
            side_effect=Exception("connection refused"),
        ):
            with pytest.raises(TokenInvalidError, match="Failed to fetch JWKS"):
                self.validator.validate(token)

    def test_malformed_token_raises_token_invalid_error(self):
        with pytest.raises(TokenInvalidError, match="Malformed token header"):
            self.validator.validate("not.a.token")

    def test_key_is_cached_after_first_validation(self):
        token = make_test_jwt(_valid_payload(), self.private_pem)
        with mock_jwks_server(self.public_pem) as _:
            self.validator.validate(token)
            fetch_count_after_first = 1

        # Second validation must NOT call _fetch_jwks again (cache hit).
        with patch.object(self.validator, "_fetch_jwks", wraps=self.validator._fetch_jwks) as mock_fetch:
            with mock_jwks_server(self.public_pem):
                # Manually warm the cache so the mock is hit only if needed.
                self.validator.validate(token)
            # _fetch_jwks should not have been called — cache was warm.
            mock_fetch.assert_not_called()

    def test_key_rotation_refetches_and_validates(self):
        """
        Simulates a key rotation: first JWKS has the wrong key,
        second JWKS (after rotation) has the correct key.
        The validator should retry once and succeed.
        """
        _, wrong_public_pem = make_test_rsa_key_pair()  # Different, wrong key.
        token = make_test_jwt(_valid_payload(), self.private_pem)

        wrong_jwks = _build_jwks(wrong_public_pem, kid="test-key")
        correct_jwks = _build_jwks(self.public_pem, kid="test-key")
        call_count = {"n": 0}

        def side_effect():
            call_count["n"] += 1
            return wrong_jwks if call_count["n"] == 1 else correct_jwks

        with patch.object(self.validator, "_fetch_jwks", side_effect=side_effect):
            payload = self.validator.validate(token)

        assert payload["sub"] == "1"
        assert call_count["n"] == 2


# ── JWTAuthMiddleware ─────────────────────────────────────────────────────────

class TestJWTAuthMiddleware:
    def setup_method(self):
        self.private_pem, self.public_pem = make_test_rsa_key_pair()
        self.factory = RequestFactory()

    def _make_middleware(self):
        def dummy_get_response(request):
            from django.http import HttpResponse
            return HttpResponse("ok")

        middleware = JWTAuthMiddleware(dummy_get_response)
        # Inject a pre-configured validator to avoid hitting settings.
        middleware._validator = JWTValidator(jwks_uri="http://mock/", cache_ttl=3600)
        return middleware

    def test_valid_token_sets_authenticated_user(self):
        token = make_test_jwt(_valid_payload(sub="42", role="admin"), self.private_pem)
        request = self.factory.get("/", HTTP_AUTHORIZATION=f"Bearer {token}")
        middleware = self._make_middleware()

        with mock_jwks_server(self.public_pem):
            middleware(request)

        assert isinstance(request.user, AuthenticatedUser)
        assert request.user.id == 42
        assert isinstance(request.user.id, int)
        assert request.user.role == "admin"
        assert request.auth_token_payload is not None

    def test_invalid_token_sets_user_to_none(self):
        request = self.factory.get("/", HTTP_AUTHORIZATION="Bearer not.a.real.token")
        middleware = self._make_middleware()
        with mock_jwks_server(self.public_pem):
            middleware(request)
        assert request.user is None

    def test_missing_authorization_header_sets_user_to_none(self):
        request = self.factory.get("/")
        middleware = self._make_middleware()
        middleware(request)
        assert request.user is None

    def test_expired_token_sets_user_to_none(self):
        token = make_test_jwt(_expired_payload(), self.private_pem)
        request = self.factory.get("/", HTTP_AUTHORIZATION=f"Bearer {token}")
        middleware = self._make_middleware()
        with mock_jwks_server(self.public_pem):
            middleware(request)
        assert request.user is None

    def test_non_bearer_scheme_sets_user_to_none(self):
        request = self.factory.get("/", HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz")
        middleware = self._make_middleware()
        middleware(request)
        assert request.user is None


# ── login_required ────────────────────────────────────────────────────────────

class TestLoginRequired:
    def setup_method(self):
        self.factory = RequestFactory()

    def test_no_user_returns_401(self):
        @login_required
        def view(request):
            from django.http import HttpResponse
            return HttpResponse("ok")

        request = self.factory.get("/")
        request.user = None
        response = view(request)
        assert response.status_code == 401

    def test_authenticated_user_calls_view(self):
        @login_required
        def view(request):
            from django.http import HttpResponse
            return HttpResponse("ok")

        request = self.factory.get("/")
        request.user = AuthenticatedUser(id=1, role="client", token_jti="jti")
        response = view(request)
        assert response.status_code == 200


# ── role_required ─────────────────────────────────────────────────────────────

class TestRoleRequired:
    def setup_method(self):
        self.factory = RequestFactory()

    def _view(self, request):
        from django.http import HttpResponse
        return HttpResponse("ok")

    def test_no_user_returns_401(self):
        request = self.factory.get("/")
        request.user = None
        response = role_required("admin")(self._view)(request)
        assert response.status_code == 401

    def test_wrong_role_returns_403(self):
        request = self.factory.get("/")
        request.user = AuthenticatedUser(id=1, role="client", token_jti="jti")
        response = role_required("admin")(self._view)(request)
        assert response.status_code == 403

    def test_correct_role_calls_view(self):
        request = self.factory.get("/")
        request.user = AuthenticatedUser(id="1", role="admin", token_jti="jti")
        response = role_required("admin")(self._view)(request)
        assert response.status_code == 200

    def test_multiple_allowed_roles(self):
        request = self.factory.get("/")
        request.user = AuthenticatedUser(id="1", role="operator", token_jti="jti")
        response = role_required("admin", "operator")(self._view)(request)
        assert response.status_code == 200


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_jwks(public_pem: str, kid: str) -> dict:
    """Build a JWKS dict from a PEM public key (mirrors mock_jwks_server internals)."""
    import base64
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    def b64url(n: int) -> str:
        byte_len = (n.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(n.to_bytes(byte_len, "big")).rstrip(b"=").decode()

    pub = load_pem_public_key(public_pem.encode())
    nums = pub.public_numbers()
    return {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256",
                      "kid": kid, "n": b64url(nums.n), "e": b64url(nums.e)}]}
