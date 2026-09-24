"""
Interfaz común para cualquier backend de datos.

Cualquier adapter nuevo (Postgres, Airtable, Notion) debe implementar
esta clase. El agente no sabe ni le importa qué hay abajo.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional


@dataclass
class Gasto:
    fecha: date
    monto: float
    moneda: str           # ARS, USD
    categoria: str
    descripcion: str
    medio_pago: str       # efectivo, debito, credito, transferencia, mp
    fuente: str = "manual"  # manual, email:<banco>, pdf:<tarjeta>, vencimiento:<id>
    id: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fecha"] = self.fecha.isoformat()
        return d


@dataclass
class Vencimiento:
    fecha_vencimiento: date
    monto_estimado: float
    moneda: str
    categoria: str
    descripcion: str
    periodicidad: str         # "mensual" | "unico"
    medio_pago: str = ""      # vacío hasta que se paga
    estado: str = "pendiente"  # "pendiente" | "pagado"
    gasto_id: Optional[str] = None      # id del gasto creado al marcar pagado
    fecha_pagado: Optional[date] = None
    id: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fecha_vencimiento"] = self.fecha_vencimiento.isoformat()
        d["fecha_pagado"] = self.fecha_pagado.isoformat() if self.fecha_pagado else None
        return d


@dataclass
class Ingreso:
    fecha: date
    monto: float
    moneda: str
    categoria: str       # sueldo, freelance, venta, regalo, cashback, reembolso, otros
    descripcion: str
    fuente: str = "manual"
    id: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fecha"] = self.fecha.isoformat()
        return d


@dataclass
class Resumen:
    desde: date
    hasta: date
    total_por_moneda: dict[str, float]
    total_por_categoria: dict[str, dict[str, float]]  # categoria -> moneda -> monto
    cantidad: int

    def to_dict(self) -> dict:
        return {
            "desde": self.desde.isoformat(),
            "hasta": self.hasta.isoformat(),
            "total_por_moneda": self.total_por_moneda,
            "total_por_categoria": self.total_por_categoria,
            "cantidad": self.cantidad,
        }


class DataAdapter(ABC):
    """Contrato que todo backend de datos debe cumplir."""

    # ---------- Gastos ----------
    @abstractmethod
    def insert_gasto(self, gasto: Gasto) -> str:
        """Inserta y devuelve el id asignado."""
        ...

    @abstractmethod
    def query_gastos(
        self,
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        categoria: Optional[str] = None,
        moneda: Optional[str] = None,
        descripcion_contiene: Optional[str] = None,
        limit: int = 100,
    ) -> list[Gasto]:
        ...

    @abstractmethod
    def update_gasto(self, id: str, **fields) -> None:
        ...

    @abstractmethod
    def delete_gasto(self, id: str) -> None:
        ...

    @abstractmethod
    def resumen(
        self,
        desde: date,
        hasta: date,
        moneda: Optional[str] = None,
    ) -> Resumen:
        ...

    @abstractmethod
    def existe_por_hash(self, hash_dedup: str) -> bool:
        """Para deduplicar al ingerir emails o PDFs."""
        ...

    @abstractmethod
    def listar_categorias(self) -> list[str]:
        """Categorías únicas que ya aparecieron en los gastos."""
        ...

    # ---------- Vencimientos ----------
    @abstractmethod
    def insert_vencimiento(self, vencimiento: Vencimiento) -> str:
        ...

    @abstractmethod
    def query_vencimientos(
        self,
        estado: Optional[str] = None,
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        categoria: Optional[str] = None,
        limit: int = 100,
    ) -> list[Vencimiento]:
        ...

    @abstractmethod
    def get_vencimiento(self, id: str) -> Optional[Vencimiento]:
        ...

    @abstractmethod
    def update_vencimiento(self, id: str, **fields) -> None:
        ...

    @abstractmethod
    def delete_vencimiento(self, id: str) -> None:
        ...

    # ---------- Ingresos ----------
    @abstractmethod
    def insert_ingreso(self, ingreso: Ingreso) -> str:
        ...

    @abstractmethod
    def query_ingresos(
        self,
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        categoria: Optional[str] = None,
        moneda: Optional[str] = None,
        limit: int = 100,
    ) -> list[Ingreso]:
        ...

    @abstractmethod
    def resumen_ingresos(
        self,
        desde: date,
        hasta: date,
        moneda: Optional[str] = None,
    ) -> Resumen:
        ...
