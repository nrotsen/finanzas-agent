"""
Tools que el LLM puede invocar.

Cada tool tiene:
  - schema (lo que ve Claude)
  - handler (la función Python que se ejecuta)

Los handlers reciben el adapter inyectado, así la misma tool sirve para
gastos personales (Sheets) o para un futuro agente sobre DynamoDB.
"""
from datetime import date
from typing import Optional

from ..adapters import DataAdapter, Gasto
from .date_utils import parse_periodo


# ============================================================
# SCHEMAS — lo que Claude ve
# ============================================================

TOOLS_SCHEMA = [
    {
        "name": "registrar_gasto",
        "description": (
            "Registra un nuevo gasto. Usar cuando el usuario describe un gasto "
            "(ej: 'gasté 5000 en el súper', 'pagué 12000 de luz'). "
            "Si falta categoría, inferir del contexto. "
            "Si falta fecha, asumir hoy. "
            "Si falta moneda, asumir ARS."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "monto": {"type": "number", "description": "Monto del gasto"},
                "moneda": {"type": "string", "enum": ["ARS", "USD"], "default": "ARS"},
                "descripcion": {"type": "string", "description": "Descripción libre"},
                "categoria": {
                    "type": "string",
                    "description": (
                        "Categoría inferida. Sugeridas: supermercado, transporte, "
                        "servicios, comida_fuera, salud, ocio, educacion, ropa, "
                        "hogar, regalos, viajes, otros"
                    ),
                },
                "fecha": {
                    "type": "string",
                    "description": "Fecha en formato YYYY-MM-DD. Omitir para usar hoy.",
                },
                "medio_pago": {
                    "type": "string",
                    "enum": ["efectivo", "debito", "credito", "transferencia", "mp"],
                    "description": (
                        "Cómo pagó el usuario. NO inventar — si el usuario no lo "
                        "aclaró ni se puede inferir del mensaje, NO llames a esta "
                        "tool todavía: preguntale primero al usuario."
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags opcionales adicionales.",
                },
            },
            "required": ["monto", "descripcion", "categoria"],
        },
    },
    {
        "name": "consultar_gastos",
        "description": (
            "Lista gastos filtrados. Usar cuando el usuario pregunta 'qué gasté en X', "
            "'mostrame los gastos de marzo', 'cuánto llevo este mes en comida', etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "periodo": {
                    "type": "string",
                    "description": (
                        "Período en lenguaje natural: 'hoy', 'esta semana', 'este mes', "
                        "'mes pasado', 'marzo', 'marzo 2026', o rango ISO 'YYYY-MM-DD:YYYY-MM-DD'."
                    ),
                },
                "categoria": {"type": "string"},
                "moneda": {"type": "string", "enum": ["ARS", "USD"]},
                "descripcion_contiene": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "resumen",
        "description": (
            "Resumen agregado por categoría y moneda en un período. "
            "Usar para 'cuánto gasté en total', 'resumen del mes', etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "periodo": {"type": "string", "description": "Período (ver consultar_gastos)"},
                "moneda": {"type": "string", "enum": ["ARS", "USD"]},
            },
            "required": ["periodo"],
        },
    },
    {
        "name": "editar_gasto",
        "description": "Edita un gasto existente por id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "monto": {"type": "number"},
                "categoria": {"type": "string"},
                "descripcion": {"type": "string"},
                "medio_pago": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "borrar_gasto",
        "description": "Borra un gasto por id. Confirmar antes con el usuario.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "listar_categorias",
        "description": (
            "Lista todas las categorías que ya existen en los gastos registrados. "
            "Usar antes de crear una categoría nueva si tenés dudas de si ya existe "
            "algo parecido, o cuando el usuario pregunte 'qué categorías tengo'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ============================================================
# HANDLERS — la lógica real
# ============================================================

def registrar_gasto(adapter: DataAdapter, **kwargs) -> dict:
    fecha = (
        date.fromisoformat(kwargs["fecha"])
        if kwargs.get("fecha")
        else date.today()
    )
    gasto = Gasto(
        fecha=fecha,
        monto=float(kwargs["monto"]),
        moneda=kwargs.get("moneda", "ARS"),
        categoria=kwargs["categoria"],
        descripcion=kwargs["descripcion"],
        medio_pago=kwargs.get("medio_pago", "efectivo"),
        fuente="manual",
        tags=kwargs.get("tags", []),
    )
    id_ = adapter.insert_gasto(gasto)
    return {"ok": True, "id": id_, "gasto": gasto.to_dict()}


def consultar_gastos(adapter: DataAdapter, **kwargs) -> dict:
    desde = hasta = None
    if kwargs.get("periodo"):
        desde, hasta = parse_periodo(kwargs["periodo"])
    gastos = adapter.query_gastos(
        desde=desde,
        hasta=hasta,
        categoria=kwargs.get("categoria"),
        moneda=kwargs.get("moneda"),
        descripcion_contiene=kwargs.get("descripcion_contiene"),
        limit=kwargs.get("limit", 50),
    )
    return {
        "cantidad": len(gastos),
        "gastos": [g.to_dict() for g in gastos],
    }


def resumen(adapter: DataAdapter, **kwargs) -> dict:
    desde, hasta = parse_periodo(kwargs["periodo"])
    r = adapter.resumen(desde=desde, hasta=hasta, moneda=kwargs.get("moneda"))
    return r.to_dict()


def editar_gasto(adapter: DataAdapter, **kwargs) -> dict:
    id_ = kwargs.pop("id")
    adapter.update_gasto(id_, **kwargs)
    return {"ok": True, "id": id_}


def borrar_gasto(adapter: DataAdapter, **kwargs) -> dict:
    adapter.delete_gasto(kwargs["id"])
    return {"ok": True, "id": kwargs["id"]}


def listar_categorias(adapter: DataAdapter, **kwargs) -> dict:
    return {"categorias": adapter.listar_categorias()}


HANDLERS = {
    "registrar_gasto": registrar_gasto,
    "consultar_gastos": consultar_gastos,
    "resumen": resumen,
    "editar_gasto": editar_gasto,
    "borrar_gasto": borrar_gasto,
    "listar_categorias": listar_categorias,
}
