"""
Acceso a AWS Secrets Manager con caché por cold start.

Patrón de uso en Lambda:
  - Al cargar el módulo del handler se llama bootstrap_lambda(), que hidrata
    las env vars que el resto del código espera (ANTHROPIC_API_KEY, etc.)
    leyéndolas de Secrets Manager si no están ya en el entorno.
  - En local, las env vars vienen de .env y bootstrap_lambda() no hace nada
    (porque ya están seteadas; get_secret() ni se llama).

Los nombres de los secrets se leen de env vars (las setea el template SAM):
  ANTHROPIC_SECRET_NAME, GOOGLE_SHEETS_CREDS_SECRET_NAME,
  META_VERIFY_TOKEN_SECRET_NAME, META_ACCESS_TOKEN_SECRET_NAME,
  META_APP_SECRET_SECRET_NAME, ALLOWED_SENDERS_SECRET_NAME,
  AGENT_PROFILE_SECRET_NAME

Eso permite cambiar nombres / mover entre cuentas sin tocar código.
"""
from __future__ import annotations
import logging
import os

log = logging.getLogger(__name__)

_cache: dict[str, str | None] = {}
_bootstrapped = False


def get_secret(secret_id: str) -> str | None:
    """Lee un secret de AWS Secrets Manager. Cacheado. Devuelve None si no existe."""
    if secret_id in _cache:
        return _cache[secret_id]
    try:
        import boto3
        client = boto3.client("secretsmanager")
        resp = client.get_secret_value(SecretId=secret_id)
        value = resp.get("SecretString")
        _cache[secret_id] = value
        return value
    except Exception as e:
        # ResourceNotFoundException, NoRegionError, AccessDenied, etc.
        log.warning("get_secret(%s) falló: %s", secret_id, e)
        _cache[secret_id] = None
        return None


def hydrate_env(env_name: str, secret_id: str | None, required: bool = True) -> bool:
    """
    Si env_name no está seteada y secret_id está definido, intenta leerla de
    Secrets Manager y exponerla como env var. Devuelve True si la env var quedó
    poblada al terminar (ya estaba o se acaba de setear), False si no.
    """
    if os.environ.get(env_name):
        return True
    if not secret_id:
        if required:
            log.error("hydrate_env(%s): no hay env value ni secret_id", env_name)
        return False
    value = get_secret(secret_id)
    if value is None:
        if required:
            log.error("hydrate_env(%s): secret %s no disponible", env_name, secret_id)
        else:
            log.info("hydrate_env(%s) opcional, secret %s no disponible (skip)", env_name, secret_id)
        return False
    os.environ[env_name] = value
    return True


def bootstrap_lambda() -> dict[str, bool]:
    """
    Llamar al cargar el módulo de cada handler. Idempotente: la segunda llamada
    es no-op porque _bootstrapped se mantiene en True por todo el cold start.

    Devuelve un dict con el estado de cada env var (True = poblada, False = no).
    """
    global _bootstrapped
    if _bootstrapped:
        return {}
    _bootstrapped = True

    status = {
        "ANTHROPIC_API_KEY": hydrate_env(
            "ANTHROPIC_API_KEY",
            os.environ.get("ANTHROPIC_SECRET_NAME"),
            required=True,
        ),
        "GOOGLE_SHEETS_CREDS_JSON": hydrate_env(
            "GOOGLE_SHEETS_CREDS_JSON",
            os.environ.get("GOOGLE_SHEETS_CREDS_SECRET_NAME"),
            required=True,
        ),
        "META_VERIFY_TOKEN": hydrate_env(
            "META_VERIFY_TOKEN",
            os.environ.get("META_VERIFY_TOKEN_SECRET_NAME"),
            required=True,
        ),
        "META_ACCESS_TOKEN": hydrate_env(
            "META_ACCESS_TOKEN",
            os.environ.get("META_ACCESS_TOKEN_SECRET_NAME"),
            required=False,
        ),
        "META_APP_SECRET": hydrate_env(
            "META_APP_SECRET",
            os.environ.get("META_APP_SECRET_SECRET_NAME"),
            required=False,
        ),
        # Sin allowlist el webhook descarta todos los mensajes (fail-closed).
        "ALLOWED_SENDERS": hydrate_env(
            "ALLOWED_SENDERS",
            os.environ.get("ALLOWED_SENDERS_SECRET_NAME"),
            required=True,
        ),
        # Sin perfil el agente usa uno genérico (ver agents/profile.py).
        "AGENT_PROFILE_JSON": hydrate_env(
            "AGENT_PROFILE_JSON",
            os.environ.get("AGENT_PROFILE_SECRET_NAME"),
            required=False,
        ),
    }
    log.info("bootstrap_lambda status: %s", status)
    return status
