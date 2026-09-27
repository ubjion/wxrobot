from app.services.privacy import anonymous_id, redact_sensitive_text


def test_redacts_common_sensitive_values_without_losing_intent():
    source = (
        "联系13800138000或alice@example.com，身份证110101199001011234，"
        "账号wxid_alice123，Bearer abcdefghijklmnop，"
        "api_key=sk-test-secret-value，password: open-sesame，请帮我订票"
    )

    cleaned = redact_sensitive_text(source)

    for secret in (
        "13800138000",
        "alice@example.com",
        "110101199001011234",
        "wxid_alice123",
        "abcdefghijklmnop",
        "sk-test-secret-value",
        "open-sesame",
    ):
        assert secret not in cleaned
    assert "请帮我订票" in cleaned
    assert "[PHONE]" in cleaned
    assert "[EMAIL]" in cleaned
    assert "[ID_CARD]" in cleaned
    assert "[USER]" in cleaned
    assert "[SECRET]" in cleaned


def test_anonymous_id_is_stable_and_does_not_expose_input():
    first = anonymous_id("alice@chatroom")
    second = anonymous_id("alice@chatroom")

    assert first == second
    assert "alice" not in first
