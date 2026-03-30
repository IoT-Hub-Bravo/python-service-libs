import logging
import uuid
import time
from .context import request_duration, request_id

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    """Middleware to set request context for logging and track duration."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        request_id.set(str(uuid.uuid4()))

        response = self.get_response(request)

        duration_ms = round((time.time() - start_time) * 1000, 3)
        request_duration.set(duration_ms)

        logger.info(
            'request completed',
            extra={
                'method': request.method,
                'path': request.path,
                'status': response.status_code,
            },
        )

        return response