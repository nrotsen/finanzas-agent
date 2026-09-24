"""
Tests offline del agente usando un adapter en memoria.
Probamos que la lógica de tool use funciona sin tocar Sheets ni Anthropic.

Para correr los tests REALES contra Sheets, ver test_sheets_adapter.py.
"""
import uuid
from datetime import date
from typing import Optional

from src.adapters.base import (
    DataAdapter, Gasto, Vencimiento, Ingreso, Resumen,
)


class InMemoryAdapter(DataAdapter):
    def __init__(self):
        self.gastos: dict[str, Gasto] = {}
        self.vencimientos: dict[str, Vencimiento] = {}
        self.ingresos: dict[str, Ingreso] = {}
        self.hashes: set[str] = set()

    # ---------- Gastos ----------
    def insert_gasto(self, gasto: Gasto, hash_dedup: str = "") -> str:
        if not gasto.id:
            gasto.id = uuid.uuid4().hex[:12]
        self.gastos[gasto.id] = gasto
        if hash_dedup:
            self.hashes.add(hash_dedup)
        return gasto.id

    def query_gastos(self, **kwargs) -> list[Gasto]:
        out = list(self.gastos.values())
        if kwargs.get("desde"):
            out = [g for g in out if g.fecha >= kwargs["desde"]]
        if kwargs.get("hasta"):
            out = [g for g in out if g.fecha <= kwargs["hasta"]]
        if kwargs.get("categoria"):
            out = [g for g in out if g.categoria.lower() == kwargs["categoria"].lower()]
        if kwargs.get("moneda"):
            out = [g for g in out if g.moneda.upper() == kwargs["moneda"].upper()]
        if kwargs.get("descripcion_contiene"):
            s = kwargs["descripcion_contiene"].lower()
            out = [g for g in out if s in g.descripcion.lower()]
        out.sort(key=lambda x: x.fecha, reverse=True)
        return out[: kwargs.get("limit", 100)]

    def update_gasto(self, id: str, **fields) -> None:
        if id not in self.gastos:
            raise ValueError(f"no existe {id}")
        g = self.gastos[id]
        for k, v in fields.items():
            if hasattr(g, k):
                setattr(g, k, v)

    def delete_gasto(self, id: str) -> None:
        if id not in self.gastos:
            raise ValueError(f"no existe {id}")
        del self.gastos[id]

    def resumen(self, desde: date, hasta: date, moneda: Optional[str] = None) -> Resumen:
        gastos = self.query_gastos(desde=desde, hasta=hasta, moneda=moneda, limit=10000)
        return _resumen_de(desde, hasta, gastos, lambda x: (x.monto, x.moneda, x.categoria))

    def existe_por_hash(self, hash_dedup: str) -> bool:
        return hash_dedup in self.hashes

    def listar_categorias(self) -> list[str]:
        return sorted({g.categoria for g in self.gastos.values()})

    # ---------- Vencimientos ----------
    def insert_vencimiento(self, v: Vencimiento) -> str:
        if not v.id:
            v.id = uuid.uuid4().hex[:12]
        self.vencimientos[v.id] = v
        return v.id

    def query_vencimientos(self, **kwargs) -> list[Vencimiento]:
        out = list(self.vencimientos.values())
        if kwargs.get("estado"):
            out = [v for v in out if v.estado == kwargs["estado"]]
        if kwargs.get("desde"):
            out = [v for v in out if v.fecha_vencimiento >= kwargs["desde"]]
        if kwargs.get("hasta"):
            out = [v for v in out if v.fecha_vencimiento <= kwargs["hasta"]]
        if kwargs.get("categoria"):
            out = [v for v in out if v.categoria.lower() == kwargs["categoria"].lower()]
        out.sort(key=lambda v: v.fecha_vencimiento)
        return out[: kwargs.get("limit", 100)]

    def get_vencimiento(self, id: str) -> Optional[Vencimiento]:
        return self.vencimientos.get(id)

    def update_vencimiento(self, id: str, **fields) -> None:
        if id not in self.vencimientos:
            raise ValueError(f"no existe vencimiento {id}")
        v = self.vencimientos[id]
        for k, val in fields.items():
            if hasattr(v, k):
                setattr(v, k, val)

    def delete_vencimiento(self, id: str) -> None:
        if id not in self.vencimientos:
            raise ValueError(f"no existe vencimiento {id}")
        del self.vencimientos[id]

    # ---------- Ingresos ----------
    def insert_ingreso(self, i: Ingreso) -> str:
        if not i.id:
            i.id = uuid.uuid4().hex[:12]
        self.ingresos[i.id] = i
        return i.id

    def query_ingresos(self, **kwargs) -> list[Ingreso]:
        out = list(self.ingresos.values())
        if kwargs.get("desde"):
            out = [i for i in out if i.fecha >= kwargs["desde"]]
        if kwargs.get("hasta"):
            out = [i for i in out if i.fecha <= kwargs["hasta"]]
        if kwargs.get("categoria"):
            out = [i for i in out if i.categoria.lower() == kwargs["categoria"].lower()]
        if kwargs.get("moneda"):
            out = [i for i in out if i.moneda.upper() == kwargs["moneda"].upper()]
        out.sort(key=lambda x: x.fecha, reverse=True)
        return out[: kwargs.get("limit", 100)]

    def resumen_ingresos(self, desde: date, hasta: date, moneda: Optional[str] = None) -> Resumen:
        ings = self.query_ingresos(desde=desde, hasta=hasta, moneda=moneda, limit=10000)
        return _resumen_de(desde, hasta, ings, lambda x: (x.monto, x.moneda, x.categoria))


