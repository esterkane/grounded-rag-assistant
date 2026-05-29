"""Unit tests for cost estimation (pure, no services)."""

from app.generation.models import TokenUsage
from app.observability.cost import estimate_cost, price_for


def test_gemini_cost_from_list_price() -> None:
    # gemini-2.0-flash: $0.0001/1k input, $0.0004/1k output.
    usage = TokenUsage(input_tokens=1000, output_tokens=1000)
    cost = estimate_cost("gemini-2.0-flash", usage)
    assert cost == 0.0001 + 0.0004


def test_unknown_model_is_free() -> None:
    assert price_for("some-unlisted-model") == (0.0, 0.0)
    assert estimate_cost("some-unlisted-model", TokenUsage(input_tokens=10_000)) == 0.0


def test_local_model_is_free() -> None:
    assert estimate_cost("llama3.1", TokenUsage(input_tokens=5000, output_tokens=5000)) == 0.0


def test_none_usage_is_zero() -> None:
    assert estimate_cost("gemini-2.0-flash", None) == 0.0


def test_token_usage_total_and_add() -> None:
    a = TokenUsage(input_tokens=3, output_tokens=4)
    b = TokenUsage(input_tokens=1, output_tokens=1)
    summed = a + b
    assert summed.input_tokens == 4
    assert summed.output_tokens == 5
    assert summed.total_tokens == 9
