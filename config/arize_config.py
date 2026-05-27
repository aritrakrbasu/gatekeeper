"""
Arize AI Observability Configuration Module.

This module handles the initialization of Arize AI observability and Phoenix
for tracing, evaluation, and self-improvement capabilities.
"""

import os
import logging
from typing import Optional
from urllib.parse import urljoin

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Arize Configuration
SPACE_ID = os.getenv("ARIZE_SPACE_ID", "")
API_KEY = os.getenv("ARIZE_API_KEY", "")

# Phoenix Configuration
PHOENIX_MODE = os.getenv("PHOENIX_MODE", "cloud")  # 'cloud' or 'self-hosted'
PHOENIX_API_KEY = os.getenv("PHOENIX_API_KEY", "")
PHOENIX_BASE_URL = os.getenv("PHOENIX_BASE_URL", "https://app.phoenix.arize.com")
PHOENIX_PROJECT_NAME = os.getenv("PHOENIX_PROJECT_NAME", "gatekeeper")

# Configure Phoenix environment variables for SDK
# These are read by the Phoenix SDK for evaluation export
if PHOENIX_MODE == "cloud" and PHOENIX_API_KEY:
    os.environ["PHOENIX_API_KEY"] = PHOENIX_API_KEY
    os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = PHOENIX_BASE_URL

# Feature Flags
ENABLE_EVALUATIONS = os.getenv("ENABLE_EVALUATIONS", "true").lower() == "true"
ENABLE_SELF_IMPROVEMENT = os.getenv("ENABLE_SELF_IMPROVEMENT", "true").lower() == "true"

# Global tracer provider
tracer_provider = None
arize_initialized = False
phoenix_client = None


def is_arize_configured() -> bool:
    """Check if Arize credentials are properly configured."""
    return bool(SPACE_ID and API_KEY and SPACE_ID != "your_space_id_here" and API_KEY != "your_api_key_here")


def is_phoenix_configured() -> bool:
    """Check if Phoenix is properly configured."""
    if PHOENIX_MODE == "cloud":
        return bool(PHOENIX_API_KEY and PHOENIX_API_KEY != "your_phoenix_api_key_here")
    return True  # Self-hosted doesn't require API key


def get_phoenix_endpoint() -> str:
    """Get the Phoenix endpoint URL."""
    return PHOENIX_BASE_URL


def get_tracer_provider():
    """Get the global tracer provider instance."""
    return tracer_provider


def get_phoenix_client():
    """Get the Phoenix client instance."""
    return phoenix_client


def init_arize(
    space_id: Optional[str] = None,
    api_key: Optional[str] = None,
    project_name: str = "gatekeeper",
) -> bool:
    """
    Initialize Arize observability using the register() pattern.

    This sets up OpenTelemetry tracing with Arize as the backend.
    All instrumented LLM calls will automatically be traced.

    Args:
        space_id: Arize space ID (defaults to env var ARIZE_SPACE_ID)
        api_key: Arize API key (defaults to env var ARIZE_API_KEY)
        project_name: Project name for grouping traces in Arize

    Returns:
        True if initialization was successful, False otherwise
    """
    global tracer_provider, arize_initialized

    # Use provided keys or fall back to environment variables
    space_id = space_id or SPACE_ID
    api_key = api_key or API_KEY

    if not is_arize_configured():
        logger.warning(
            "[⚠️] Arize credentials not configured. "
            "Set ARIZE_SPACE_ID and ARIZE_API_KEY in .env to enable observability."
        )
        return False

    try:
        from arize.otel import register

        tracer_provider = register(
            space_id=space_id,
            api_key=api_key,
            project_name=project_name,
        )

        if tracer_provider:
            arize_initialized = True
            logger.info(f"[✅] Arize observability initialized for project: {project_name}")
            return True
        else:
            logger.warning("[⚠️] Arize registration returned None")
            return False

    except ImportError as e:
        logger.error(f"[x] Arize-otel package not installed: {e}")
        logger.info("[i] Install with: pip install arize-otel")
        return False
    except Exception as e:
        logger.error(f"[x] Failed to initialize Arize: {e}")
        return False