def _resumen_de(desde, hasta, items, getter) -> Resumen:
    total_moneda, total_cat = {}, {}
    for it in items:
        m, mon, cat = getter(it)
        total_moneda[mon] = total_moneda.get(mon, 0) + m
        total_cat.setdefault(cat, {})
        total_cat[cat][mon] = total_cat[cat].get(mon, 0) + m
    return Resumen(
        desde=desde, hasta=hasta,
        total_por_moneda=total_moneda,
        total_por_categoria=total_cat,
        cantidad=len(items),
    )


# ============================================================
# Tests: gastos
# ============================================================

def test_insert_and_query():
    a = InMemoryAdapter()
    g = Gasto(
        fecha=date(2026, 5, 15),
        monto=5000,
        moneda="ARS",
        categoria="supermercado",
        descripcion="coto",
        medio_pago="debito",
    )
    id_ = a.insert_gasto(g)
    assert id_
    results = a.query_gastos(categoria="supermercado")
    assert len(results) == 1
    assert results[0].monto == 5000


def test_resumen():
    a = InMemoryAdapter()
    for monto, cat in [(1000, "supermercado"), (2000, "supermercado"), (500, "transporte")]:
        a.insert_gasto(Gasto(
            fecha=date(2026, 5, 1),
            monto=monto, moneda="ARS",
            categoria=cat, descripcion="x", medio_pago="efectivo",
        ))
    r = a.resumen(date(2026, 5, 1), date(2026, 5, 31))
    assert r.total_por_moneda["ARS"] == 3500
    assert r.total_por_categoria["supermercado"]["ARS"] == 3000
    assert r.cantidad == 3


def test_update_and_delete():
    a = InMemoryAdapter()
    id_ = a.insert_gasto(Gasto(
        fecha=date(2026, 5, 1), monto=100, moneda="ARS",
        categoria="x", descripcion="y", medio_pago="efectivo",
    ))
    a.update_gasto(id_, monto=200)
    assert a.gastos[id_].monto == 200
    a.delete_gasto(id_)
    assert id_ not in a.gastos


def test_tools_handlers():
    """Prueba que los handlers de tools funcionan con el adapter."""
    from src.tools import HANDLERS

    a = InMemoryAdapter()
    res = HANDLERS["registrar_gasto"](
        a, monto=8500, descripcion="coto", categoria="supermercado",
        medio_pago="debito",
    )
    assert res["ok"]
    assert res["gasto"]["monto"] == 8500

    res = HANDLERS["consultar_gastos"](a, periodo="hoy")
    assert res["cantidad"] == 1

    res = HANDLERS["resumen"](a, periodo="este mes")
    assert res["total_por_moneda"]["ARS"] == 8500


# ============================================================
# Tests: vencimientos
# ============================================================

def test_vencimientos_crud():
    from src.tools import HANDLERS

    a = InMemoryAdapter()
    res = HANDLERS["agregar_vencimiento"](
        a,
        fecha_vencimiento="2026-06-05",
        monto_estimado=380000,
        categoria="alquiler",
        descripcion="alquiler depto",
        periodicidad="mensual",
    )
    assert res["ok"]
    venc_id = res["id"]

    res = HANDLERS["listar_vencimientos"](a, estado="pendiente")
    assert res["cantidad"] == 1
    assert res["vencimientos"][0]["categoria"] == "alquiler"

    res = HANDLERS["editar_vencimiento"](a, id=venc_id, monto_estimado=400000)
    assert res["ok"]
    assert a.vencimientos[venc_id].monto_estimado == 400000


