"""基线协议回归：webhook 事件 message_id 兜底、json 段前缀、alt_message 兜底"""

from WebhookAdapter.Converter import WebhookConverter


def test_message_id_generated_when_missing():
    conv = WebhookConverter("bot1")
    event = conv.convert({"user_id": "u1", "message": []}, account_name="default")
    assert isinstance(event["message_id"], str) and event["message_id"]


def test_message_id_passthrough():
    conv = WebhookConverter("bot1")
    event = conv.convert(
        {"user_id": "u1", "message_id": "abc", "message": []}, account_name="default"
    )
    assert event["message_id"] == "abc"


def test_json_segment_prefixed():
    conv = WebhookConverter("bot1")
    event = conv.convert(
        {
            "user_id": "u1",
            "message": [{"type": "json", "data": {"raw": {"a": 1}}}],
        },
        account_name="default",
    )
    assert [seg["type"] for seg in event["message"]] == ["webhook_json"]


def test_alt_message_defaults_to_empty_string():
    conv = WebhookConverter("bot1")
    event = conv.convert({"user_id": "u1", "message": []}, account_name="default")
    assert event["alt_message"] == ""
