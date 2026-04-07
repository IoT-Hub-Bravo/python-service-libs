# iot-hub-shared

Shared Python infrastructure library for IoT Hub microservices.

This library provides **service-agnostic technical building blocks** — Kafka abstractions,
structured logging, Prometheus metrics, audit event contracts, and reusable serializer
base classes — so that each microservice can focus exclusively on its own domain logic.

---

## Table of Contents

- [Packages](#packages)
- [Architectural Boundaries](#architectural-boundaries)
- [Versioning and Release Process](#versioning-and-release-process)
- [Installation](#installation)
- [Usage Examples](#usage-examples)
- [auth_kit](#auth_kit)
- [Runnable Examples Directory](#runnable-examples-directory)
- [Running the Library's Own Tests](#running-the-librarys-own-tests)
- [Test Kit — Fixtures for Downstream Services](#test-kit--fixtures-for-downstream-services)

---

## Packages

| Package | Description |
|---|---|
| `kafka_kit` | `KafkaProducer` and `KafkaConsumer` wrappers around `confluent-kafka` |
| `observability_kit` | JSON structured logging, Prometheus metrics view, request-context middleware |
| `audit_kit` | `AuditRecord` Kafka event contract and `publish_audit_event` helper |
| `auth_kit` | RS256 JWT validation middleware, `login_required`/`role_required` decorators, JWKS caching |
| `serializer_kit` | Framework-agnostic `BaseSerializer`, `JSONSerializer`, and `BaseValidator` |
| `utils_kit` | Generic dict, JSON, and datetime normalization utilities |
| `test_kit` | pytest plugin with `FakeKafkaProducer`, `audit_record_factory`, and Prometheus fixtures |

---

## Architectural Boundaries

This is the most important section. All contributors must read it before opening a pull request.

### What belongs here

- **Service-agnostic technical abstractions** — Kafka I/O wrappers, structured log formatters,
  Prometheus metric helpers, serializer base classes, generic data-normalisation utilities.
- **Shared cross-service event contracts** — schemas that define the *shape* of a Kafka message
  (e.g. `AuditRecord`). The contract lives here; the persistence of consumed events belongs in
  each consuming service.

### What is strictly forbidden

| Category | Example | Why |
|---|---|---|
| ORM / database models | `class AuditLog(models.Model)` | Violates the **Database-per-Service** principle. Shared DB models create hidden schema coupling between services and make independent deploys impossible. Every service must own its own data store. |
| Domain / business logic | Rule evaluation, telemetry validation, device registry lookups | Domain logic belongs in the service that owns the domain. Placing it here creates a distributed monolith. |
| Framework-coupled response objects | `JsonResponse`, `Response` (DRF) | These tie consumers to a specific web framework and import path. |
| Service-specific configuration | Hardcoded topic names, environment-specific URLs | Configuration belongs in each service's own settings or environment variables. |
| Concrete ORM serializers | `ModelSerializer` subclasses | These serialise ORM rows — a domain concern, not a shared technical building block. |

> **The litmus test:** "If I removed this from the shared library and put it in a single
> service, would any *other* service break?" If the answer is no, it does not belong here.

---

## Versioning and Release Process

This library follows **Semantic Versioning** ([SemVer](https://semver.org)):
`MAJOR.MINOR.PATCH`.

| Increment | When |
|---|---|
| `PATCH` | Backwards-compatible bug fixes |
| `MINOR` | New backwards-compatible features |
| `MAJOR` | Breaking changes to any public API |

### Cutting a release

```bash
# 1. Bump the version in pyproject.toml
#    [project]
#    version = "0.3.0"

# 2. Commit the version bump
git add pyproject.toml
git commit -m "chore: bump version to 0.3.0"

# 3. Tag the release
git tag v0.3.0

# 4. Push the commit and the tag
git push origin main
git push origin v0.3.0
```

Downstream services pin to a specific tag. There is no PyPI publication — distribution
is done entirely via the Git URL.

---

## Installation

### Production and CI — downstream services

Install directly from the Git repository using a version tag.

**Core (no optional framework extras):**

```bash
pip install "iot-hub-shared @ git+https://github.com/IoT-Hub-Bravo/python-service-libs.git@v0.2.0"
```

**With Django support** (enables `observability_kit` middleware and metrics view):

```bash
pip install "iot-hub-shared[django] @ git+https://github.com/IoT-Hub-Bravo/python-service-libs.git@v0.2.0"
```

**With Celery support** (enables `CeleryPayloadHandler` and Celery logging config):

```bash
pip install "iot-hub-shared[celery] @ git+https://github.com/IoT-Hub-Bravo/python-service-libs.git@v0.2.0"
```

**With both Django and Celery:**

```bash
pip install "iot-hub-shared[django,celery] @ git+https://github.com/IoT-Hub-Bravo/python-service-libs.git@v0.2.0"
```

In `pyproject.toml` of a consuming service:

```toml
[project]
dependencies = [
    "iot-hub-shared[django,celery] @ git+https://github.com/IoT-Hub-Bravo/python-service-libs.git@v0.2.0",
]
```

In `requirements.txt`:

```text
iot-hub-shared[django,celery] @ git+https://github.com/IoT-Hub-Bravo/python-service-libs.git@v0.2.0
```

### Local development — working on this library

```bash
git clone https://github.com/IoT-Hub-Bravo/python-service-libs.git
cd iot-hub-shared
pip install -e ".[dev]"
pytest
```

### Local development — working on a microservice while modifying this library simultaneously

Mount the library into the consuming service's container as an editable install.
In the consuming service's `docker-compose.yml`:

```yaml
services:
  api:
    build: .
    volumes:
      # Mount the local iot-hub-shared checkout into the container
      - ../iot-hub-shared:/packages/iot-hub-shared
    environment:
      - PYTHONPATH=/packages
```

In the consuming service's `Dockerfile` (or entrypoint), install the mounted copy as editable:

```dockerfile
RUN pip install -e /packages/iot-hub-shared
```

Any changes made to the local `iot-hub-shared` source are reflected immediately inside the
container without a rebuild.

---

## Usage Examples

### Kafka producer and audit event

```python
from iot_hub_shared.kafka_kit.producer import KafkaProducer
from iot_hub_shared.kafka_kit.config import ProducerConfig
from iot_hub_shared.audit_kit import AuditRecord, AuditActor, AuditEntity, AuditSeverity
from iot_hub_shared.audit_kit.publisher import publish_audit_event

# Build the producer (typically a module-level singleton)
producer = KafkaProducer(
    config=ProducerConfig(),   # reads KAFKA_BOOTSTRAP_SERVERS etc. from env
    topic='audit.records',
)

# Build an audit record — pure Python, no ORM required
record = AuditRecord(
    actor=AuditActor.user(request.user.id),
    entity=AuditEntity(type='Device', id=str(device.id)),
    event_type='device.CREATED',
    severity=AuditSeverity.INFO,
    details={'name': device.name},
)

# Publish to Kafka
result = publish_audit_event(event=record, producer=producer)
```

### Kafka consumer with a Celery task handler

```python
from iot_hub_shared.kafka_kit.consumer import KafkaConsumer
from iot_hub_shared.kafka_kit.config import ConsumerConfig
from iot_hub_shared.kafka_kit.handlers import CeleryPayloadHandler

from myservice.tasks import process_device_event  # your Celery task

consumer = KafkaConsumer(
    config=ConsumerConfig(),   # reads KAFKA_BOOTSTRAP_SERVERS, KAFKA_GROUP_ID from env
    topics=['device.events'],
    handler=CeleryPayloadHandler(process_device_event),
    decode_json=True,
)

consumer.start()  # blocking; wire up SIGTERM via consumer.stop()
```

### Observability — Django settings

```python
# settings.py
from iot_hub_shared.observability_kit import get_json_logging_config

LOGGING = get_json_logging_config(
    django_level='INFO',
    celery_level='WARNING',
    include_django=True,
    include_celery=True,   # set False for services without Celery
)

MIDDLEWARE = [
    # Assigns a UUID request_id and records duration in ContextVar for every request
    'iot_hub_shared.observability_kit.middleware.RequestLoggingMiddleware',
    ...
]
```

Expose the Prometheus metrics endpoint:

```python
# urls.py
from iot_hub_shared.observability_kit.metrics import metrics_view

urlpatterns = [
    path('metrics/', metrics_view),
    ...
]
```

### Serializer base classes

```python
from iot_hub_shared.serializer_kit import JSONSerializer

class DeviceCreateSerializer(JSONSerializer):
    REQUIRED_FIELDS = {'name': str, 'type': str}
    OPTIONAL_FIELDS = {'description': str}
    STRICT_SCHEMA = True   # reject unknown fields

s = DeviceCreateSerializer(request.data)
if not s.is_valid():
    return JsonResponse(s.errors, status=400)

data = s.validated_data  # {'name': '...', 'type': '...'}
```

---

## auth_kit

`auth_kit` provides Zero Trust JWT authentication for Django microservices.
Services validate RS256 tokens locally using the public key fetched from the
auth-service JWKS endpoint — no synchronous call to auth-service on the hot path.

The public key is cached in-process for a configurable TTL and automatically
re-fetched on cache expiry or unknown `kid` (transparent key rotation support).

### Installation

Add the `auth_kit` extra to the library pin in your service's `requirements.txt`:

```text
iot-hub-shared[auth_kit] @ git+https://github.com/IoT-Hub-Bravo/python-service-libs.git@v0.3.0
```

Or in `pyproject.toml`:

```toml
[project]
dependencies = [
    "iot-hub-shared[auth_kit] @ git+https://github.com/IoT-Hub-Bravo/python-service-libs.git@v0.3.0",
]
```

This pulls in `PyJWT>=2.8.0` and `cryptography>=42.0.0` as additional dependencies.

### Configuration

Add the following settings to your service's `settings.py`:

```python
# Required — the JWKS endpoint exposed by auth-service.
AUTH_KIT_JWKS_URI = "http://auth-service:8001/api/auth/.well-known/jwks.json"

# Optional — seconds to cache the public key in-process (default: 3600).
AUTH_KIT_CACHE_TTL = 3600
```

### Middleware Setup

Add `JWTAuthMiddleware` to `MIDDLEWARE` in your service's `settings.py`.
It must come **after** Django's `SecurityMiddleware` and **before** any view
middleware that needs to read `request.user`:

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "iot_hub_shared.auth_kit.middleware.JWTAuthMiddleware",  # <-- add here
    "django.middleware.common.CommonMiddleware",
    ...
]
```

The middleware runs on every request:

- **Valid Bearer token** → sets `request.user` (`AuthenticatedUser`) and `request.auth_token_payload` (the full decoded JWT dict).
- **Missing, invalid, or expired token** → sets both to `None`. The request is **not** short-circuited; authorization is the responsibility of the view or its decorators.

### Usage in Views

#### Protecting a view with `@login_required`

Returns `HTTP 401` if no valid token was presented.

```python
from iot_hub_shared.auth_kit.middleware import login_required

@login_required
def my_view(request):
    # request.user is guaranteed to be an AuthenticatedUser here.
    user_id = request.user.id          # int — JWT "sub" cast to int (matches AutoField/BigAutoField PKs)
    role    = request.user.role        # str — e.g. "admin" or "client"
    jti     = request.user.token_jti   # str — unique token ID (for revocation checks)
    ...
```

#### Restricting a view to specific roles with `@role_required`

Returns `HTTP 401` if no valid token was presented, `HTTP 403` if the role is not allowed.

```python
from iot_hub_shared.auth_kit.middleware import role_required

# Single role
@role_required("admin")
def admin_only_view(request):
    ...

# Multiple allowed roles
@role_required("admin", "operator")
def privileged_view(request):
    ...
```

#### Accessing the full token payload

`request.auth_token_payload` contains the raw decoded JWT dict, useful when you
need claims beyond `sub` and `role`:

```python
@login_required
def my_view(request):
    payload = request.auth_token_payload
    issued_at = payload["iat"]
    expires_at = payload["exp"]
    ...
```

#### Manual validation (outside a Django view)

If you need to validate a token outside of the middleware — for example in a
Celery task, a WebSocket consumer, or a management command — use `JWTValidator`
directly:

```python
from iot_hub_shared.auth_kit.validator import JWTValidator
from iot_hub_shared.auth_kit.exceptions import TokenExpiredError, TokenInvalidError

validator = JWTValidator(
    jwks_uri="http://auth-service:8001/api/auth/.well-known/jwks.json",
    cache_ttl=3600,
)

try:
    payload = validator.validate(token)
except TokenExpiredError:
    # Token was valid but has expired.
    ...
except TokenInvalidError:
    # Token is malformed, signature is invalid, or JWKS could not be fetched.
    ...
```

`JWTValidator` is thread-safe and intended to be used as a long-lived singleton.

### Testing

`test_kit.auth` provides helpers for writing JWT-related tests without running
a real auth-service. Import them explicitly in your service's `conftest.py`
(they are not auto-registered to avoid requiring optional dependencies in
services that do not use `auth_kit`):

```python
# conftest.py
from iot_hub_shared.test_kit.auth import auth_kit_rsa_key_pair, auth_kit_jwt_factory
```

| Helper | Type | Description |
|---|---|---|
| `make_test_rsa_key_pair()` | function | Generates a throwaway 2048-bit RSA key pair in memory. Returns `(private_pem, public_pem)`. |
| `make_test_jwt(payload, private_key, *, kid)` | function | Signs a JWT with RS256 using the given PEM private key. |
| `mock_jwks_server(public_pem, *, kid)` | context manager | Patches `JWTValidator._fetch_jwks` to return a JWKS built from the given public key. No HTTP calls are made. |
| `auth_kit_rsa_key_pair` | session fixture | Session-scoped key pair — generated once per test run. Returns `(private_pem, public_pem)`. |
| `auth_kit_jwt_factory` | function fixture | Returns a callable that builds signed JWTs with sane `iat`, `exp`, and `jti` defaults. |

#### Example: testing a view that requires authentication

```python
from iot_hub_shared.test_kit.auth import (
    auth_kit_rsa_key_pair,
    auth_kit_jwt_factory,
    make_test_jwt,
    make_test_rsa_key_pair,
    mock_jwks_server,
)
from iot_hub_shared.auth_kit.validator import JWTValidator


def test_admin_view_returns_200_for_admin_role(client):
    private_pem, public_pem = make_test_rsa_key_pair()
    token = make_test_jwt(
        {"sub": "user-1", "role": "admin", "jti": "abc"},
        private_pem,
    )

    with mock_jwks_server(public_pem):
        response = client.get(
            "/api/admin/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    assert response.status_code == 200


def test_admin_view_returns_403_for_client_role(client):
    private_pem, public_pem = make_test_rsa_key_pair()
    token = make_test_jwt(
        {"sub": "user-2", "role": "client", "jti": "xyz"},
        private_pem,
    )

    with mock_jwks_server(public_pem):
        response = client.get(
            "/api/admin/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    assert response.status_code == 403
```

#### Example: using the pytest fixtures

```python
# After importing auth_kit_rsa_key_pair and auth_kit_jwt_factory in conftest.py:

def test_something_with_fixture(auth_kit_jwt_factory, auth_kit_rsa_key_pair):
    _, public_pem = auth_kit_rsa_key_pair
    token = auth_kit_jwt_factory({"sub": "user-1", "role": "admin"})

    with mock_jwks_server(public_pem):
        response = client.get("/api/protected/", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 200
```

---

## Runnable Examples Directory

The [`examples/`](examples/) folder contains standalone Python scripts that
demonstrate each kit end-to-end. They require no web server, no database, and
no live Kafka broker — every example runs in-process with fakes or stdlib.

| Script | What it demonstrates |
|---|---|
| [`examples/demo_audit_and_kafka.py`](examples/demo_audit_and_kafka.py) | Building an `AuditRecord`, serialising it with `to_record()`, publishing via `FakeKafkaProducer`, and simulating broker failures |
| [`examples/demo_observability.py`](examples/demo_observability.py) | Generating a JSON logging config, setting `request_id`/`request_duration` ContextVars mid-request, and using `CeleryContextFilter` outside a task |
| [`examples/demo_serializers.py`](examples/demo_serializers.py) | Subclassing `JSONSerializer` with strict/flexible schemas, overriding `_validate_fields` for domain rules, and using `BaseValidator` standalone |
| [`examples/demo_utils.py`](examples/demo_utils.py) | `normalize_str`, `to_iso8601_utc`, `parse_iso8601_utc`, `normalize_schema`, and `diff_dicts` with annotated output |
| [`examples/test_demo_fixtures.py`](examples/test_demo_fixtures.py) | pytest plugin fixtures (`fake_kafka_producer`, `audit_record_factory`, `reset_prometheus_registry`) injected automatically — no imports needed |

Install the library first (local dev mode), then run any script directly:

```bash
pip install -e ".[dev]"

# Plain Python scripts (no pytest required)
python examples/demo_audit_and_kafka.py
python examples/demo_observability.py
python examples/demo_serializers.py
python examples/demo_utils.py

# pytest plugin demo — must be run with pytest
pytest -v examples/test_demo_fixtures.py
```

The plain Python scripts print step-by-step output and exit `0` on success.
`test_demo_fixtures.py` proves the `pytest11` entry point is working: fixtures
are injected by name with no import statements in the file itself.

---

## Running the Library's Own Tests

```bash
pip install -e ".[dev]"
pytest                          # full suite
pytest tests/test_kafka_kit.py -v      # single module
pytest tests/test_audit_kit.py -v
```

All tests run without a database or a live Kafka broker.
Django is configured automatically via `pytest_configure` in `tests/conftest.py`
(minimal in-memory settings, no `INSTALLED_APPS`).

---

## Test Kit — Fixtures for Downstream Services

`test_kit` is a pytest plugin distributed with this library. It is activated
**automatically** when `iot-hub-shared` is installed (via the `pytest11` entry point).

To activate it explicitly instead, add this to your service's root `conftest.py`:

```python
pytest_plugins = ['iot_hub_shared.test_kit.conftest']
```

### Available fixtures

| Fixture | Scope | Description |
|---|---|---|
| `fake_kafka_producer` | function | In-memory `FakeKafkaProducer`; captures produced messages in `.messages` |
| `audit_record_factory` | function | Callable factory for `AuditRecord` instances with overridable defaults |
| `reset_prometheus_registry` | function | Unregisters Prometheus collectors created during the test; prevents duplicate-timeseries errors across tests |

### Example: testing a service that publishes audit events

```python
from iot_hub_shared.audit_kit.publisher import publish_audit_event
from iot_hub_shared.kafka_kit.producer import ProduceResult


def test_publish_sends_correct_payload(fake_kafka_producer, audit_record_factory):
    record = audit_record_factory(event_type='device.CREATED', details={'id': 1})

    result = publish_audit_event(event=record, producer=fake_kafka_producer)

    assert result == ProduceResult.ENQUEUED
    assert len(fake_kafka_producer.messages) == 1
    msg = fake_kafka_producer.messages[0]
    assert msg['payload']['event_type'] == 'device.CREATED'
    assert msg['key'] == 'device.CREATED'
```

### Example: testing with Prometheus metrics

```python
from prometheus_client import Counter


def test_counter_increments(reset_prometheus_registry):
    c = Counter('my_service_ops_total', 'Total ops', ['status'])
    c.labels(status='ok').inc()
    assert c.labels(status='ok')._value.get() == 1.0
    # counter is unregistered automatically after the test
```

### Example: simulating Kafka producer failures

`FakeKafkaProducer` exposes `force_result()` to simulate infrastructure errors
without connecting to a real broker:

```python
from iot_hub_shared.kafka_kit.producer import ProduceResult
from iot_hub_shared.test_kit.kafka import FakeKafkaProducer


def test_service_handles_buffer_full_gracefully():
    producer = FakeKafkaProducer(topic='audit.records')
    producer.force_result(ProduceResult.BUFFER_FULL)

    result = my_service.publish_event(producer=producer)

    assert result == ProduceResult.BUFFER_FULL
    assert producer.messages == []   # nothing was enqueued
```
