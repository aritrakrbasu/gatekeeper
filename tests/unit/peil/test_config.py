import os

from peil.config import get_aril_settings, is_capture_enabled


def test_capture_enabled_default(monkeypatch):
    monkeypatch.delenv("ARIL_CAPTURE_ENABLED", raising=False)
    get_aril_settings.cache_clear()
    assert is_capture_enabled() is True


def test_capture_disabled_via_env(monkeypatch):
    monkeypatch.setenv("ARIL_CAPTURE_ENABLED", "false")
    get_aril_settings.cache_clear()
    assert is_capture_enabled() is False


def test_collection_names_override(monkeypatch):
    monkeypatch.setenv("ARIL_COLLECTION_SUBJECTS", "custom_subjects")
    get_aril_settings.cache_clear()
    settings = get_aril_settings()
    assert settings.collection_subjects == "custom_subjects"
