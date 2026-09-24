"""
Tests offline del webhook + state + cliente Meta.
No tocan AWS ni Anthropic.
"""
import hashlib
import hmac
import json
import os

# Env vars necesarias antes de importar los módulos
os.environ.setdefault("META_APP_SECRET", "test_secret_123")
os.environ.setdefault("META_VERIFY_TOKEN", "my_verify_token")

from src.handlers import whatsapp_webhook  # noqa: E402
from src.state.conversation import (  # noqa: E402
    InMemoryConversationStore, serialize_messages, truncate,
)
from src.whatsapp.meta_client import extract_message, validate_signature  # noqa: E402


# ============================================================
# Meta client
# ============================================================

def test_validate_signature_ok():
    body = b'{"hello":"world"}'
    sig = "sha256=" + hmac.new(b"test_secret_123", body, hashlib.sha256).hexdigest()
    assert validate_signature(body, sig)


def test_validate_signature_bad():
    assert not validate_signature(b'{"x":1}', "sha256=deadbeef")
    assert not validate_signature(b'{"x":1}', None)


def test_extract_message_text():
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "5491112345678",
                        "id": "wamid.ABC",
                        "timestamp": "1716148800",
                        "text": {"body": "hola"},
                        "type": "text",
                    }],
                },
            }],
        }],
    }
    msg = extract_message(payload)
    assert msg["from"] == "5491112345678"
    assert msg["text"] == "hola"
    assert msg["message_id"] == "wamid.ABC"


def test_extract_message_status_event():
    """Eventos de status (delivered/read) no son mensajes — devolver None."""
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
    assert extract_message(payload) is None


# ============================================================
# Webhook handler
# ============================================================

def test_webhook_get_verification_ok():
    event = {
        "httpMethod": "GET",
        "queryStringParameters": {
            "hub.mode": "subscribe",
            "hub.verify_token": "my_verify_token",
            "hub.challenge": "12345",
        },
    }
    resp = whatsapp_webhook.lambda_handler(event, None)
    assert resp["statusCode"] == 200
    assert resp["body"] == "12345"


def test_webhook_get_verification_bad_token():
    event = {
        "httpMethod": "GET",
        "queryStringParameters": {
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "12345",
        },
    }
    resp = whatsapp_webhook.lambda_handler(event, None)
    assert resp["statusCode"] == 403


def test_webhook_post_invalid_signature():
    event = {
        "httpMethod": "POST",
        "body": '{"foo":"bar"}',
        "headers": {"X-Hub-Signature-256": "sha256=deadbeef"},
    }
    resp = whatsapp_webhook.lambda_handler(event, None)
    assert resp["statusCode"] == 401


class _FakeLambdaClient:
    def __init__(self):
        self.invocations = []

    def invoke(self, **kwargs):
        self.invocations.append(kwargs)


def _signed_message_event(sender: str) -> dict:
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [{
        "from": sender, "id": "wamid.test", "timestamp": "1716000000",
        "type": "text", "text": {"body": "hola"},
    }]}}]}]})
    sig = "sha256=" + hmac.new(b"test_secret_123", body.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"httpMethod": "POST", "body": body, "headers": {"X-Hub-Signature-256": sig}}


def _post_with_allowlist(sender: str, allowlist: str) -> _FakeLambdaClient:
    fake = _FakeLambdaClient()
    os.environ["ALLOWED_SENDERS"] = allowlist
    os.environ["AGENT_FUNCTION_NAME"] = "runner"
    whatsapp_webhook._lambda_client = fake
    try:
        resp = whatsapp_webhook.lambda_handler(_signed_message_event(sender), None)
    finally:
        whatsapp_webhook._lambda_client = None
    assert resp["statusCode"] == 200  # siempre 200: Meta no debe reintentar
    return fake


def test_webhook_post_allowed_sender_invokes_agent():
    fake = _post_with_allowlist("5491112345678", "5491112345678")
    assert len(fake.invocations) == 1
    assert json.loads(fake.invocations[0]["Payload"])["user_id"] == "5491112345678"


def test_webhook_post_unknown_sender_is_dropped():
    fake = _post_with_allowlist("5491199998888", "5491112345678")
    assert fake.invocations == []


def test_webhook_post_allowlist_matches_legacy_ar_format():
    """El wa_id llega moderno (549 11 ...) y la allowlist puede estar en legacy (54 11 15 ...)."""
    fake = _post_with_allowlist("5491112345678", "+54111512345678")
    assert len(fake.invocations) == 1


def test_webhook_post_empty_allowlist_fails_closed():
    fake = _post_with_allowlist("5491112345678", "")
    assert fake.invocations == []


# ============================================================
# State / conversation
# ============================================================

def test_serialize_strings_passthrough():
    msgs = [{"role": "user", "content": "hola"}]
    assert serialize_messages(msgs) == msgs


def test_serialize_content_blocks():
    """Bloques con .model_dump() deben convertirse a dict."""
    class FakeBlock:
        def model_dump(self, mode=None, exclude_none=None):
            return {"type": "text", "text": "hola"}

    msgs = [{"role": "assistant", "content": [FakeBlock()]}]
    out = serialize_messages(msgs)
    assert out == [{"role": "assistant", "content": [{"type": "text", "text": "hola"}]}]


def test_truncate_corta_par_tool_use():
    """Si el primer mensaje del corte es un tool_result, debe avanzar para no
    dejar un tool_result huérfano (sin su tool_use)."""
    msgs = [{"role": "user", "content": f"msg{i}"} for i in range(50)]
    msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "y"}]})
    msgs.append({"role": "assistant", "content": "ok"})
    truncated = truncate(msgs, max_messages=2)
    # Debe haber saltado el tool_result huérfano
    assert all(
        not (isinstance(m["content"], list) and m["content"] and m["content"][0].get("type") == "tool_result")
        for m in truncated
    )


def test_inmemory_store_roundtrip():
    s = InMemoryConversationStore()
    assert s.load("user1") == {"messages": [], "last_message_id": None}
    s.save("user1", [{"role": "user", "content": "hola"}], last_message_id="m1")
    state = s.load("user1")
    assert state["messages"] == [{"role": "user", "content": "hola"}]
    assert state["last_message_id"] == "m1"
    s.clear("user1")
    assert s.load("user1") == {"messages": [], "last_message_id": None}
