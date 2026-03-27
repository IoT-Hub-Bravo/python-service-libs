"""
Unit tests for kafka_kit — all Kafka I/O is mocked.

Covers:
  - KafkaProducer.produce() result variants
  - KafkaProducer._encode_key() encoding logic
  - KafkaConsumer._is_valid_message() guard
  - KafkaConsumer._decode_message() JSON decoding
  - KafkaConsumer._handle_payload() metric instrumentation (post F-01/F-02 fix)
  - KafkaConsumer._get_message_payload() decode-error metric (post F-02 fix)
  - CeleryPayloadHandler.handle() task dispatch
  - FakeKafkaProducer behaviour (test_kit self-test)
"""

from unittest.mock import MagicMock, call

import pytest

from iot_hub_shared.kafka_kit.config import ConsumerConfig, ProducerConfig
from iot_hub_shared.kafka_kit.consumer import KafkaConsumer
from iot_hub_shared.kafka_kit.handlers import CeleryPayloadHandler
from iot_hub_shared.kafka_kit.metrics import (
    kafka_errors_total,
    kafka_latency_seconds,
    kafka_messages_total,
)
from iot_hub_shared.kafka_kit.producer import KafkaProducer, ProduceResult
from iot_hub_shared.test_kit.kafka import FakeKafkaProducer


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_confluent_producer(mocker):
    return mocker.patch('iot_hub_shared.kafka_kit.producer.Producer')


@pytest.fixture
def mock_confluent_consumer(mocker):
    return mocker.patch('iot_hub_shared.kafka_kit.consumer.Consumer')


@pytest.fixture
def producer(mock_confluent_producer):
    return KafkaProducer(config=ProducerConfig(), topic='test-topic')


@pytest.fixture
def consumer(mock_confluent_consumer):
    handler = MagicMock()
    cfg = ConsumerConfig()
    c = KafkaConsumer(config=cfg, topics=['test-topic'], handler=handler)
    return c, handler


def _make_message(value=b'{}', topic='test-topic', error=None):
    """Build a minimal mock Message."""
    msg = MagicMock()
    msg.value.return_value = value
    msg.topic.return_value = topic
    msg.error.return_value = error
    msg.offset.return_value = 0
    return msg


# ---------------------------------------------------------------------------
# KafkaProducer.produce()
# ---------------------------------------------------------------------------

class TestKafkaProducerProduce:
    def test_enqueued_on_success(self, producer, mock_confluent_producer):
        result = producer.produce({'event': 'test'})
        assert result == ProduceResult.ENQUEUED

    def test_serialization_failed_for_bad_payload(self, producer):
        result = producer.produce({1, 2, 3})  # sets are not JSON-serializable
        assert result == ProduceResult.SERIALIZATION_FAILED

    def test_buffer_full_on_buffer_error(self, producer, mock_confluent_producer):
        mock_confluent_producer.return_value.produce.side_effect = BufferError
        result = producer.produce({'event': 'test'})
        assert result == ProduceResult.BUFFER_FULL

    def test_producer_error_on_kafka_exception(self, producer, mock_confluent_producer):
        from confluent_kafka import KafkaException
        mock_confluent_producer.return_value.produce.side_effect = KafkaException
        result = producer.produce({'event': 'test'})
        assert result == ProduceResult.PRODUCER_ERROR

    def test_poll_called_after_produce(self, producer, mock_confluent_producer):
        producer.produce({'x': 1})
        mock_confluent_producer.return_value.poll.assert_called()


# ---------------------------------------------------------------------------
# KafkaProducer._encode_key()
# ---------------------------------------------------------------------------

class TestEncodeKey:
    def test_none_returns_none(self):
        assert KafkaProducer._encode_key(None) is None

    def test_bytes_returned_as_is(self):
        assert KafkaProducer._encode_key(b'raw') == b'raw'

    def test_string_encoded_to_utf8(self):
        assert KafkaProducer._encode_key('hello') == b'hello'

    def test_empty_string_returns_none(self):
        assert KafkaProducer._encode_key('') is None

    def test_whitespace_string_returns_none(self):
        assert KafkaProducer._encode_key('   ') is None

    def test_int_converted_to_bytes(self):
        assert KafkaProducer._encode_key(42) == b'42'


# ---------------------------------------------------------------------------
# KafkaConsumer._is_valid_message()
# ---------------------------------------------------------------------------

class TestIsValidMessage:
    def test_none_message_is_invalid(self):
        assert KafkaConsumer._is_valid_message(None) is False

    def test_message_with_error_is_invalid(self):
        msg = _make_message(error=MagicMock())
        assert KafkaConsumer._is_valid_message(msg) is False

    def test_valid_message_is_valid(self):
        msg = _make_message()
        msg.error.return_value = None
        assert KafkaConsumer._is_valid_message(msg) is True


# ---------------------------------------------------------------------------
# KafkaConsumer._decode_message()
# ---------------------------------------------------------------------------

