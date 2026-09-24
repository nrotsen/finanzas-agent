"""
Loop de tool use de Claude.

El agente recibe un mensaje, llama a Claude, ejecuta tools si Claude las pide,
y devuelve la respuesta final en texto. Mantiene el historial entre llamadas
del mismo usuario (se inyecta desde fuera, ver state/conversation.py).
"""
import json
from dataclasses import dataclass

from ..adapters import DataAdapter
from ..llm import ClaudeClient
from ..tools import TOOLS_SCHEMA, HANDLERS


MAX_TOOL_ITERATIONS = 8


@dataclass
class AgentConfig:
    name: str               # "personal" | futuros agentes
    system_prompt: str
    adapter: DataAdapter
    tools_schema: list[dict]
    handlers: dict


class Agent:
    def __init__(self, config: AgentConfig, llm: ClaudeClient | None = None):
        self.cfg = config
        self.llm = llm or ClaudeClient()

    def run(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """
        Corre un turno completo (puede incluir varias tool calls).

        Args:
            messages: historial completo de la conversación (formato Anthropic).

        Returns:
            (texto_de_respuesta, mensajes_actualizados)
        """
        msgs = list(messages)

        for _ in range(MAX_TOOL_ITERATIONS):
            resp = self.llm.create_message(
                messages=msgs,
                system=self.cfg.system_prompt,
                tools=self.cfg.tools_schema,
            )

            # Append assistant turn
            msgs.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason != "tool_use":
                # Terminó. Extraer texto.
                texto = "".join(
                    block.text for block in resp.content if block.type == "text"
                )
                return texto, msgs

            # Procesar tool calls
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                handler = self.cfg.handlers.get(block.name)
                if not handler:
                    result = {"error": f"tool desconocida: {block.name}"}
                else:
                    try:
                        result = handler(self.cfg.adapter, **block.input)
                    except Exception as e:
                        result = {"error": str(e)}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

            msgs.append({"role": "user", "content": tool_results})

        return "Disculpá, me quedé en loop procesando esto. Probá de nuevo.", msgs