def init_phoenix_client() -> bool:
    """
    Initialize Phoenix client for evaluations and tracing.

    Returns:
        True if initialization was successful, False otherwise
    """
    global phoenix_client

    if not is_phoenix_configured():
        logger.warning("[⚠️] Phoenix not configured - skipping Phoenix client initialization")
        return False

    try:
        from phoenix.client import Client as PhoenixClient

        # Configure Phoenix client
        if PHOENIX_MODE == "cloud":
            # Phoenix Cloud
            if PHOENIX_API_KEY:
                phoenix_client = PhoenixClient(
                    base_url=PHOENIX_BASE_URL,
                    api_key=PHOENIX_API_KEY,
                )
                logger.info(f"[✅] Phoenix Cloud client initialized: {PHOENIX_BASE_URL}")
            else:
                logger.warning("[⚠️] Phoenix Cloud mode but no API key provided")
                return False
        else:
            # Self-hosted Phoenix
            phoenix_client = PhoenixClient(base_url=PHOENIX_BASE_URL)
            logger.info(f"[✅] Phoenix client initialized (self-hosted): {PHOENIX_BASE_URL}")

        return True

    except ImportError as e:
        logger.warning(f"[⚠️] Phoenix package not installed: {e}")
        logger.info("[i] Install with: pip install arize-phoenix")
        return False
    except Exception as e:
        logger.error(f"[x] Failed to initialize Phoenix client: {e}")
        return False


def instrument_google_genai() -> bool:
    """
    Instrument Google GenAI for automatic tracing.

    This must be called after init_arize() and before creating any Gemini clients.

    Returns:
        True if instrumentation was successful, False otherwise
    """
    if not arize_initialized:
        logger.warning("[⚠️] Arize not initialized - skipping Google GenAI instrumentation")
        return False

    try:
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

        GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)
        logger.info("[✅] Google GenAI instrumentor registered")
        return True

    except ImportError:
        logger.warning("[⚠️] openinference-instrumentation-google-genai not installed")
        logger.info("[i] Install with: pip install openinference-instrumentation-google-genai")
        return False
    except Exception as e:
        logger.error(f"[x] Failed to instrument Google GenAI: {e}")
        return False


def get_space_id() -> str:
    """Get the Arize space ID."""
    return SPACE_ID


def get_api_key() -> str:
    """Get the Arize API key."""
    return API_KEY


def is_arize_initialized() -> bool:
    """Check if Arize has been initialized."""
    return arize_initialized


def set_span_attributes(**attributes):
    """
    Set custom attributes on the current span for enhanced observability.

    This function adds metadata to the current OpenTelemetry span for
    better trace filtering and analysis in Phoenix.

    Args:
        **attributes: Key-value pairs to add as span attributes

    Example:
        set_span_attributes(
            mr_id=123,
            project_id="myproject",
            file_count=5,
            review_type="security"
        )
    """
    if not arize_initialized:
        logger.debug(f"[DEBUG] Arize not initialized - skipping span attributes: {list(attributes.keys())}")
        return

    try:
        from opentelemetry import trace

        # Use the direct approach to get current span from context
        current_span = trace.get_current_span()

        if current_span and current_span.is_recording():
            current_span.set_attributes(attributes)
            logger.info(f"[✅] Set {len(attributes)} span attributes: {list(attributes.keys())[:5]}...")
        else:
            logger.warning(f"[⚠️] No active/recording span - cannot set attributes: {list(attributes.keys())}")
    except Exception as e:
        logger.warning(f"[⚠️] Failed to set span attributes: {e}")
        import traceback
        logger.debug(f"[DEBUG] Traceback: {traceback.format_exc()}")


def get_phoenix_mode() -> str:
    """Get the Phoenix deployment mode."""
    return PHOENIX_MODE


def get_phoenix_api_key() -> str:
    """Get the Phoenix API key for authentication."""
    return PHOENIX_API_KEY


def get_phoenix_project_name() -> str:
    """Get the Phoenix project name for evaluation grouping."""
    return PHOENIX_PROJECT_NAME


def shutdown():
    """Shutdown the Arize tracer provider (flushes pending traces)."""
    global tracer_provider, arize_initialized, phoenix_client

    if tracer_provider:
        try:
            tracer_provider.shutdown()
            logger.info("[✅] Arize tracer provider shut down")
        except Exception as e:
            logger.warning(f"[⚠️] Error shutting down tracer provider: {e}")
        finally:
            tracer_provider = None
            arize_initialized = False

    if phoenix_client:
        try:
            phoenix_client.close()
            logger.info("[✅] Phoenix client closed")
        except Exception as e:
            logger.warning(f"[⚠️] Error closing Phoenix client: {e}")
        finally:
            phoenix_client = None