class TestDecodeMessage:
    def test_valid_json_decoded(self):
        msg = _make_message(value=b'{"key": "value"}')
        result = KafkaConsumer._decode_message(msg)
        assert result == {'key': 'value'}

    def test_none_value_returns_none(self):
        msg = _make_message(value=None)
        result = KafkaConsumer._decode_message(msg)
        assert result is None

    def test_invalid_utf8_returns_none(self):
        msg = _make_message(value=b'\xff\xfe invalid')
        result = KafkaConsumer._decode_message(msg)
        assert result is None

    def test_invalid_json_returns_none(self):
        msg = _make_message(value=b'not-json')
        result = KafkaConsumer._decode_message(msg)
        assert result is None

    def test_json_array_decoded(self):
        msg = _make_message(value=b'[1, 2, 3]')
        result = KafkaConsumer._decode_message(msg)
        assert result == [1, 2, 3]


# ---------------------------------------------------------------------------
# KafkaConsumer._handle_payload() — metrics instrumentation (F-01 fix)
# ---------------------------------------------------------------------------

class TestHandlePayloadMetrics:
    def test_success_increments_messages_total(self, consumer, mocker):
        c, handler = consumer
        mock_labels = mocker.patch.object(kafka_messages_total, 'labels')

        c._handle_payload({'data': 1}, 'test-topic')

        mock_labels.assert_called_once_with(topic='test-topic', status='success')
        mock_labels.return_value.inc.assert_called_once()

    def test_success_observes_latency(self, consumer, mocker):
        c, handler = consumer
        mock_labels = mocker.patch.object(kafka_latency_seconds, 'labels')

        c._handle_payload({'data': 1}, 'test-topic')

        mock_labels.assert_called_once_with(topic='test-topic')
        mock_labels.return_value.observe.assert_called_once()

    def test_handler_exception_increments_errors_total(self, consumer, mocker):
        c, handler = consumer
        handler.handle.side_effect = RuntimeError('boom')
        mock_labels = mocker.patch.object(kafka_errors_total, 'labels')

        result = c._handle_payload({'data': 1}, 'test-topic')

        assert result is False
        mock_labels.assert_called_once_with(topic='test-topic', error_type='handler_error')
        mock_labels.return_value.inc.assert_called_once()

    def test_handler_exception_still_observes_latency(self, consumer, mocker):
        c, handler = consumer
        handler.handle.side_effect = RuntimeError('boom')
        mocker.patch.object(kafka_errors_total, 'labels')
        mock_latency = mocker.patch.object(kafka_latency_seconds, 'labels')

        c._handle_payload({}, 'test-topic')

        mock_latency.return_value.observe.assert_called_once()


# ---------------------------------------------------------------------------
# KafkaConsumer._get_message_payload() — decode error metric (F-02 fix)
# ---------------------------------------------------------------------------

class TestGetMessagePayloadMetrics:
    def test_decode_failure_increments_errors_total(self, consumer, mocker):
        c, _ = consumer
        c._decode_json = True
        msg = _make_message(value=b'not-json', topic='test-topic')
        mock_labels = mocker.patch.object(kafka_errors_total, 'labels')

        result = c._get_message_payload(msg)

        assert result is None
        mock_labels.assert_called_once_with(topic='test-topic', error_type='decode_error')
        mock_labels.return_value.inc.assert_called_once()

    def test_valid_payload_does_not_increment_errors(self, consumer, mocker):
        c, _ = consumer
        c._decode_json = True
        msg = _make_message(value=b'{"ok": true}', topic='test-topic')
        mock_labels = mocker.patch.object(kafka_errors_total, 'labels')

        result = c._get_message_payload(msg)

        assert result == {'ok': True}
        mock_labels.assert_not_called()


# ---------------------------------------------------------------------------
# CeleryPayloadHandler
# ---------------------------------------------------------------------------

class TestCeleryPayloadHandler:
    def test_handle_calls_task_delay(self):
        task = MagicMock()
        handler = CeleryPayloadHandler(task)
        handler.handle({'key': 'value'})
        task.delay.assert_called_once_with({'key': 'value'})


# ---------------------------------------------------------------------------
# FakeKafkaProducer (test_kit self-test)
# ---------------------------------------------------------------------------

class TestFakeKafkaProducer:
    def test_produce_returns_enqueued(self):
        p = FakeKafkaProducer()
        assert p.produce({'x': 1}) == ProduceResult.ENQUEUED

    def test_produce_captures_message(self):
        p = FakeKafkaProducer(topic='events')
        p.produce({'event': 'CREATED'}, key='entity')
        assert len(p.messages) == 1
        assert p.messages[0]['topic'] == 'events'
        assert p.messages[0]['key'] == 'entity'
        assert p.messages[0]['payload'] == {'event': 'CREATED'}

    def test_produce_unserializable_returns_serialization_failed(self):
        p = FakeKafkaProducer()
        assert p.produce({1, 2, 3}) == ProduceResult.SERIALIZATION_FAILED
        assert p.messages == []

    def test_force_result_overrides_outcome(self):
        p = FakeKafkaProducer()
        p.force_result(ProduceResult.BUFFER_FULL)
        assert p.produce({'x': 1}) == ProduceResult.BUFFER_FULL
        assert p.messages == []

    def test_reset_clears_messages_and_forced_result(self):
        p = FakeKafkaProducer()
        p.produce({'x': 1})
        p.force_result(ProduceResult.PRODUCER_ERROR)
        p.reset()
        assert p.messages == []
        assert p.produce({'x': 1}) == ProduceResult.ENQUEUED

    def test_topic_property(self):
        p = FakeKafkaProducer(topic='my-topic')
        assert p.topic == 'my-topic'
