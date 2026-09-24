"""
Lambda async que corre el agente personal.

Invocado por whatsapp_webhook con payload:
  { "user_id": "<phone>", "message": "<text>", "message_id": "<id>" }

Flujo:
  1. Carga estado de DynamoDB (history + last_message_id).
  2. Idempotencia: si el último message_id procesado == el nuevo, ignora.
  3. Append user message → agent.run() → recibe respuesta.
  4. Manda respuesta por WhatsApp via Meta API (si Meta está configurada).
  5. Guarda historial actualizado + last_message_id en DynamoDB.

Si las credenciales de Meta no están seteadas (deploy parcial sin Meta),
el agente igual procesa el mensaje y devuelve el response en el payload de
retorno (útil para test manual con `aws lambda invoke`).

El agente y el cliente Meta se cachean a nivel módulo para reusar entre
invocaciones tibias (cold start solo paga el costo una vez).
"""
from __future__ import annotations
import logging
import os

from ..config import bootstrap_lambda

# Hidratar env vars desde Secrets Manager al cold start, antes de importar
# el resto (que va a leer ANTHROPIC_API_KEY, GOOGLE_SHEETS_CREDS_JSON, etc.).
bootstrap_lambda()

from ..agents.personal import build_personal_agent  # noqa: E402
from ..state.conversation import ConversationStore  # noqa: E402
from ..whatsapp.meta_client import MetaWhatsAppClient  # noqa: E402

log = logging.getLogger()
log.setLevel(logging.INFO)

_agent = None
_store: ConversationStore | None = None
_meta: MetaWhatsAppClient | None = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = build_personal_agent()
    return _agent


def _get_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store


def _get_meta() -> MetaWhatsAppClient | None:
    """Devuelve el cliente Meta o None si las credenciales no están configuradas."""
    global _meta
    if _meta is not None:
        return _meta
    if not os.environ.get("META_ACCESS_TOKEN") or not os.environ.get("META_PHONE_NUMBER_ID"):
        return None
    _meta = MetaWhatsAppClient()
    return _meta


def lambda_handler(event: dict, context) -> dict:
    user_id = event.get("user_id")
    message = event.get("message")
    message_id = event.get("message_id")
    if not (user_id and message and message_id):
        log.error("payload inválido: %s", event)
        return {"ok": False, "error": "missing fields"}

    store = _get_store()
    state = store.load(user_id)
    if state["last_message_id"] == message_id:
        log.info("mensaje %s ya procesado, skip", message_id)
        return {"ok": True, "skipped": True}

    log.info("procesando msg user=%s id=%s", user_id, message_id)
    history = state["messages"]
    history.append({"role": "user", "content": message})

    try:
        respuesta, history = _get_agent().run(history)
    except Exception:
        log.exception("error corriendo agente")
        meta = _get_meta()
        if meta:
            try:
                meta.send_text(
                    user_id,
                    "Uy, se me rompió algo procesando eso. Probá de nuevo en un toque.",
                )
            except Exception:
                log.exception("además falló el aviso a usuario")
        return {"ok": False, "error": "agent error"}

    meta = _get_meta()
    meta_skipped = False
    if respuesta.strip():
        if meta is None:
            log.warning(
                "Meta no configurada — agente corrió OK pero no se envió respuesta. "
                "Response del agente: %s",
                respuesta,
            )
            meta_skipped = True
        else:
            try:
                meta.send_text(user_id, respuesta)
            except Exception:
                log.exception("error mandando respuesta a Meta")
                return {"ok": False, "error": "meta send failed", "agent_response": respuesta}

    store.save(user_id, history, last_message_id=message_id)
    return {"ok": True, "agent_response": respuesta, "meta_skipped": meta_skipped}
