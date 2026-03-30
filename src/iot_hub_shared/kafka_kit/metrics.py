from prometheus_client import Counter, Histogram

kafka_messages_total = Counter(
    'kafka_consumer_messages_total',
    'Total number of messages received from Kafka',
    ['topic', 'status'],
)

kafka_latency_seconds = Histogram(
    'kafka_consumer_latency_seconds',
    'Time to process incoming Kafka message (seconds)',
    ['topic'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

kafka_errors_total = Counter(
    'kafka_consumer_errors_total',
    'Total number of Kafka consumer errors',
    ['topic', 'error_type'],
)