"""
Gemini API pricing and cost calculation.
"""

from typing import Dict

# Gemini pricing as of 2026 (per 1M tokens)
GEMINI_PRICING = {
    "gemini-3.5-flash": {
        "input_per_million": 0.075,   # $0.075 per 1M input tokens
        "output_per_million": 0.15    # $0.15 per 1M output tokens
    },
    "gemini-3.1-pro-preview": {
        "input_per_million": 0.50,    # $0.50 per 1M input tokens
        "output_per_million": 1.50    # $1.50 per 1M output tokens
    },
    "gemini-1.5-pro": {
        "input_per_million": 1.25,    # $1.25 per 1M input tokens
        "output_per_million": 2.50    # $2.50 per 1M output tokens
    },
    "gemini-1.5-flash": {
        "input_per_million": 0.075,   # $0.075 per 1M input tokens
        "output_per_million": 0.15    # $0.15 per 1M output tokens
    }
}


async def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate cost based on Gemini pricing.

    Args:
        model_name: Model used (e.g., "gemini-3.5-flash")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Estimated cost in USD
    """
    pricing = GEMINI_PRICING.get(model_name, GEMINI_PRICING["gemini-3.5-flash"])

    input_cost = (input_tokens / 1_000_000) * pricing["input_per_million"]
    output_cost = (output_tokens / 1_000_000) * pricing["output_per_million"]

    return round(input_cost + output_cost, 6)


def get_pricing_info() -> Dict[str, Dict[str, float]]:
    """Get all pricing information."""
    return GEMINI_PRICING


def get_model_pricing(model_name: str) -> Dict[str, float]:
    """
    Get pricing for a specific model.

    Args:
        model_name: Model to get pricing for

    Returns:
        Dict with input_per_million and output_per_million pricing
    """
    return GEMINI_PRICING.get(model_name, GEMINI_PRICING["gemini-3.5-flash"])
