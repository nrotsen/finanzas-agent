"""
Cliente fino sobre la API de Anthropic.

El día que migres a Bedrock, este es el ÚNICO archivo que cambia.
El resto del código habla con esta interfaz.
"""
import logging
import os

from anthropic import Anthropic

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"  # ajustar al modelo que prefieras


class ClaudeClient:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None):
        self.model = model
        self.client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        log.info("ClaudeClient instanciado con modelo=%s", self.model)

    def create_message(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 2048,
    ):
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
        log.info(
            "anthropic respuesta model=%s stop_reason=%s input_tokens=%s output_tokens=%s",
            resp.model, resp.stop_reason,
            resp.usage.input_tokens, resp.usage.output_tokens,
        )
        return resp
