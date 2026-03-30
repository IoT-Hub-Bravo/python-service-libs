"""
Unit tests for audit_kit — no Django, no external dependencies.

Covers:
  - AuditActorType enum values
  - AuditSeverity enum values
  - AuditActor factory methods (user, system, external)
  - AuditEntity construction
  - AuditRecord defaults and to_record() serialization
  - publish_audit_event() with FakeKafkaProducer
"""

import uuid
from datetime import datetime, timezone

import pytest

from iot_hub_shared.audit_kit.publisher import publish_audit_event
from iot_hub_shared.audit_kit.record import (
    AuditActor,
    AuditActorType,
    AuditEntity,
    AuditRecord,
    AuditSeverity,
)
from iot_hub_shared.kafka_kit.producer import ProduceResult
from iot_hub_shared.test_kit.kafka import FakeKafkaProducer


# ---------------------------------------------------------------------------
# AuditActorType
# ---------------------------------------------------------------------------

class TestAuditActorType:
    def test_user_value(self):
        assert AuditActorType.USER.value == 'user'

    def test_system_value(self):
        assert AuditActorType.SYSTEM.value == 'system'

    def test_external_value(self):
        assert AuditActorType.EXTERNAL.value == 'external'

    def test_is_str_subclass(self):
        assert isinstance(AuditActorType.USER, str)


# ---------------------------------------------------------------------------
# AuditSeverity
# ---------------------------------------------------------------------------

class TestAuditSeverity:
    def test_info_value(self):
        assert AuditSeverity.INFO.value == 'info'

    def test_warning_value(self):
        assert AuditSeverity.WARNING.value == 'warning'

    def test_error_value(self):
        assert AuditSeverity.ERROR.value == 'error'

    def test_is_str_subclass(self):
        assert isinstance(AuditSeverity.INFO, str)


# ---------------------------------------------------------------------------
# AuditActor
# ---------------------------------------------------------------------------

class TestAuditActor:
    def test_user_factory_sets_type(self):
        actor = AuditActor.user(42)
        assert actor.type == AuditActorType.USER

    def test_user_factory_converts_id_to_str(self):
        actor = AuditActor.user(42)
        assert actor.id == '42'

    def test_system_factory_sets_type(self):
        actor = AuditActor.system('ingestion-service')
        assert actor.type == AuditActorType.SYSTEM

    def test_system_factory_preserves_id(self):
        actor = AuditActor.system('ingestion-service')
        assert actor.id == 'ingestion-service'

    def test_system_factory_none_id_by_default(self):
        actor = AuditActor.system()
        assert actor.id is None

    def test_external_factory_sets_type(self):
        actor = AuditActor.external('partner-x')
        assert actor.type == AuditActorType.EXTERNAL

    def test_external_factory_preserves_id(self):
        actor = AuditActor.external('partner-x')
        assert actor.id == 'partner-x'

    def test_external_factory_none_id_by_default(self):
        actor = AuditActor.external()
        assert actor.id is None

    def test_is_frozen(self):
        actor = AuditActor.system('svc')
        with pytest.raises(AttributeError):
            actor.id = 'other'


# ---------------------------------------------------------------------------
# AuditEntity
# ---------------------------------------------------------------------------

class TestAuditEntity:
    def test_stores_type_and_id(self):
        entity = AuditEntity(type='Device', id='device-123')
        assert entity.type == 'Device'
        assert entity.id == 'device-123'

    def test_is_frozen(self):
        entity = AuditEntity(type='Rule', id='1')
        with pytest.raises(AttributeError):
            entity.id = '2'


# ---------------------------------------------------------------------------
# AuditRecord
# ---------------------------------------------------------------------------

class TestAuditRecord:
    def _make_record(self, **kwargs):
        defaults = dict(
            actor=AuditActor.system('test'),
            entity=AuditEntity(type='Device', id='d-1'),
            event_type='device.CREATED',
        )
        defaults.update(kwargs)
        return AuditRecord(**defaults)

    def test_default_severity_is_info(self):
        record = self._make_record()
        assert record.severity == AuditSeverity.INFO

    def test_default_details_is_empty_dict(self):
        record = self._make_record()
        assert record.details == {}

    def test_default_occurred_at_is_utc(self):
        record = self._make_record()
        assert record.occurred_at.tzinfo == timezone.utc

    def test_default_audit_event_id_is_uuid(self):
        record = self._make_record()
        assert isinstance(record.audit_event_id, uuid.UUID)

    def test_each_record_gets_unique_id(self):
        r1 = self._make_record()
        r2 = self._make_record()
        assert r1.audit_event_id != r2.audit_event_id

    def test_is_frozen(self):
        record = self._make_record()
        with pytest.raises(AttributeError):
            record.event_type = 'other'

    def test_custom_severity(self):
        record = self._make_record(severity=AuditSeverity.WARNING)
        assert record.severity == AuditSeverity.WARNING

    def test_custom_details(self):
        record = self._make_record(details={'key': 'value'})
        assert record.details == {'key': 'value'}


