import json
import time
import urllib.request
from typing import Any

import jwt
from jwt.algorithms import RSAAlgorithm

from .exceptions import TokenExpiredError, TokenInvalidError


class JWTValidator:
    """
    RS256 JWT validator with in-process JWKS key caching.

    Fetches the public key from the auth-service JWKS endpoint on first use,
    caches it for `cache_ttl` seconds, and re-fetches on cache expiry or
    unknown kid (key rotation support).

    Usage:
        validator = JWTValidator(jwks_uri="http://auth-service:8001/api/auth/.well-known/jwks.json")
        payload = validator.validate(token)
    """

    def __init__(self, jwks_uri: str, cache_ttl: int = 3600) -> None:
        self._jwks_uri = jwks_uri
        self._cache_ttl = cache_ttl
        # kid -> (public_key_object, fetched_at_timestamp)
        self._key_cache: dict[str, tuple[Any, float]] = {}

    def validate(self, token: str) -> dict:
        """
        Decode and verify an RS256 JWT.

        Returns the decoded payload dict on success.
        Raises TokenExpiredError if the token has expired.
        Raises TokenInvalidError for any other failure (bad signature, malformed, unknown kid).
        """
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise TokenInvalidError("Malformed token header") from exc

        kid = header.get("kid")

        # First attempt with cached (or freshly fetched) key.
        public_key = self._resolve_key(kid, force_refresh=False)
        try:
            return jwt.decode(token, public_key, algorithms=["RS256"])
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("Token has expired") from exc
        except jwt.InvalidTokenError:
            pass  # Signature mismatch — key may have been rotated.

        # Second attempt after a forced JWKS refresh (key rotation path).
        public_key = self._resolve_key(kid, force_refresh=True)
        try:
            return jwt.decode(token, public_key, algorithms=["RS256"])
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("Token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise TokenInvalidError("Token signature verification failed") from exc

    # ── Private ───────────────────────────────────────────────────────────────

    def _resolve_key(self, kid: str | None, force_refresh: bool) -> Any:
        """Return the public key for the given kid, fetching JWKS if necessary."""
        if not force_refresh:
            cached = self._from_cache(kid)
            if cached is not None:
                return cached

        self._refresh_cache()

        if kid is not None:
            if kid not in self._key_cache:
                raise TokenInvalidError(f"Unknown key ID '{kid}' — not found in JWKS")
            return self._key_cache[kid][0]

        # No kid in token header — use first available key.
        if not self._key_cache:
            raise TokenInvalidError("JWKS endpoint returned no usable keys")
        return next(iter(self._key_cache.values()))[0]

    def _from_cache(self, kid: str | None) -> Any | None:
        """Return a cached key if present and within TTL, otherwise None."""
        now = time.time()
        if kid is not None:
            entry = self._key_cache.get(kid)
            if entry and now - entry[1] < self._cache_ttl:
                return entry[0]
        else:
            # No kid — use first key if cache is not empty and fresh.
            for key_obj, fetched_at in self._key_cache.values():
                if now - fetched_at < self._cache_ttl:
                    return key_obj
        return None

    def _refresh_cache(self) -> None:
        """Fetch JWKS and rebuild the key cache."""
        try:
            jwks = self._fetch_jwks()
        except TokenInvalidError:
            raise
        except Exception as exc:
            raise TokenInvalidError(f"Failed to fetch JWKS: {exc}") from exc
        now = time.time()
        new_cache: dict[str, tuple[Any, float]] = {}
        for jwk in jwks.get("keys", []):
            entry_kid = jwk.get("kid", "default")
            try:
                key_obj = RSAAlgorithm.from_jwk(jwk)
                new_cache[entry_kid] = (key_obj, now)
            except Exception:
                pass  # Skip malformed JWK entries.
        if new_cache:
            self._key_cache = new_cache

    def _fetch_jwks(self) -> dict:
        """Fetch the JWKS document from the configured URI."""
        try:
            with urllib.request.urlopen(self._jwks_uri, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise TokenInvalidError(f"Failed to fetch JWKS from '{self._jwks_uri}': {exc}") from exc
