"""
test_kit — reusable pytest fixtures and fakes for microservices that depend on iot-hub-shared.

Usage in a downstream service's conftest.py:
    pytest_plugins = ['iot_hub_shared.test_kit.conftest']

This makes all fixtures below available project-wide without any extra imports:
    - fake_kafka_producer       FakeKafkaProducer instance (function-scoped)
    - audit_record_factory      factory for AuditRecord instances
    - reset_prometheus_registry tears down newly registered metrics after each test
"""
