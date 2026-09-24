"""Utilidades de fechas para parsear "este mes", "marzo", "última semana", etc."""
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def parse_periodo(periodo: str, hoy: date | None = None) -> tuple[date, date]:
    """
    Devuelve (desde, hasta) para un período expresado en lenguaje natural.

    Soporta:
      - "hoy", "ayer"
      - "esta semana", "ultima semana"
      - "este mes", "mes pasado"
      - "este año", "año pasado"
      - nombres de mes: "marzo", "marzo 2026"
      - rangos ISO: "2026-03-01:2026-03-31"
    """
    hoy = hoy or date.today()
    p = periodo.lower().strip().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")

    if p == "hoy":
        return hoy, hoy
    if p == "ayer":
        d = hoy - timedelta(days=1)
        return d, d
    if p in ("esta semana", "semana"):
        ini = hoy - timedelta(days=hoy.weekday())
        return ini, hoy
    if p in ("ultima semana", "semana pasada"):
        ini = hoy - timedelta(days=hoy.weekday() + 7)
        fin = ini + timedelta(days=6)
        return ini, fin
    if p in ("este mes", "mes"):
        return hoy.replace(day=1), hoy
    if p in ("mes pasado", "ultimo mes"):
        primero_este = hoy.replace(day=1)
        fin = primero_este - timedelta(days=1)
        ini = fin.replace(day=1)
        return ini, fin
    if p in ("este ano", "ano"):
        return hoy.replace(month=1, day=1), hoy
    if p in ("ano pasado", "ultimo ano"):
        return date(hoy.year - 1, 1, 1), date(hoy.year - 1, 12, 31)

    # Rango ISO
    if ":" in p:
        a, b = p.split(":")
        return date.fromisoformat(a.strip()), date.fromisoformat(b.strip())

    # Mes con o sin año
    partes = p.split()
    if partes[0] in MESES:
        mes = MESES[partes[0]]
        anio = int(partes[1]) if len(partes) > 1 else hoy.year
        ini = date(anio, mes, 1)
        fin = (ini + relativedelta(months=1)) - timedelta(days=1)
        return ini, fin

    raise ValueError(f"No entiendo el período: {periodo}")
