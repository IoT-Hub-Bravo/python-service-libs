from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedUser:
    """
    Represents a verified JWT principal. Set on request.user by JWTAuthMiddleware.

    This is NOT a Django ORM model — it is a plain immutable dataclass.
    It carries only the claims extracted from the token; no DB lookup is performed.
    """

    id: int        # JWT "sub" claim — cast to int (matches AutoField/BigAutoField PKs)
    role: str      # JWT "role" claim — e.g. "admin" or "client"
    token_jti: str  # JWT "jti" claim — unique token ID for audit trails
