"""
Unit tests for observability_kit.

Covers:
  - RequestContextFilter injects request_id and duration into log records
  - CeleryContextFilter injects task_id and task_name; no-ops without Celery
  - RequestLoggingMiddleware sets ContextVars and emits an access log
  - metrics_view returns 200 with correct content type
  - get_json_logging_config structure and importable filter class paths
"""

import importlib
import logging
import uuid

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from prometheus_client import CONTENT_TYPE_LATEST

from iot_hub_shared.observability_kit.context import request_duration, request_id
from iot_hub_shared.observability_kit.filters import CeleryContextFilter, RequestContextFilter
from iot_hub_shared.observability_kit.logging import get_json_logging_config
from iot_hub_shared.observability_kit.metrics import metrics_view
from iot_hub_shared.observability_kit.middleware import RequestLoggingMiddleware


# ---------------------------------------------------------------------------
# RequestContextFilter
# ---------------------------------------------------------------------------

class TestRequestContextFilter:
    def test_injects_request_id_into_record(self):
        token = request_id.set('test-request-id')
        try:
            f = RequestContextFilter()
            record = logging.LogRecord('test', logging.INFO, '', 0, 'msg', (), None)
            f.filter(record)
            assert record.request_id == 'test-request-id'
        finally:
            request_id.reset(token)

    def test_injects_duration_into_record(self):
        token = request_duration.set(42.5)
        try:
            f = RequestContextFilter()
            record = logging.LogRecord('test', logging.INFO, '', 0, 'msg', (), None)
            f.filter(record)
            assert record.duration == 42.5
        finally:
            request_duration.reset(token)

    def test_filter_returns_true(self):
        f = RequestContextFilter()
        record = logging.LogRecord('test', logging.INFO, '', 0, 'msg', (), None)
        assert f.filter(record) is True

    def test_default_values_used_when_no_context_set(self):
        # Reset to defaults
        token_id = request_id.set('no-request-id')
        token_dur = request_duration.set(0.0)
        try:
            f = RequestContextFilter()
            record = logging.LogRecord('test', logging.INFO, '', 0, 'msg', (), None)
            f.filter(record)
            assert record.request_id == 'no-request-id'
            assert record.duration == 0.0
        finally:
            request_id.reset(token_id)
            request_duration.reset(token_dur)


# ---------------------------------------------------------------------------
# CeleryContextFilter
# ---------------------------------------------------------------------------

class TestCeleryContextFilter:
    def test_filter_returns_true(self):
        f = CeleryContextFilter()
        record = logging.LogRecord('test', logging.INFO, '', 0, 'msg', (), None)
        assert f.filter(record) is True

    def test_sets_task_id_and_name_to_none_outside_task(self):
        f = CeleryContextFilter()
        record = logging.LogRecord('test', logging.INFO, '', 0, 'msg', (), None)
        f.filter(record)
        assert record.task_id is None
        assert record.task_name is None

    def test_does_not_crash_when_celery_unavailable(self, mocker):
        # Simulate ImportError as if Celery were not installed
        mocker.patch.dict('sys.modules', {'celery': None})
        f = CeleryContextFilter()
        record = logging.LogRecord('test', logging.INFO, '', 0, 'msg', (), None)
        # Should not raise even though celery is unavailable
        result = f.filter(record)
        assert result is True


# ---------------------------------------------------------------------------
# RequestLoggingMiddleware
# ---------------------------------------------------------------------------

class TestRequestLoggingMiddleware:
    def _make_middleware(self, status=200):
        def get_response(request):
            return HttpResponse('OK', status=status)
        return RequestLoggingMiddleware(get_response)

    def test_response_is_returned(self):
        factory = RequestFactory()
        request = factory.get('/')
        middleware = self._make_middleware()
        response = middleware(request)
        assert response.status_code == 200

    def test_request_id_set_to_valid_uuid(self):
        factory = RequestFactory()
        request = factory.get('/')
        middleware = self._make_middleware()
        middleware(request)
        rid = request_id.get()
        # Must be a parseable UUID (not the default placeholder)
        parsed = uuid.UUID(rid)
        assert str(parsed) == rid

    def test_request_duration_set_after_response(self):
        factory = RequestFactory()
        request = factory.get('/')
        middleware = self._make_middleware()
        middleware(request)
        duration = request_duration.get()
        assert isinstance(duration, float)
        assert duration >= 0.0

    def test_access_log_emitted(self, mocker):
        factory = RequestFactory()
        request = factory.get('/health/')
        mock_log = mocker.patch(
            'iot_hub_shared.observability_kit.middleware.logger'
        )
        middleware = self._make_middleware(status=204)
        middleware(request)

        mock_log.info.assert_called_once()
        call_kwargs = mock_log.info.call_args
        extra = call_kwargs.kwargs.get('extra', {})
        assert extra.get('method') == 'GET'
        assert extra.get('path') == '/health/'
        assert extra.get('status') == 204


# ---------------------------------------------------------------------------
# metrics_view
# ---------------------------------------------------------------------------

class TestMetricsView:
    def test_returns_200(self):
        factory = RequestFactory()
        request = factory.get('/metrics/')
        response = metrics_view(request)
        assert response.status_code == 200

    def test_content_type_is_prometheus(self):
        factory = RequestFactory()
        request = factory.get('/metrics/')
        response = metrics_view(request)
        assert response['Content-Type'] == CONTENT_TYPE_LATEST


# ---------------------------------------------------------------------------
# get_json_logging_config
# ---------------------------------------------------------------------------

class TestGetJsonLoggingConfig:
    def test_returns_dict_with_required_keys(self):
        config = get_json_logging_config()
        for key in ('version', 'formatters', 'filters', 'handlers', 'loggers'):
            assert key in config

    def test_version_is_1(self):
        config = get_json_logging_config()
        assert config['version'] == 1

    def test_django_level_applied(self):
        config = get_json_logging_config(django_level='WARNING')
        assert config['loggers']['django']['level'] == 'WARNING'

    def test_celery_level_applied(self):
        config = get_json_logging_config(celery_level='DEBUG')
        assert config['loggers']['celery']['level'] == 'DEBUG'

    def test_filter_class_paths_are_importable(self):
        config = get_json_logging_config()
        for filter_name, filter_cfg in config['filters'].items():
            dotted_path = filter_cfg['()']
            module_path, class_name = dotted_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            assert hasattr(module, class_name), (
                f"Filter '{filter_name}' class '{class_name}' not found in '{module_path}'"
            )

    def test_filter_paths_use_correct_package_name(self):
        config = get_json_logging_config()
        for filter_cfg in config['filters'].values():
            assert filter_cfg['()'].startswith('iot_hub_shared.'), (
                f"Filter path must start with 'iot_hub_shared.', got: {filter_cfg['()']}"
            )
