"""Static LLM cost estimation.

Estimates the would-be USD cost of a generation from a small public price table,
even when the actual provider is free (gemini free tier, local ollama). This is
purely for observability — recorded on ``query_log`` and surfaced at ``/metrics``
so the project can reason about cost at scale.

Prices are USD per 1,000 tokens, from public list pricing. They are intentionally
static (no network) and approximate; update the table when prices change.
"""

from __future__ import annotations

from app.generation.models import TokenUsage

# model -> (input_usd_per_1k, output_usd_per_1k). Public list prices.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    # Gemini Flash list prices (free tier in practice; logged anyway).
    # gemini-2.0-flash is deprecated (shuts down 2026-06-01) but kept for historical rows.
    "gemini-2.5-flash": (0.0003, 0.0025),
    "gemini-2.0-flash": (0.0001, 0.0004),
    "gemini-1.5-flash": (0.000075, 0.0003),
    "gemini-1.5-pro": (0.00125, 0.005),
    # Local models cost nothing to run.
    "llama3.1": (0.0, 0.0),
}

# Used when a model is not in the table: assume free rather than guess a price.
_DEFAULT_PRICE = (0.0, 0.0)


def price_for(model: str) -> tuple[float, float]:
    """Return (input, output) USD-per-1k price for ``model`` (default free)."""
    return PRICE_TABLE.get(model, _DEFAULT_PRICE)


def estimate_cost(model: str, usage: TokenUsage | None) -> float:
    """Estimate USD cost for ``usage`` under ``model``'s list price."""
    if usage is None:
        return 0.0
    input_price, output_price = price_for(model)
    return (
        usage.input_tokens / 1000.0 * input_price
        + usage.output_tokens / 1000.0 * output_price
    )
