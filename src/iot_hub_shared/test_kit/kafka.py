"""
Kafka fakes and fixtures for testing code that produces to Kafka.

Provides:
    FakeKafkaProducer   — in-memory drop-in for KafkaProducer.
    fake_kafka_producer — pytest fixture returning a fresh FakeKafkaProducer.

To inspect captured messages in a test, access the .messages attribute directly:
    def test_publish(fake_kafka_producer):
        service.publish(producer=fake_kafka_producer, ...)
        assert fake_kafka_producer.messages[0]['payload']['event_type'] == 'CREATED'
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from iot_hub_shared.kafka_kit.producer import ProduceResult


class FakeKafkaProducer:
    """
    In-memory KafkaProducer substitute for use in tests.

    Matches the public interface of KafkaProducer so it can be injected
    anywhere a real producer is expected without connecting to Kafka.

    Captured messages are stored as dicts with keys:
        topic   — the producer's configured topic
        key     — the raw key passed to produce()
        payload — the JSON-decoded message payload
        raw     — the JSON string that would have been sent over the wire

    Usage:
        producer = FakeKafkaProducer(topic='audit.records')
        result = producer.produce({'event': 'CREATED'}, key='entity_type')
        assert result == ProduceResult.ENQUEUED
        assert producer.messages[0]['payload'] == {'event': 'CREATED'}
    """

    def __init__(self, topic: str = 'fake-topic') -> None:
        self._topic = topic
        self.messages: list[dict[str, Any]] = []
        self._forced_result: ProduceResult | None = None

    @property
    def topic(self) -> str:
        return self._topic

    def produce(self, payload: Any, key: Any = None) -> ProduceResult:
        if self._forced_result is not None:
            return self._forced_result

        try:
            raw = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        except (TypeError, ValueError):
            return ProduceResult.SERIALIZATION_FAILED

        self.messages.append({
            'topic': self._topic,
            'key': key,
            'payload': json.loads(raw),
            'raw': raw,
        })
        return ProduceResult.ENQUEUED

    def flush(self, timeout: float = 2.0) -> None:
        pass

    def reset(self) -> None:
        """Clear captured messages and remove any forced result override."""
        self.messages.clear()
        self._forced_result = None

    def force_result(self, result: ProduceResult) -> None:
        """
        Force produce() to return a specific result on every call.

        Useful for simulating BUFFER_FULL or PRODUCER_ERROR in tests:
            producer.force_result(ProduceResult.BUFFER_FULL)
            result = service.publish(...)
            assert result == ProduceResult.BUFFER_FULL
        """
        self._forced_result = result


@pytest.fixture
def fake_kafka_producer() -> FakeKafkaProducer:
    """Return a fresh FakeKafkaProducer for the current test."""
    return FakeKafkaProducer()
