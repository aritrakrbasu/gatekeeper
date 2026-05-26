"""
Configuration module for The Gatekeeper.

Contains configuration for repositories, Arize observability, and other settings.
"""

from .arize_config import (
    init_arize,
    instrument_google_genai,
    is_arize_configured,
    get_space_id,
    get_api_key,
    is_arize_initialized,
    shutdown,
)

__all__ = [
    "init_arize",
    "instrument_google_genai",
    "is_arize_configured",
    "get_space_id",
    "get_api_key",
    "is_arize_initialized",
    "shutdown",
]