def test_marcar_pagado_recurrente_genera_siguiente():
    """Al marcar pagado un vencimiento mensual, debe crear el gasto y el del mes que viene."""
    from src.tools import HANDLERS

    a = InMemoryAdapter()
    res = HANDLERS["agregar_vencimiento"](
        a,
        fecha_vencimiento="2026-05-05",
        monto_estimado=380000,
        categoria="alquiler",
        descripcion="alquiler depto",
        periodicidad="mensual",
    )
    venc_id = res["id"]

    res = HANDLERS["marcar_pagado"](
        a, id=venc_id, medio_pago="transferencia", monto_real=385000,
        fecha_pagado="2026-05-05",
    )
    assert res["ok"]
    # el gasto se creó
    assert res["gasto_id"] in a.gastos
    g = a.gastos[res["gasto_id"]]
    assert g.monto == 385000
    assert g.medio_pago == "transferencia"
    assert g.categoria == "alquiler"
    assert g.fuente == f"vencimiento:{venc_id}"
    # el vencimiento original quedó pagado
    assert a.vencimientos[venc_id].estado == "pagado"
    assert a.vencimientos[venc_id].gasto_id == res["gasto_id"]
    # se creó el del mes siguiente
    assert res["siguiente_vencimiento_id"]
    siguiente = a.vencimientos[res["siguiente_vencimiento_id"]]
    assert siguiente.fecha_vencimiento == date(2026, 6, 5)
    assert siguiente.monto_estimado == 385000
    assert siguiente.estado == "pendiente"


def test_marcar_pagado_unico_no_genera_siguiente():
    from src.tools import HANDLERS

    a = InMemoryAdapter()
    res = HANDLERS["agregar_vencimiento"](
        a, fecha_vencimiento="2026-05-20", monto_estimado=50000,
        categoria="extra", descripcion="préstamo amigo", periodicidad="unico",
    )
    venc_id = res["id"]
    res = HANDLERS["marcar_pagado"](a, id=venc_id, medio_pago="efectivo")
    assert res["ok"]
    assert res["siguiente_vencimiento_id"] is None
    assert len(a.vencimientos) == 1  # solo el original


def test_vencimientos_proximos():
    from src.tools import HANDLERS

    a = InMemoryAdapter()
    hoy = date.today()
    # uno en 2 días, otro en 30 días, uno vencido hace 1 día
    from dateutil.relativedelta import relativedelta
    HANDLERS["agregar_vencimiento"](
        a, fecha_vencimiento=(hoy + relativedelta(days=2)).isoformat(),
        monto_estimado=100, categoria="x", descripcion="cerca", periodicidad="unico",
    )
    HANDLERS["agregar_vencimiento"](
        a, fecha_vencimiento=(hoy + relativedelta(days=30)).isoformat(),
        monto_estimado=200, categoria="x", descripcion="lejos", periodicidad="unico",
    )
    HANDLERS["agregar_vencimiento"](
        a, fecha_vencimiento=(hoy - relativedelta(days=1)).isoformat(),
        monto_estimado=300, categoria="x", descripcion="vencido", periodicidad="unico",
    )

    res = HANDLERS["vencimientos_proximos"](a, dias=7)
    assert res["cantidad"] == 2  # el de 2 días y el vencido
    descripciones = {v["descripcion"] for v in res["vencimientos"]}
    assert descripciones == {"cerca", "vencido"}


# ============================================================
# Tests: ingresos
# ============================================================

def test_ingresos_crud():
    from src.tools import HANDLERS

    a = InMemoryAdapter()
    res = HANDLERS["registrar_ingreso"](
        a, monto=2500000, categoria="sueldo", descripcion="sueldo mayo",
        fecha="2026-05-05",
    )
    assert res["ok"]
    assert res["ingreso"]["monto"] == 2500000

    res = HANDLERS["consultar_ingresos"](a, periodo="mayo 2026")
    assert res["cantidad"] == 1


def test_resumen_financiero():
    from src.tools import HANDLERS

    a = InMemoryAdapter()
    HANDLERS["registrar_ingreso"](
        a, monto=2500000, categoria="sueldo", descripcion="sueldo",
        fecha="2026-05-05",
    )
    HANDLERS["registrar_gasto"](
        a, monto=300000, categoria="extra", descripcion="x",
        medio_pago="credito", fecha="2026-05-10",
    )
    HANDLERS["registrar_gasto"](
        a, monto=200000, categoria="comida", descripcion="y",
        medio_pago="debito", fecha="2026-05-12",
    )

    res = HANDLERS["resumen_financiero"](a, periodo="mayo 2026")
    assert res["ingresos_por_moneda"]["ARS"] == 2500000
    assert res["gastos_por_moneda"]["ARS"] == 500000
    assert res["neto_por_moneda"]["ARS"] == 2000000
    assert res["cantidad_ingresos"] == 1
    assert res["cantidad_gastos"] == 2
