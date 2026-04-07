"""
pytest plugin entry-point for iot_hub_shared.test_kit.

Registered automatically via the pytest11 entry point in pyproject.toml.
Activating this plugin makes all test_kit fixtures available project-wide
without any per-file imports.

--- How to activate in a downstream service ---

The plugin is registered automatically when iot-hub-shared is installed.
If you prefer an explicit registration, add this to your service's root conftest.py:
    pytest_plugins = ['iot_hub_shared.test_kit.conftest']

--- Provided fixtures ---

| Fixture                   | Scope    | Description                                         |
|---------------------------|----------|-----------------------------------------------------|
| fake_kafka_producer       | function | FakeKafkaProducer — captures messages in .messages  |
| audit_record_factory      | function | Factory for AuditRecord instances                   |
| reset_prometheus_registry | function | Unregisters test-created metrics after each test    |

--- Optional auth_kit fixtures (require PyJWT + cryptography) ---

NOT auto-registered to avoid hard-requiring optional deps.
Import explicitly in your service's conftest.py:

    from iot_hub_shared.test_kit.auth import auth_kit_rsa_key_pair, auth_kit_jwt_factory

| auth_kit_rsa_key_pair     | session  | Throwaway RSA key pair (private_pem, public_pem)    |
| auth_kit_jwt_factory      | function | Callable that builds signed JWTs with sane defaults |
"""

from iot_hub_shared.test_kit.audit import audit_record_factory
from iot_hub_shared.test_kit.kafka import fake_kafka_producer
from iot_hub_shared.test_kit.prometheus import reset_prometheus_registry

__all__ = [
    'fake_kafka_producer',
    'audit_record_factory',
    'reset_prometheus_registry',
]
