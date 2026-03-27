from typing import Any

def get_json_logging_config(
    django_level: str = 'INFO',
    celery_level: str = 'ERROR',
    include_django: bool = True,
    include_celery: bool = True,
) -> dict[str, Any]:
    """
    Returns a standardized JSON logging configuration dictionary.

    Args:
        django_level: Log level for the 'django' logger. Ignored when include_django=False.
        celery_level: Log level for the 'celery' logger. Ignored when include_celery=False.
        include_django: Include Django-specific logger and handler entries.
        include_celery: Include Celery-specific logger, handler, filter, and formatter entries.

    Usage in settings.py:
        from iot_hub_shared.observability_kit import get_json_logging_config
        LOGGING = get_json_logging_config(django_level='INFO', celery_level='WARNING')

    For non-Django/non-Celery services:
        LOGGING = get_json_logging_config(include_django=False, include_celery=False)
    """
    formatters: dict[str, Any] = {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "{asctime} {levelname} {name} {message} {request_id} {duration}",
            "style": "{",
            "rename_fields": {
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger_name",
            },
        },
    }

    filters: dict[str, Any] = {
        "request_context": {
            "()": "iot_hub_shared.observability_kit.filters.RequestContextFilter",
        },
    }

    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_context"],
            "formatter": "json",
        },
    }

    loggers: dict[str, Any] = {
        "": {
            "handlers": ["console"],
            "level": django_level,
        },
    }

    if include_celery:
        formatters["celery_json"] = {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "{asctime} {levelname} {name} {message} {task_id} {task_name}",
            "style": "{",
            "rename_fields": {
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger_name",
            },
        }
        filters["celery_context"] = {
            "()": "iot_hub_shared.observability_kit.filters.CeleryContextFilter",
        }
        handlers["celery_console"] = {
            "class": "logging.StreamHandler",
            "filters": ["celery_context"],
            "formatter": "celery_json",
        }
        loggers["celery"] = {
            "handlers": ["celery_console"],
            "level": celery_level,
            "propagate": False,
        }

    if include_django:
        loggers["django"] = {
            "handlers": ["console"],
            "level": django_level,
            "propagate": False,
        }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "filters": filters,
        "handlers": handlers,
        "loggers": loggers,
    }