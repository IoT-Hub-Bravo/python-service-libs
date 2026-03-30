from contextvars import ContextVar

# Context variables for logging
request_id: ContextVar[str] = ContextVar('request_id', default='no-request-id')
request_duration: ContextVar[float] = ContextVar('request_duration', default=0.0)