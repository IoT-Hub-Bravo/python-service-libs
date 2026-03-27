"""
Audit record factory fixture.

Provides:
    audit_record_factory — factory for AuditRecord domain objects.

Usage:
    def test_publish(audit_record_factory, fake_kafka_producer):
        record = audit_record_factory(event_type='device.CREATED')
        result = publish_audit_event(event=record, producer=fake_kafka_producer)
        assert result == ProduceResult.ENQUEUED
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from iot_hub_shared.audit_kit.record import (
    AuditActor,
    AuditEntity,
    AuditRecord,
    AuditSeverity,
)


@pytest.fixture
def audit_record_factory():
    """
    Return a callable factory that builds AuditRecord instances with sane defaults.

    All fields can be overridden via keyword arguments.
    """
    def _factory(
        *,
        actor: AuditActor | None = None,
        entity: AuditEntity | None = None,
        event_type: str = 'test.EVENT_CREATED',
        severity: AuditSeverity = AuditSeverity.INFO,
        details: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AuditRecord:
        return AuditRecord(
            actor=actor or AuditActor.system('test-service'),
            entity=entity or AuditEntity(type='test.Entity', id=str(uuid.uuid4())),
            event_type=event_type,
            severity=severity,
            details=details if details is not None else {},
            **kwargs,
        )

    return _factory
