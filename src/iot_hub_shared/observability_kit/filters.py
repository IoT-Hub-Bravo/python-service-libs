import logging

from .context import request_duration, request_id


class RequestContextFilter(logging.Filter):
    """Add request context for request logging."""

    def filter(self, record):
        record.duration = request_duration.get()
        record.request_id = request_id.get()
        return True


class CeleryContextFilter(logging.Filter):
    """Add Celery task context for logging.

    Celery is an optional dependency. This filter silently no-ops when Celery
    is not installed, so services that only use Django (without Celery) can
    still safely include this filter in their logging config.
    """

    def filter(self, record):
        record.task_id = None
        record.task_name = None

        try:
            from celery import current_task  # noqa: PLC0415
        except ImportError:
            return True

        if current_task and current_task.request:
            record.task_id = current_task.request.id
            record.task_name = current_task.name

        return True