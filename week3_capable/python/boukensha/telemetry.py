import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .conversation_span_processor import ConversationSpanProcessor

_configured = False


# Looked up lazily, at call time, rather than cached in a module-level
# constant at import time. configure() below installs a brand-new
# TracerProvider the first time it runs, and it always runs after this
# module (and client.py/registry.py/agent.py) have already been imported --
# a tracer captured at import time would bind to the pre-configuration
# no-op provider, and every span created through it would be silently
# dropped.
def tracer():
    return trace.get_tracer_provider().get_tracer("boukensha")


# Configures the OpenTelemetry SDK exactly once. Must run *after* Config has
# loaded .env (see Config._load_env) -- OTLPSpanExporter() reads
# OTEL_EXPORTER_OTLP_ENDPOINT/HEADERS from the environment at construction
# time, so configuring any earlier would silently point the exporter at the
# OTLP default (localhost:4318) instead of Honeycomb.
def configure():
    global _configured
    if _configured:
        return
    _configured = True

    resource = Resource.create({SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", "boukensha")})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    provider.add_span_processor(ConversationSpanProcessor())
    trace.set_tracer_provider(provider)


def is_configured():
    return _configured


# Flushes whatever spans are still sitting in the BatchSpanProcessor's queue
# before the process exits -- without this, a short-lived run can exit
# before the processor's next scheduled export and silently drop every span
# it recorded.
def shutdown():
    if _configured:
        trace.get_tracer_provider().shutdown()
