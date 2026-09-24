"""
Tools de vencimientos (cuentas a pagar).

Marcar como pagado crea el gasto correspondiente y, si era recurrente
mensual, genera automáticamente el vencimiento del mes siguiente.
"""
from datetime import date

from dateutil.relativedelta import relativedelta

from ..adapters import DataAdapter, Gasto, Vencimiento
from .date_utils import parse_periodo


TOOLS_SCHEMA = [
    {
        "name": "agregar_vencimiento",
        "description": (
            "Registra un vencimiento futuro (cuenta a pagar). Usar cuando el "
            "usuario dice 'me vence X el día Y', 'tengo que pagar Z', o cuando "
            "describe un gasto fijo recurrente (alquiler, tarjeta, internet)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha_vencimiento": {
                    "type": "string",
                    "description": "Fecha de vencimiento en YYYY-MM-DD.",
                },
                "monto_estimado": {
                    "type": "number",
                    "description": "Monto esperado. Si no se sabe, usar 0 y editarlo después.",
                },
                "moneda": {"type": "string", "enum": ["ARS", "USD"], "default": "ARS"},
                "categoria": {
                    "type": "string",
                    "description": (
                        "Categoría del gasto que se va a generar al pagar. "
                        "Para fijos, usar las categorías fijas habituales del usuario."
                    ),
                },
                "descripcion": {"type": "string"},
                "periodicidad": {
                    "type": "string",
                    "enum": ["mensual", "unico"],
                    "default": "unico",
                    "description": (
                        "Mensual: al marcar pagado se genera automáticamente "
                        "el del mes que viene. Unico: cuota suelta, no se regenera."
                    ),
                },
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["fecha_vencimiento", "monto_estimado", "categoria", "descripcion"],
        },
    },
    {
        "name": "listar_vencimientos",
        "description": (
            "Lista vencimientos filtrados por estado y/o período. Usar para "
            "'qué tengo pendiente', 'qué vence este mes', 'qué ya pagué'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "estado": {
                    "type": "string",
                    "enum": ["pendiente", "pagado"],
                    "description": "Default: pendiente.",
                },
                "periodo": {
                    "type": "string",
                    "description": "Período opcional (ver consultar_gastos).",
                },
                "categoria": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "vencimientos_proximos",
        "description": (
            "Lista vencimientos pendientes que vencen en los próximos N días "
            "(incluye los ya vencidos no pagados). Usar para alertar al usuario "
            "o cuando pregunte 'qué tengo cerca'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {"type": "integer", "default": 7},
            },
        },
    },
    {
        "name": "marcar_pagado",
        "description": (
            "Marca un vencimiento como pagado. Crea automáticamente el gasto "
            "correspondiente y, si era mensual, genera el vencimiento del mes "
            "siguiente. REQUIERE medio_pago — si el usuario no lo aclaró, "
            "preguntale antes de llamar a esta tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "id del vencimiento"},
                "medio_pago": {
                    "type": "string",
                    "enum": ["efectivo", "debito", "credito", "transferencia", "mp"],
                },
                "monto_real": {
                    "type": "number",
                    "description": "Monto real pagado si difiere del estimado. Omitir si coincide.",
                },
                "fecha_pagado": {
                    "type": "string",
                    "description": "Fecha en que se pagó (YYYY-MM-DD). Default: hoy.",
                },
            },
            "required": ["id", "medio_pago"],
        },
    },
    {
        "name": "editar_vencimiento",
        "description": "Edita un vencimiento pendiente (monto, fecha, descripción, etc).",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "fecha_vencimiento": {"type": "string"},
                "monto_estimado": {"type": "number"},
                "categoria": {"type": "string"},
                "descripcion": {"type": "string"},
                "periodicidad": {"type": "string", "enum": ["mensual", "unico"]},
            },
            "required": ["id"],
        },
    },
    {
        "name": "borrar_vencimiento",
        "description": "Borra un vencimiento por id. Confirmar con el usuario antes.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
]


# ============================================================
# HANDLERS
# ============================================================

def agregar_vencimiento(adapter: DataAdapter, **kwargs) -> dict:
    v = Vencimiento(
        fecha_vencimiento=date.fromisoformat(kwargs["fecha_vencimiento"]),
        monto_estimado=float(kwargs["monto_estimado"]),
        moneda=kwargs.get("moneda", "ARS"),
        categoria=kwargs["categoria"],
        descripcion=kwargs["descripcion"],
        periodicidad=kwargs.get("periodicidad", "unico"),
        tags=kwargs.get("tags", []),
    )
    id_ = adapter.insert_vencimiento(v)
    return {"ok": True, "id": id_, "vencimiento": v.to_dict()}


