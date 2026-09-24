"""
Lambda webhook de WhatsApp (Meta Cloud API).

GET /webhook:
  Meta envía hub.mode/hub.verify_token/hub.challenge para verificar el endpoint.
  Si el verify_token matchea, devolvemos hub.challenge como plain text.

POST /webhook:
  Meta nos manda mensajes entrantes (y eventos de status que ignoramos).
  Validamos la firma X-Hub-Signature-256, extraemos el mensaje, e invocamos
  al agent_runner ASÍNCRONO (InvocationType=Event) — así devolvemos 200 OK
  en <1s. Meta tiene timeout ~5s y reintenta si no respondemos rápido.
"""
from __future__ import annotations
import hmac
import json
import logging
import os

from ..config import bootstrap_lambda
from ..whatsapp.meta_client import extract_message, normalize_ar_wa_id, validate_signature

# Hidratar env vars desde Secrets Manager al cold start, antes de cualquier uso.
bootstrap_lambda()

log = logging.getLogger()
log.setLevel(logging.INFO)

_lambda_client = None


def _get_lambda_client():
    """Lazy-init para no fallar al importar fuera de Lambda."""
    global _lambda_client
    if _lambda_client is None:
        import boto3
        _lambda_client = boto3.client("lambda")
    return _lambda_client


def _resp(status: int, body: str = "", content_type: str = "text/plain") -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": content_type},
        "body": body,
    }


def _handle_verification(event: dict) -> dict:
    qs = event.get("queryStringParameters") or {}
    mode = qs.get("hub.mode")
    token = qs.get("hub.verify_token")
    challenge = qs.get("hub.challenge", "")
    expected_token = os.environ.get("META_VERIFY_TOKEN") or ""
    token_ok = bool(expected_token) and hmac.compare_digest(
        (token or "").encode("utf-8"), expected_token.encode("utf-8")
    )
    if mode == "subscribe" and token_ok:
        log.info("webhook verificado")
        return _resp(200, challenge)
    log.warning("webhook verification falló mode=%s token_match=%s", mode, token_ok)
    return _resp(403, "forbidden")


def _allowed_senders() -> set[str]:
    """
    ALLOWED_SENDERS: wa_ids separados por coma. Se comparan normalizados
    (ver normalize_ar_wa_id) para que el formato moderno y el legacy de un
    mismo número argentino matcheen.
    """
    raw = os.environ.get("ALLOWED_SENDERS", "")
    return {normalize_ar_wa_id(n.strip().lstrip("+")) for n in raw.split(",") if n.strip()}


def _is_allowed(sender: str) -> bool:
    return normalize_ar_wa_id(sender) in _allowed_senders()


def _get_raw_body(event: dict) -> bytes:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        import base64
        return base64.b64decode(body)
    return body.encode("utf-8")


def _get_header(event: dict, name: str) -> str | None:
    headers = event.get("headers") or {}
    # API Gateway puede dar headers con cualquier case
    lowered = {k.lower(): v for k, v in headers.items()}
    return lowered.get(name.lower())


def _handle_incoming(event: dict) -> dict:
    raw = _get_raw_body(event)
    sig = _get_header(event, "x-hub-signature-256")
    if not validate_signature(raw, sig):
        log.warning("firma inválida — descartando")
        return _resp(401, "invalid signature")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("body no es JSON válido")
        return _resp(400, "bad request")

    message = extract_message(payload)
    if not message:
        # Eventos de status (delivered, read, etc) — ignorar pero responder 200
        log.info("evento sin mensaje entrante, ignorado")
        return _resp(200, "ok")

    if not _is_allowed(message["from"]):
        # 200 para que Meta no reintente; el agente solo atiende a su dueño.
        log.warning("remitente fuera de ALLOWED_SENDERS — descartando msg_id=%s",
                    message["message_id"])
        return _resp(200, "ok")

    agent_function = os.environ.get("AGENT_FUNCTION_NAME")
    if not agent_function:
        log.error("AGENT_FUNCTION_NAME no seteado")
        return _resp(500, "misconfigured")

    _get_lambda_client().invoke(
        FunctionName=agent_function,
        InvocationType="Event",  # async fire-and-forget
        Payload=json.dumps({
            "user_id": message["from"],
            "message": message["text"],
            "message_id": message["message_id"],
        }).encode("utf-8"),
    )
    log.info("invocado agent_runner para user=%s msg_id=%s",
             message["from"], message["message_id"])
    return _resp(200, "ok")


def lambda_handler(event: dict, context) -> dict:
    method = event.get("httpMethod") or (event.get("requestContext", {})
                                         .get("http", {}).get("method"))
    if method == "GET":
        return _handle_verification(event)
    if method == "POST":
        try:
            return _handle_incoming(event)
        except Exception:
            log.exception("error procesando webhook")
            # Devolvemos 200 para que Meta no reintente — el error queda en logs
            return _resp(200, "ok")
    return _resp(405, "method not allowed")
