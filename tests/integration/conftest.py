"""Integration test environment — set API keys before agent/service imports."""

import os

os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key-for-integration")
os.environ.setdefault("GOOGLE_API_KEY", "test-gemini-key-for-integration")
