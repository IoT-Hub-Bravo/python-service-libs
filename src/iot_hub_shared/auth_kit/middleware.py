from functools import wraps

from django.conf import settings
from django.http import JsonResponse

from .exceptions import TokenExpiredError, TokenInvalidError
from .models import AuthenticatedUser
from .validator import JWTValidator


class JWTAuthMiddleware:
    """
    Django middleware that validates a Bearer JWT on every request.

    On success: sets request.user (AuthenticatedUser) and request.auth_token_payload (dict).
    On failure or missing header: sets both to None. Does not short-circuit the request —
    authorization is the responsibility of the view or its decorators.

    Required Django setting:
        AUTH_KIT_JWKS_URI = "http://auth-service:8001/api/auth/.well-known/jwks.json"

    Optional:
        AUTH_KIT_CACHE_TTL = 3600  # seconds to cache the public key locally
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._validator: JWTValidator | None = None

    def __call__(self, request):
        request.user = None
        request.auth_token_payload = None

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = self._get_validator().validate(token)
                request.user = AuthenticatedUser(
                    id=int(payload["sub"]),
                    role=payload["role"],
                    token_jti=payload.get("jti", ""),
                )
                request.auth_token_payload = payload
            except (TokenExpiredError, TokenInvalidError):
                pass  # request.user stays None; view can decide to return 401.

        return self.get_response(request)

    def _get_validator(self) -> JWTValidator:
        if self._validator is None:
            jwks_uri = settings.AUTH_KIT_JWKS_URI
            cache_ttl = getattr(settings, "AUTH_KIT_CACHE_TTL", 3600)
            self._validator = JWTValidator(jwks_uri=jwks_uri, cache_ttl=cache_ttl)
        return self._validator


def login_required(view_func):
    """
    View decorator that returns HTTP 401 if request.user is None.
    Must be used with JWTAuthMiddleware in MIDDLEWARE.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user is None:
            return JsonResponse({"error": "Authentication required"}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


def role_required(*roles):
    """
    View decorator that returns HTTP 403 if request.user.role is not in `roles`.
    Returns HTTP 401 if request.user is None.
    Must be used with JWTAuthMiddleware in MIDDLEWARE.

    Usage:
        @role_required("admin")
        def admin_only_view(request): ...

        @role_required("admin", "operator")
        def privileged_view(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user is None:
                return JsonResponse({"error": "Authentication required"}, status=401)
            if request.user.role not in roles:
                return JsonResponse({"error": "Forbidden"}, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
