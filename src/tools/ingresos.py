"""
Tools de ingresos y resumen financiero (ingresos vs gastos).
"""
from datetime import date

from ..adapters import DataAdapter, Ingreso
from .date_utils import parse_periodo


TOOLS_SCHEMA = [
    {
        "name": "registrar_ingreso",
        "description": (
            "Registra un ingreso (sueldo, freelance, venta, regalo, cashback, etc). "
            "Usar cuando el usuario diga 'cobré X', 'me entró Y', 'me pagaron Z'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "monto": {"type": "number"},
                "moneda": {"type": "string", "enum": ["ARS", "USD"], "default": "ARS"},
                "categoria": {
                    "type": "string",
                    "description": (
                        "Tipo de ingreso. Sugeridas: sueldo, freelance, venta, "
                        "regalo, cashback, reembolso, otros."
                    ),
                },
                "descripcion": {"type": "string"},
                "fecha": {
                    "type": "string",
                    "description": "YYYY-MM-DD. Omitir para hoy.",
                },
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["monto", "categoria", "descripcion"],
        },
    },
    {
        "name": "consultar_ingresos",
        "description": "Lista ingresos filtrados por período/categoría/moneda.",
        "input_schema": {
            "type": "object",
            "properties": {
                "periodo": {"type": "string"},
                "categoria": {"type": "string"},
                "moneda": {"type": "string", "enum": ["ARS", "USD"]},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "resumen_financiero",
        "description": (
            "Resumen consolidado de ingresos vs gastos en un período. "
            "Devuelve totales por moneda y el flujo neto. Usar para 'cómo voy "
            "este mes', 'cuánto neto llevo', 'balance del mes'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "periodo": {
                    "type": "string",
                    "description": "Período (ej: 'este mes', 'mayo', 'mes pasado').",
                },
                "moneda": {"type": "string", "enum": ["ARS", "USD"]},
            },
            "required": ["periodo"],
        },
    },
]


def registrar_ingreso(adapter: DataAdapter, **kwargs) -> dict:
    fecha = (
        date.fromisoformat(kwargs["fecha"])
        if kwargs.get("fecha")
        else date.today()
    )
    ingreso = Ingreso(
        fecha=fecha,
        monto=float(kwargs["monto"]),
        moneda=kwargs.get("moneda", "ARS"),
        categoria=kwargs["categoria"],
        descripcion=kwargs["descripcion"],
        fuente="manual",
        tags=kwargs.get("tags", []),
    )
    id_ = adapter.insert_ingreso(ingreso)
    return {"ok": True, "id": id_, "ingreso": ingreso.to_dict()}


def consultar_ingresos(adapter: DataAdapter, **kwargs) -> dict:
    desde = hasta = None
    if kwargs.get("periodo"):
        desde, hasta = parse_periodo(kwargs["periodo"])
    ings = adapter.query_ingresos(
        desde=desde,
        hasta=hasta,
        categoria=kwargs.get("categoria"),
        moneda=kwargs.get("moneda"),
        limit=kwargs.get("limit", 50),
    )
    return {
        "cantidad": len(ings),
        "ingresos": [i.to_dict() for i in ings],
    }


def resumen_financiero(adapter: DataAdapter, **kwargs) -> dict:
    desde, hasta = parse_periodo(kwargs["periodo"])
    moneda = kwargs.get("moneda")
    r_gastos = adapter.resumen(desde=desde, hasta=hasta, moneda=moneda)
    r_ings = adapter.resumen_ingresos(desde=desde, hasta=hasta, moneda=moneda)

    monedas = set(r_gastos.total_por_moneda) | set(r_ings.total_por_moneda)
    neto = {
        m: r_ings.total_por_moneda.get(m, 0) - r_gastos.total_por_moneda.get(m, 0)
        for m in monedas
    }
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "ingresos_por_moneda": r_ings.total_por_moneda,
        "gastos_por_moneda": r_gastos.total_por_moneda,
        "neto_por_moneda": neto,
        "cantidad_ingresos": r_ings.cantidad,
        "cantidad_gastos": r_gastos.cantidad,
        "gastos_por_categoria": r_gastos.total_por_categoria,
        "ingresos_por_categoria": r_ings.total_por_categoria,
    }


HANDLERS = {
    "registrar_ingreso": registrar_ingreso,
    "consultar_ingresos": consultar_ingresos,
    "resumen_financiero": resumen_financiero,
}
