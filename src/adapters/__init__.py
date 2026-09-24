from .base import DataAdapter, Gasto, Vencimiento, Ingreso, Resumen


def __getattr__(name):
    """Lazy import — Sheets/Dynamo solo se cargan si se usan."""
    if name == "SheetsAdapter":
        from .sheets import SheetsAdapter
        return SheetsAdapter
    if name == "DynamoAdapter":
        from .dynamo import DynamoAdapter
        return DynamoAdapter
    raise AttributeError(name)


__all__ = [
    "DataAdapter", "Gasto", "Vencimiento", "Ingreso", "Resumen",
    "SheetsAdapter", "DynamoAdapter",
]
