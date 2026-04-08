class AuthenticationError(Exception):
    """Base class for all auth_kit errors."""


class TokenExpiredError(AuthenticationError):
    """Raised when a JWT's exp claim is in the past."""


class TokenInvalidError(AuthenticationError):
    """Raised when a JWT is malformed, has an invalid signature, or an unknown kid."""
