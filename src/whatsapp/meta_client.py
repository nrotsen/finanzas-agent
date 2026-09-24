"""
Cliente Meta WhatsApp Cloud API (envío de mensajes + validación de firma).

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api

Env vars necesarias:
  META_ACCESS_TOKEN     - Bearer token (System User token permanente o dev token)
  META_PHONE_NUMBER_ID  - ID del número emisor (no es el número en sí)
  META_APP_SECRET       - App secret para validar firma X-Hub-Signature-256
"""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import os
import re
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


# Argentine mobile wa_id viene en formato moderno: 54 + 9 + AREA + LOCAL.
# Meta sin embargo guarda el destinatario en la whitelist (cuentas de test) y
# acepta envíos en formato legacy: 54 + AREA + 15 + LOCAL. Si mandamos el
# wa_id tal cual, Meta responde #131030 ("not in allowed list") aunque el
# número esté autorizado. La conversión es solo "mover el 9 al 15 que va
# después del código de área". Por ahora solo manejamos área 11 (Buenos
# Aires); otras áreas (223, 261, 341, 351, etc.) las dejamos sin cambios
# hasta que aparezca un caso real.
_AR_BS_AS_MOBILE = re.compile(r"^549(11)(\d{8})$")


def normalize_ar_wa_id(wa_id: str) -> str:
    """Convierte un wa_id argentino al formato legacy que Meta espera. Para
    números no argentinos / áreas no soportadas devuelve el input sin cambios."""
    m = _AR_BS_AS_MOBILE.match(wa_id or "")
    if not m:
        return wa_id
    area, local = m.group(1), m.group(2)
    return f"54{area}15{local}"


class MetaWhatsAppClient:
    def __init__(
        self,
        access_token: str | None = None,
        phone_number_id: str | None = None,
    ):
        self.access_token = access_token or os.environ["META_ACCESS_TOKEN"]
        self.phone_number_id = phone_number_id or os.environ["META_PHONE_NUMBER_ID"]

    def send_text(self, to: str, text: str) -> dict:
        """
        Envía un mensaje de texto. `to` es el E.164 sin '+' (ej: 5491112345678).
        Para wa_ids argentinos se aplica normalize_ar_wa_id antes de mandar.
        Devuelve el JSON de respuesta de Meta.
        """
        to_normalized = normalize_ar_wa_id(to)
        if to_normalized != to:
            log.info("normalizado wa_id %s → %s para Meta", to, to_normalized)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_normalized,
            "type": "text",
            "text": {"body": text[:4096], "preview_url": False},
        }
        url = f"{GRAPH_API_BASE}/{self.phone_number_id}/messages"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            log.error("meta send_text failed status=%s body=%s", e.code, body)
            raise


def validate_signature(body: bytes, header_sig: str | None, app_secret: str | None = None) -> bool:
    """
    Valida la firma X-Hub-Signature-256 que Meta envía con cada webhook.
    `body` debe ser el raw body (bytes) — NO el JSON parseado.
    """
    if not header_sig:
        return False
    secret = app_secret or os.environ.get("META_APP_SECRET")
    if not secret:
        log.warning("META_APP_SECRET no seteado — validación de firma deshabilitada")
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header_sig)


def extract_message(payload: dict) -> dict | None:
    """
    Extrae info del primer mensaje de texto en el payload de webhook de Meta.
    Devuelve {from, text, message_id, timestamp} o None si no hay mensaje
    procesable (puede ser un evento de status, no de mensaje entrante).
    """
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
        messages = value.get("messages")
        if not messages:
            return None
        m = messages[0]
        if m.get("type") != "text":
            # TODO: manejar audio, image, document
            return {
                "from": m.get("from"),
                "text": f"[mensaje no soportado: type={m.get('type')}]",
                "message_id": m.get("id"),
                "timestamp": m.get("timestamp"),
                "unsupported_type": m.get("type"),
            }
        return {
            "from": m["from"],
            "text": m["text"]["body"],
            "message_id": m["id"],
            "timestamp": m.get("timestamp"),
        }
    except (KeyError, IndexError) as e:
        log.warning("payload de Meta inesperado: %s", e)
        return None
