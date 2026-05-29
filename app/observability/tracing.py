"""OpenTelemetry tracing setup.

``configure_tracing`` installs a global ``TracerProvider`` so spans opened in the
retrieval and generation core (via ``opentelemetry.trace.get_tracer``) are
exported. The default exporter prints to the console; set
``OTEL_EXPORTER_OTLP_ENDPOINT`` (e.g. the Jaeger OTLP/HTTP port) to ship spans
there instead.

The core modules only use the OpenTelemetry **API**, which is a no-op until this
function runs — so importing or unit-testing them needs no tracing setup and no
FastAPI.
"""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)

from app.config import Settings

logger = logging.getLogger(__name__)

# Marks our own provider so configure_tracing is idempotent across reloads.
_CONFIGURED_FLAG = "_grounded_rag_configured"


def _build_exporter(settings: Settings) -> SpanExporter:
    endpoint = settings.otel_exporter_otlp_endpoint.strip()
    if endpoint:
        # Imported lazily so the OTLP exporter dependency is only needed when used.
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        traces_url = endpoint.rstrip("/") + "/v1/traces"
        logger.info("Exporting traces via OTLP to %s", traces_url)
        return OTLPSpanExporter(endpoint=traces_url)
    logger.info("Exporting traces to the console")
    return ConsoleSpanExporter()


def configure_tracing(settings: Settings) -> None:
    """Install a global TracerProvider (idempotent). No-op if traces disabled."""
    if not settings.otel_traces_enabled:
        return

    current = trace.get_tracer_provider()
    if getattr(current, _CONFIGURED_FLAG, False):
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )
    provider.add_span_processor(BatchSpanProcessor(_build_exporter(settings)))
    setattr(provider, _CONFIGURED_FLAG, True)
    trace.set_tracer_provider(provider)
