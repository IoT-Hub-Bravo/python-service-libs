import os
from django.http import HttpResponse
from prometheus_client import (
    CollectorRegistry,
    generate_latest,
    multiprocess,
    CONTENT_TYPE_LATEST,
)

def metrics_view(request):
    """
    Prometheus metrics endpoint with multiprocess support.
    """
    if os.environ.get('PROMETHEUS_MULTIPROC_DIR'):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        from prometheus_client import REGISTRY
        registry = REGISTRY

    data = generate_latest(registry)
    return HttpResponse(data, content_type=CONTENT_TYPE_LATEST)