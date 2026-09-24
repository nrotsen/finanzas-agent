"""
Historial de conversación por usuario, persistido en DynamoDB con TTL.

El historial se guarda como un único atributo string con JSON serializado
para sortear las restricciones de tipos de DynamoDB (no acepta floats sin
Decimal). Eso es suficiente: el historial es chico (limitado por TTL 24h
y truncado a últimas N rondas si crece).

Para tests locales sin AWS, usar InMemoryConversationStore.
"""
from __future__ import annotations
import json
import os
import time
from typing import Optional

TTL_SECONDS = 24 * 60 * 60  # 24h
MAX_MESSAGES = 60  # truncar para mantener costos de Claude bajos


def _block_to_dict(block) -> dict:
    """Convierte un ContentBlock de Anthropic a dict JSON-safe."""
    if isinstance(block, dict):
        return block
    # Pydantic v2 (anthropic SDK)
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json", exclude_none=True)
    # Fallback (anthropic SDK viejo o tipo inesperado)
    if hasattr(block, "dict"):
        return block.dict()
    raise TypeError(f"No sé serializar bloque tipo {type(block)}")


def serialize_messages(messages: list[dict]) -> list[dict]:
    """Convierte mensajes con ContentBlock objects a dicts puros."""
    out = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
        else:
            out.append({
                "role": m["role"],
                "content": [_block_to_dict(b) for b in content],
            })
    return out


def truncate(messages: list[dict], max_messages: int = MAX_MESSAGES) -> list[dict]:
    """
    Trunca el historial conservando el contexto reciente. Cuida que no se corte
    en medio de un par tool_use → tool_result (la API rechaza eso).
    """
    if len(messages) <= max_messages:
        return messages
    cut = len(messages) - max_messages
    # Si el mensaje en `cut` es un user con tool_result, retrocedé hasta encontrar
    # un mensaje que no rompa el par tool_use/tool_result.
    while cut < len(messages):
        m = messages[cut]
        content = m.get("content")
        if isinstance(content, list) and any(
            (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_result"
            for b in content
        ):
            cut += 1  # saltar mensajes con tool_result hasta encontrar uno limpio
            continue
        break
    return messages[cut:]


class ConversationStore:
    """Backend DynamoDB."""

    def __init__(self, table_name: Optional[str] = None, region: Optional[str] = None):
        import boto3
        self.table_name = table_name or os.environ["CONVERSATION_TABLE"]
        # En Lambda, AWS_REGION lo setea el runtime. Localmente, fallback a us-east-2.
        region = region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2"
        self.table = boto3.resource("dynamodb", region_name=region).Table(self.table_name)

    def load(self, user_id: str) -> dict:
        """Devuelve {messages: [...], last_message_id: '...'} (vacío si no existe)."""
        resp = self.table.get_item(Key={"user_id": user_id})
        item = resp.get("Item")
        if not item:
            return {"messages": [], "last_message_id": None}
        return {
            "messages": json.loads(item.get("messages", "[]")),
            "last_message_id": item.get("last_message_id"),
        }

    def save(self, user_id: str, messages: list[dict], last_message_id: Optional[str] = None) -> None:
        serialized = truncate(serialize_messages(messages))
        item = {
            "user_id": user_id,
            "messages": json.dumps(serialized, ensure_ascii=False),
            "expires_at": int(time.time()) + TTL_SECONDS,
        }
        if last_message_id:
            item["last_message_id"] = last_message_id
        self.table.put_item(Item=item)

    def clear(self, user_id: str) -> None:
        self.table.delete_item(Key={"user_id": user_id})


class InMemoryConversationStore:
    """Backend en memoria para tests."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    def load(self, user_id: str) -> dict:
        s = self._store.get(user_id)
        if not s:
            return {"messages": [], "last_message_id": None}
        return {"messages": list(s["messages"]), "last_message_id": s["last_message_id"]}

    def save(self, user_id: str, messages: list[dict], last_message_id: Optional[str] = None) -> None:
        self._store[user_id] = {
            "messages": truncate(serialize_messages(messages)),
            "last_message_id": last_message_id,
        }

    def clear(self, user_id: str) -> None:
        self._store.pop(user_id, None)
