from peil.capture.sanitize import mask_sensitive_arguments, sanitize_event_payload, sanitize_text


def test_mask_sensitive_keys():
    masked = mask_sensitive_arguments(
        {"api_key": "secret", "repo": "gatekeeper", "nested": {"password": "x"}}
    )
    assert masked["api_key"] == "[MASKED]"
    assert masked["repo"] == "gatekeeper"
    assert masked["nested"]["password"] == "[MASKED]"


def test_sanitize_text_masks_tokens():
    text = "token glpat-abcdefghijklmnopqrstuvwxyz123456"
    sanitized = sanitize_text(text)
    assert "glpat-" not in sanitized
    assert "[MASKED_GITLAB_TOKEN]" in sanitized


def test_sanitize_event_payload_recursive():
    payload = sanitize_event_payload(
        {
            "arguments": {"api_key": "abc"},
            "message": "Bearer abc.def.ghi",
        }
    )
    assert payload["arguments"]["api_key"] == "[MASKED]"
    assert "Bearer [MASKED_BEARER_TOKEN]" in payload["message"]