# ---------------------------------------------------------------------------
# AuditRecord.to_record()
# ---------------------------------------------------------------------------

class TestAuditRecordToRecord:
    def _make_record(self, **kwargs):
        defaults = dict(
            actor=AuditActor.user(99),
            entity=AuditEntity(type='Rule', id='rule-7'),
            event_type='rule.TRIGGERED',
        )
        defaults.update(kwargs)
        return AuditRecord(**defaults)

    def test_to_record_returns_dict(self):
        assert isinstance(self._make_record().to_record(), dict)

    def test_actor_type_serialized_as_value(self):
        record = self._make_record()
        assert record.to_record()['actor_type'] == 'user'

    def test_actor_id_included(self):
        record = self._make_record()
        assert record.to_record()['actor_id'] == '99'

    def test_entity_type_included(self):
        record = self._make_record()
        assert record.to_record()['entity_type'] == 'Rule'

    def test_entity_id_included(self):
        record = self._make_record()
        assert record.to_record()['entity_id'] == 'rule-7'

    def test_event_type_included(self):
        record = self._make_record()
        assert record.to_record()['event_type'] == 'rule.TRIGGERED'

    def test_severity_serialized_as_value(self):
        record = self._make_record(severity=AuditSeverity.ERROR)
        assert record.to_record()['severity'] == 'error'

    def test_occurred_at_is_iso_string(self):
        fixed_dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        record = self._make_record(occurred_at=fixed_dt)
        assert record.to_record()['occurred_at'] == '2024-06-01T12:00:00+00:00'

    def test_details_included(self):
        record = self._make_record(details={'threshold': 90})
        assert record.to_record()['details'] == {'threshold': 90}

    def test_audit_event_id_is_str(self):
        record = self._make_record()
        result = record.to_record()
        assert isinstance(result['audit_event_id'], str)
        # must be a valid UUID string
        uuid.UUID(result['audit_event_id'])

    def test_all_required_keys_present(self):
        result = self._make_record().to_record()
        for key in ('actor_type', 'actor_id', 'entity_type', 'entity_id',
                    'event_type', 'severity', 'occurred_at', 'details',
                    'audit_event_id'):
            assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# publish_audit_event
# ---------------------------------------------------------------------------

class TestPublishAuditEvent:
    def _record(self, event_type='device.CREATED'):
        return AuditRecord(
            actor=AuditActor.system('test-service'),
            entity=AuditEntity(type='Device', id='d-42'),
            event_type=event_type,
        )

    def test_returns_enqueued(self):
        producer = FakeKafkaProducer(topic='audit.records')
        result = publish_audit_event(event=self._record(), producer=producer)
        assert result == ProduceResult.ENQUEUED

    def test_message_captured(self):
        producer = FakeKafkaProducer(topic='audit.records')
        publish_audit_event(event=self._record(), producer=producer)
        assert len(producer.messages) == 1

    def test_key_is_event_type(self):
        producer = FakeKafkaProducer(topic='audit.records')
        publish_audit_event(event=self._record(event_type='rule.TRIGGERED'), producer=producer)
        assert producer.messages[0]['key'] == 'rule.TRIGGERED'

    def test_payload_contains_event_type(self):
        producer = FakeKafkaProducer(topic='audit.records')
        publish_audit_event(event=self._record(event_type='device.DELETED'), producer=producer)
        assert producer.messages[0]['payload']['event_type'] == 'device.DELETED'

    def test_payload_is_json_serializable(self):
        producer = FakeKafkaProducer(topic='audit.records')
        publish_audit_event(event=self._record(), producer=producer)
        # FakeKafkaProducer already round-trips through json.dumps/loads;
        # if we reach here without SERIALIZATION_FAILED, the payload is valid JSON
        assert producer.messages[0]['raw'] is not None

    def test_producer_error_propagated(self):
        producer = FakeKafkaProducer(topic='audit.records')
        producer.force_result(ProduceResult.PRODUCER_ERROR)
        result = publish_audit_event(event=self._record(), producer=producer)
        assert result == ProduceResult.PRODUCER_ERROR
        assert producer.messages == []