def listar_vencimientos(adapter: DataAdapter, **kwargs) -> dict:
    desde = hasta = None
    if kwargs.get("periodo"):
        desde, hasta = parse_periodo(kwargs["periodo"])
    vencs = adapter.query_vencimientos(
        estado=kwargs.get("estado", "pendiente"),
        desde=desde,
        hasta=hasta,
        categoria=kwargs.get("categoria"),
        limit=kwargs.get("limit", 50),
    )
    return {
        "cantidad": len(vencs),
        "vencimientos": [v.to_dict() for v in vencs],
    }


def vencimientos_proximos(adapter: DataAdapter, **kwargs) -> dict:
    dias = int(kwargs.get("dias", 7))
    hoy = date.today()
    limite = hoy + relativedelta(days=dias)
    vencs = adapter.query_vencimientos(estado="pendiente", hasta=limite, limit=100)
    # incluye los ya vencidos no pagados (fecha < hoy con estado pendiente)
    return {
        "cantidad": len(vencs),
        "vencimientos": [
            {
                **v.to_dict(),
                "dias_para_vencer": (v.fecha_vencimiento - hoy).days,
                "vencido": v.fecha_vencimiento < hoy,
            }
            for v in vencs
        ],
    }


def marcar_pagado(adapter: DataAdapter, **kwargs) -> dict:
    venc = adapter.get_vencimiento(kwargs["id"])
    if not venc:
        return {"error": f"No existe vencimiento {kwargs['id']}"}
    if venc.estado == "pagado":
        return {"error": f"Vencimiento {venc.id} ya está pagado (gasto {venc.gasto_id})"}

    fecha_pago = (
        date.fromisoformat(kwargs["fecha_pagado"])
        if kwargs.get("fecha_pagado")
        else date.today()
    )
    monto = float(kwargs["monto_real"]) if kwargs.get("monto_real") is not None else venc.monto_estimado

    gasto = Gasto(
        fecha=fecha_pago,
        monto=monto,
        moneda=venc.moneda,
        categoria=venc.categoria,
        descripcion=venc.descripcion,
        medio_pago=kwargs["medio_pago"],
        fuente=f"vencimiento:{venc.id}",
        tags=list(venc.tags),
    )
    gasto_id = adapter.insert_gasto(gasto)

    adapter.update_vencimiento(
        venc.id,
        estado="pagado",
        gasto_id=gasto_id,
        fecha_pagado=fecha_pago,
        medio_pago=kwargs["medio_pago"],
    )

    siguiente_id = None
    if venc.periodicidad == "mensual":
        siguiente = Vencimiento(
            fecha_vencimiento=venc.fecha_vencimiento + relativedelta(months=1),
            monto_estimado=monto,  # usamos el monto real como nueva estimación
            moneda=venc.moneda,
            categoria=venc.categoria,
            descripcion=venc.descripcion,
            periodicidad="mensual",
            tags=list(venc.tags),
        )
        siguiente_id = adapter.insert_vencimiento(siguiente)

    return {
        "ok": True,
        "gasto_id": gasto_id,
        "vencimiento_id": venc.id,
        "siguiente_vencimiento_id": siguiente_id,
        "siguiente_fecha": (venc.fecha_vencimiento + relativedelta(months=1)).isoformat()
        if siguiente_id else None,
    }


def editar_vencimiento(adapter: DataAdapter, **kwargs) -> dict:
    id_ = kwargs.pop("id")
    if "fecha_vencimiento" in kwargs:
        kwargs["fecha_vencimiento"] = date.fromisoformat(kwargs["fecha_vencimiento"])
    adapter.update_vencimiento(id_, **kwargs)
    return {"ok": True, "id": id_}


def borrar_vencimiento(adapter: DataAdapter, **kwargs) -> dict:
    adapter.delete_vencimiento(kwargs["id"])
    return {"ok": True, "id": kwargs["id"]}


HANDLERS = {
    "agregar_vencimiento": agregar_vencimiento,
    "listar_vencimientos": listar_vencimientos,
    "vencimientos_proximos": vencimientos_proximos,
    "marcar_pagado": marcar_pagado,
    "editar_vencimiento": editar_vencimiento,
    "borrar_vencimiento": borrar_vencimiento,
}
