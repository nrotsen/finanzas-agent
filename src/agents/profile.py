"""
Perfil del dueño del agente: nombre y categorías habituales.

Los datos personales no viven en el código. Se leen de AGENT_PROFILE_JSON
(en Lambda la hidrata bootstrap_lambda() desde Secrets Manager; en local,
desde .env). Si no está seteada, se usa un perfil genérico.

Formato:
  {
    "owner_name": "Ana",
    "categorias_variables": ["comida", "transporte", "salud", "extra"],
    "categorias_fijas": ["alquiler", "tarjeta_visa", "internet"]
  }
"""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentProfile:
    owner_name: str = "el usuario"
    categorias_variables: list[str] = field(
        default_factory=lambda: ["comida", "transporte", "salud", "extra"]
    )
    categorias_fijas: list[str] = field(
        default_factory=lambda: ["alquiler", "tarjeta_visa", "internet", "celular"]
    )

    @property
    def categorias(self) -> list[str]:
        return [*self.categorias_variables, *self.categorias_fijas]


def load_profile() -> AgentProfile:
    raw = os.environ.get("AGENT_PROFILE_JSON")
    if not raw:
        return AgentProfile()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.error("AGENT_PROFILE_JSON no es JSON válido — usando perfil genérico")
        return AgentProfile()
    default = AgentProfile()
    return AgentProfile(
        owner_name=data.get("owner_name") or default.owner_name,
        categorias_variables=data.get("categorias_variables") or default.categorias_variables,
        categorias_fijas=data.get("categorias_fijas") or default.categorias_fijas,
    )
