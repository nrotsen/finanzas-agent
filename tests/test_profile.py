"""
Tests offline del perfil del agente (datos personales fuera del código).
No tocan AWS, Sheets ni Anthropic.
"""
import json
import os
from datetime import date

from src.agents.profile import AgentProfile, load_profile
from src.agents.personal import build_system_prompt


def test_profile_generico_sin_env():
    os.environ.pop("AGENT_PROFILE_JSON", None)
    assert load_profile() == AgentProfile()


def test_profile_desde_env():
    os.environ["AGENT_PROFILE_JSON"] = json.dumps({
        "owner_name": "Ana",
        "categorias_fijas": ["alquiler", "gimnasio"],
    })
    try:
        p = load_profile()
    finally:
        os.environ.pop("AGENT_PROFILE_JSON")
    assert p.owner_name == "Ana"
    assert p.categorias_fijas == ["alquiler", "gimnasio"]
    # Lo que no viene en el JSON cae al default
    assert p.categorias_variables == AgentProfile().categorias_variables


def test_profile_json_invalido_usa_generico():
    os.environ["AGENT_PROFILE_JSON"] = "{no es json"
    try:
        assert load_profile() == AgentProfile()
    finally:
        os.environ.pop("AGENT_PROFILE_JSON")


def test_system_prompt_incluye_perfil():
    p = AgentProfile(owner_name="Ana", categorias_variables=["comida"], categorias_fijas=["gimnasio"])
    prompt = build_system_prompt(p, date(2026, 5, 19))
    assert "personal de Ana" in prompt
    assert "- Variables: comida" in prompt
    assert "- Fijos: gimnasio" in prompt
    assert "martes 19 de mayo de 2026 (2026-05-19)" in prompt
