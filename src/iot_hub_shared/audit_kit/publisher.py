from typing import Optional

from .record import AuditRecord 
from ..kafka_kit.producer import KafkaProducer, ProduceResult

def publish_audit_event(
    *,
    event: AuditRecord,
    producer: KafkaProducer,
) -> ProduceResult:
    """Publish audit event to Kafka."""
    return producer.produce(
        payload=event.to_record(),
        key=event.event_type,
    )