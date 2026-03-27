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
- [Running the Library's Own Tests](#running-the-librarys-own-tests)
- [Test Kit — Fixtures for Downstream Services](#test-kit--fixtures-for-downstream-services)

---

## Packages

| Package | Description |
|---|---|
| `kafka_kit` | `KafkaProducer` and `KafkaConsumer` wrappers around `confluent-kafka` |
| `observability_kit` | JSON structured logging, Prometheus metrics view, request-context middleware |
| `audit_kit` | `AuditRecord` Kafka event contract and `publish_audit_event` helper |
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
pip install "iot-hub-shared @ git+https://github.com/your-org/iot-hub-shared.git@v0.2.0"
```

**With Django support** (enables `observability_kit` middleware and metrics view):

```bash
pip install "iot-hub-shared[django] @ git+https://github.com/your-org/iot-hub-shared.git@v0.2.0"
```

**With Celery support** (enables `CeleryPayloadHandler` and Celery logging config):

```bash
pip install "iot-hub-shared[celery] @ git+https://github.com/your-org/iot-hub-shared.git@v0.2.0"
```

**With both Django and Celery:**

```bash
pip install "iot-hub-shared[django,celery] @ git+https://github.com/your-org/iot-hub-shared.git@v0.2.0"
```

In `pyproject.toml` of a consuming service:

```toml
[project]
dependencies = [
    "iot-hub-shared[django,celery] @ git+https://github.com/your-org/iot-hub-shared.git@v0.2.0",
]
```

In `requirements.txt`:

```text
iot-hub-shared[django,celery] @ git+https://github.com/your-org/iot-hub-shared.git@v0.2.0
```

### Local development — working on this library

```bash
git clone https://github.com/your-org/iot-hub-shared.git
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
