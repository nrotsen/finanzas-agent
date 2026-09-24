"""
Test local del agent_runner sin AWS (sin DynamoDB ni Lambda).

Simula el evento que el webhook le manda al runner: {user_id, message,
message_id}. Reemplaza DynamoDB por un store en memoria y el cliente Meta
por un fake que imprime en consola.

Uso:
    python -m scripts.test_webhook_local

Sirve para iterar el flow completo (state + agente + envío) antes de deployar.
"""
from __future__ import annotations
import uuid

from dotenv import load_dotenv

load_dotenv()

from src.handlers import agent_runner  # noqa: E402
from src.state.conversation import InMemoryConversationStore  # noqa: E402


class FakeMeta:
    """Reemplazo del MetaWhatsAppClient para test local."""

    def send_text(self, to: str, text: str) -> dict:
        print(f"\n[meta → {to}]\n{text}\n")
        return {"messages": [{"id": "fake-" + uuid.uuid4().hex[:8]}]}


def install_fakes() -> InMemoryConversationStore:
    store = InMemoryConversationStore()
    agent_runner._store = store
    agent_runner._meta = FakeMeta()
    return store


def main():
    store = install_fakes()
    user_id = "5491100000000"  # número fake
    print("Simulador WhatsApp local. Escribí mensajes como si fueras el usuario.")
    print("Comandos: 'reset' borra el historial, 'salir' termina.\n")

    while True:
        try:
            text = input("[whatsapp] ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in ("salir", "exit", "quit"):
            break
        if text.lower() == "reset":
            store.clear(user_id)
            print("(historial borrado)\n")
            continue

        event = {
            "user_id": user_id,
            "message": text,
            "message_id": "wamid." + uuid.uuid4().hex[:16],
        }
        result = agent_runner.lambda_handler(event, None)
        if not result.get("ok"):
            print(f"[error] {result}\n")


if __name__ == "__main__":
    main()
