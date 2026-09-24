"""
Placeholder para el adapter de DynamoDB (fase 2: agentes multi-tenant).

Layout sugerido de la tabla:
  PK: gasto#{id}              SK: meta
  GSI1PK: fecha#{YYYY-MM}     GSI1SK: {YYYY-MM-DD}#{id}
  GSI2PK: cat#{categoria}     GSI2SK: {YYYY-MM-DD}#{id}

Atributos: monto, moneda, descripcion, medio_pago, fuente, tags, hash_dedup
"""
from datetime import date
from typing import Optional

from .base import DataAdapter, Gasto, Vencimiento, Ingreso, Resumen


class DynamoAdapter(DataAdapter):
    def __init__(self, table_name: str, region: str = "us-east-1"):
        # import boto3 acá adentro para que no sea dependencia obligatoria
        # mientras estés solo en Sheets
        import boto3
        self.table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    # Gastos
    def insert_gasto(self, gasto: Gasto) -> str:
        raise NotImplementedError("Fase 2")

    def query_gastos(self, **kwargs) -> list[Gasto]:
        raise NotImplementedError("Fase 2")

    def update_gasto(self, id: str, **fields) -> None:
        raise NotImplementedError("Fase 2")

    def delete_gasto(self, id: str) -> None:
        raise NotImplementedError("Fase 2")

    def resumen(self, desde: date, hasta: date, moneda: Optional[str] = None) -> Resumen:
        raise NotImplementedError("Fase 2")

    def existe_por_hash(self, hash_dedup: str) -> bool:
        raise NotImplementedError("Fase 2")

    def listar_categorias(self) -> list[str]:
        raise NotImplementedError("Fase 2")

    # Vencimientos
    def insert_vencimiento(self, vencimiento: Vencimiento) -> str:
        raise NotImplementedError("Fase 2")

    def query_vencimientos(self, **kwargs) -> list[Vencimiento]:
        raise NotImplementedError("Fase 2")

    def get_vencimiento(self, id: str) -> Optional[Vencimiento]:
        raise NotImplementedError("Fase 2")

    def update_vencimiento(self, id: str, **fields) -> None:
        raise NotImplementedError("Fase 2")

    def delete_vencimiento(self, id: str) -> None:
        raise NotImplementedError("Fase 2")

    # Ingresos
    def insert_ingreso(self, ingreso: Ingreso) -> str:
        raise NotImplementedError("Fase 2")

    def query_ingresos(self, **kwargs) -> list[Ingreso]:
        raise NotImplementedError("Fase 2")

    def resumen_ingresos(self, desde: date, hasta: date, moneda: Optional[str] = None) -> Resumen:
        raise NotImplementedError("Fase 2")
