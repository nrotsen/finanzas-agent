"""
Adapter de Google Sheets.

Pestañas:
  gastos:        A id | B fecha | C monto | D moneda | E categoria
                 F descripcion | G medio_pago | H fuente | I tags | J hash_dedup
  vencimientos:  A id | B fecha_vencimiento | C monto_estimado | D moneda
                 E categoria | F descripcion | G medio_pago | H periodicidad
                 I estado | J gasto_id | K fecha_pagado | L tags
  ingresos:      A id | B fecha | C monto | D moneda | E categoria
                 F descripcion | G fuente | H tags

La primera fila son headers. El id es un hex random de 12 chars.
"""
from __future__ import annotations
import json
import os
import uuid
from datetime import date
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .base import DataAdapter, Gasto, Vencimiento, Ingreso, Resumen

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

GASTOS_SHEET = "gastos"
GASTOS_HEADERS = ["id", "fecha", "monto", "moneda", "categoria",
                  "descripcion", "medio_pago", "fuente", "tags", "hash_dedup"]
GASTOS_RANGE_END = "J"

VENC_SHEET = "vencimientos"
VENC_HEADERS = ["id", "fecha_vencimiento", "monto_estimado", "moneda", "categoria",
                "descripcion", "medio_pago", "periodicidad", "estado",
                "gasto_id", "fecha_pagado", "tags"]
VENC_RANGE_END = "L"

ING_SHEET = "ingresos"
ING_HEADERS = ["id", "fecha", "monto", "moneda", "categoria",
               "descripcion", "fuente", "tags"]
ING_RANGE_END = "H"


class SheetsAdapter(DataAdapter):
    def __init__(
        self,
        spreadsheet_id: Optional[str] = None,
        creds_path: Optional[str] = None,
    ):
        self.spreadsheet_id = spreadsheet_id or os.environ["GOOGLE_SHEETS_ID"]
        creds = self._load_credentials(creds_path)
        self.svc = build("sheets", "v4", credentials=creds).spreadsheets()
        self._ensure_sheets()

    @staticmethod
    def _load_credentials(creds_path: Optional[str]):
        """
        Carga credenciales del service account. Prioriza, en orden:
          1. GOOGLE_SHEETS_CREDS_JSON (string JSON inline — útil en Lambda)
          2. creds_path arg / GOOGLE_SHEETS_CREDS_PATH (archivo en disco)
        """
        inline = os.environ.get("GOOGLE_SHEETS_CREDS_JSON")
        if inline:
            info = json.loads(inline)
            return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        path = creds_path or os.environ.get("GOOGLE_SHEETS_CREDS_PATH")
        if not path:
            raise RuntimeError(
                "Faltan credenciales de Google: definí GOOGLE_SHEETS_CREDS_JSON "
                "(inline) o GOOGLE_SHEETS_CREDS_PATH (archivo)."
            )
        return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)

    # ---------- bootstrap ----------

    def _ensure_sheets(self) -> None:
        meta = self.svc.get(spreadsheetId=self.spreadsheet_id).execute()
        existing = {s["properties"]["title"] for s in meta["sheets"]}
        requests = []
        for name in (GASTOS_SHEET, VENC_SHEET, ING_SHEET):
            if name not in existing:
                requests.append({"addSheet": {"properties": {"title": name}}})
        if requests:
            self.svc.batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests},
            ).execute()
        self._ensure_headers(GASTOS_SHEET, GASTOS_HEADERS, GASTOS_RANGE_END)
        self._ensure_headers(VENC_SHEET, VENC_HEADERS, VENC_RANGE_END)
        self._ensure_headers(ING_SHEET, ING_HEADERS, ING_RANGE_END)

    def _ensure_headers(self, sheet: str, headers: list[str], end: str) -> None:
        cur = self.svc.values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet}!A1:{end}1",
        ).execute().get("values", [])
        if not cur or cur[0] != headers:
            self.svc.values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet}!A1:{end}1",
                valueInputOption="RAW",
                body={"values": [headers]},
            ).execute()

    # ---------- helpers genéricos ----------

    def _read_rows(self, sheet: str, end: str) -> list[list[str]]:
        res = self.svc.values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet}!A2:{end}",
        ).execute()
        return res.get("values", [])

    def _append_row(self, sheet: str, end: str, row: list[str]) -> None:
        self.svc.values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet}!A:{end}",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

    def _update_row(self, sheet: str, end: str, idx: int, row: list[str]) -> None:
        self.svc.values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet}!A{idx}:{end}{idx}",
            valueInputOption="USER_ENTERED",
            body={"values": [row]},
        ).execute()

    def _delete_row(self, sheet: str, idx: int) -> None:
        meta = self.svc.get(spreadsheetId=self.spreadsheet_id).execute()
        sheet_id = next(
            s["properties"]["sheetId"]
            for s in meta["sheets"]
            if s["properties"]["title"] == sheet
        )
        self.svc.batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={
                "requests": [{
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": idx - 1,
                            "endIndex": idx,
                        }
                    }
                }]
            },
        ).execute()

    def _find_row_index(self, sheet: str, end: str, id: str) -> Optional[int]:
        rows = self._read_rows(sheet, end)
        for i, row in enumerate(rows):
            if row and row[0] == id:
                return i + 2  # header en fila 1, enumerate desde 0
        return None

    # ---------- Gastos: row mapping ----------

    def _row_to_gasto(self, row: list[str]) -> Gasto:
        row = row + [""] * (10 - len(row))
        return Gasto(
            id=row[0] or None,
            fecha=date.fromisoformat(row[1]) if row[1] else date.today(),
            monto=float(row[2] or 0),
            moneda=row[3] or "ARS",
            categoria=row[4] or "otros",
            descripcion=row[5] or "",
            medio_pago=row[6] or "efectivo",
            fuente=row[7] or "manual",
            tags=[t for t in (row[8] or "").split(",") if t],
        )

    def _gasto_to_row(self, g: Gasto, hash_dedup: str = "") -> list[str]:
        return [
            g.id or "",
            g.fecha.isoformat(),
            f"{g.monto:.2f}",
            g.moneda,
            g.categoria,
            g.descripcion,
            g.medio_pago,
            g.fuente,
            ",".join(g.tags),
            hash_dedup,
        ]

    # ---------- Gastos: API ----------

    def insert_gasto(self, gasto: Gasto, hash_dedup: str = "") -> str:
        if not gasto.id:
            gasto.id = uuid.uuid4().hex[:12]
        self._append_row(GASTOS_SHEET, GASTOS_RANGE_END,
                         self._gasto_to_row(gasto, hash_dedup))
        return gasto.id

    def query_gastos(
        self,
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        categoria: Optional[str] = None,
        moneda: Optional[str] = None,
        descripcion_contiene: Optional[str] = None,
        limit: int = 100,
    ) -> list[Gasto]:
        gastos = [self._row_to_gasto(r) for r in self._read_rows(GASTOS_SHEET, GASTOS_RANGE_END) if r]
        out = []
        for g in gastos:
            if desde and g.fecha < desde:
                continue
            if hasta and g.fecha > hasta:
                continue
            if categoria and g.categoria.lower() != categoria.lower():
                continue
            if moneda and g.moneda.upper() != moneda.upper():
                continue
            if descripcion_contiene and descripcion_contiene.lower() not in g.descripcion.lower():
                continue
            out.append(g)
        out.sort(key=lambda x: x.fecha, reverse=True)
        return out[:limit]

    def update_gasto(self, id: str, **fields) -> None:
        idx = self._find_row_index(GASTOS_SHEET, GASTOS_RANGE_END, id)
        if not idx:
            raise ValueError(f"No existe gasto con id {id}")
        rows = self._read_rows(GASTOS_SHEET, GASTOS_RANGE_END)
        cur = self._row_to_gasto(rows[idx - 2])
        for k, v in fields.items():
            if hasattr(cur, k):
                setattr(cur, k, v)
        self._update_row(GASTOS_SHEET, GASTOS_RANGE_END, idx, self._gasto_to_row(cur))

    def delete_gasto(self, id: str) -> None:
        idx = self._find_row_index(GASTOS_SHEET, GASTOS_RANGE_END, id)
        if not idx:
            raise ValueError(f"No existe gasto con id {id}")
        self._delete_row(GASTOS_SHEET, idx)

    def resumen(self, desde: date, hasta: date, moneda: Optional[str] = None) -> Resumen:
        gastos = self.query_gastos(desde=desde, hasta=hasta, moneda=moneda, limit=10000)
        return _resumen_from_items(
            desde, hasta, gastos,
            get_monto=lambda x: x.monto,
            get_moneda=lambda x: x.moneda,
            get_categoria=lambda x: x.categoria,
        )

    def existe_por_hash(self, hash_dedup: str) -> bool:
        rows = self._read_rows(GASTOS_SHEET, GASTOS_RANGE_END)
        return any(len(r) >= 10 and r[9] == hash_dedup for r in rows)

    def listar_categorias(self) -> list[str]:
        rows = self._read_rows(GASTOS_SHEET, GASTOS_RANGE_END)
        cats = {row[4] for row in rows if len(row) > 4 and row[4]}
        return sorted(cats)

    # ---------- Vencimientos: row mapping ----------

    def _row_to_venc(self, row: list[str]) -> Vencimiento:
        row = row + [""] * (12 - len(row))
        return Vencimiento(
            id=row[0] or None,
            fecha_vencimiento=date.fromisoformat(row[1]) if row[1] else date.today(),
            monto_estimado=float(row[2] or 0),
            moneda=row[3] or "ARS",
            categoria=row[4] or "otros",
            descripcion=row[5] or "",
            medio_pago=row[6] or "",
            periodicidad=row[7] or "unico",
            estado=row[8] or "pendiente",
            gasto_id=row[9] or None,
            fecha_pagado=date.fromisoformat(row[10]) if row[10] else None,
            tags=[t for t in (row[11] or "").split(",") if t],
        )

    def _venc_to_row(self, v: Vencimiento) -> list[str]:
        return [
            v.id or "",
            v.fecha_vencimiento.isoformat(),
            f"{v.monto_estimado:.2f}",
            v.moneda,
            v.categoria,
            v.descripcion,
            v.medio_pago,
            v.periodicidad,
            v.estado,
            v.gasto_id or "",
            v.fecha_pagado.isoformat() if v.fecha_pagado else "",
            ",".join(v.tags),
        ]

    # ---------- Vencimientos: API ----------

    def insert_vencimiento(self, vencimiento: Vencimiento) -> str:
        if not vencimiento.id:
            vencimiento.id = uuid.uuid4().hex[:12]
        self._append_row(VENC_SHEET, VENC_RANGE_END, self._venc_to_row(vencimiento))
        return vencimiento.id

    def query_vencimientos(
        self,
        estado: Optional[str] = None,
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        categoria: Optional[str] = None,
        limit: int = 100,
    ) -> list[Vencimiento]:
        vencs = [self._row_to_venc(r) for r in self._read_rows(VENC_SHEET, VENC_RANGE_END) if r]
        out = []
        for v in vencs:
            if estado and v.estado != estado:
                continue
            if desde and v.fecha_vencimiento < desde:
                continue
            if hasta and v.fecha_vencimiento > hasta:
                continue
            if categoria and v.categoria.lower() != categoria.lower():
                continue
            out.append(v)
        out.sort(key=lambda x: x.fecha_vencimiento)
        return out[:limit]

    def get_vencimiento(self, id: str) -> Optional[Vencimiento]:
        idx = self._find_row_index(VENC_SHEET, VENC_RANGE_END, id)
        if not idx:
            return None
        rows = self._read_rows(VENC_SHEET, VENC_RANGE_END)
        return self._row_to_venc(rows[idx - 2])

    def update_vencimiento(self, id: str, **fields) -> None:
        idx = self._find_row_index(VENC_SHEET, VENC_RANGE_END, id)
        if not idx:
            raise ValueError(f"No existe vencimiento con id {id}")
        rows = self._read_rows(VENC_SHEET, VENC_RANGE_END)
        cur = self._row_to_venc(rows[idx - 2])
        for k, v in fields.items():
            if hasattr(cur, k):
                setattr(cur, k, v)
        self._update_row(VENC_SHEET, VENC_RANGE_END, idx, self._venc_to_row(cur))

    def delete_vencimiento(self, id: str) -> None:
        idx = self._find_row_index(VENC_SHEET, VENC_RANGE_END, id)
        if not idx:
            raise ValueError(f"No existe vencimiento con id {id}")
        self._delete_row(VENC_SHEET, idx)

    # ---------- Ingresos: row mapping ----------

    def _row_to_ingreso(self, row: list[str]) -> Ingreso:
        row = row + [""] * (8 - len(row))
        return Ingreso(
            id=row[0] or None,
            fecha=date.fromisoformat(row[1]) if row[1] else date.today(),
            monto=float(row[2] or 0),
            moneda=row[3] or "ARS",
            categoria=row[4] or "otros",
            descripcion=row[5] or "",
            fuente=row[6] or "manual",
            tags=[t for t in (row[7] or "").split(",") if t],
        )

    def _ingreso_to_row(self, i: Ingreso) -> list[str]:
        return [
            i.id or "",
            i.fecha.isoformat(),
            f"{i.monto:.2f}",
            i.moneda,
            i.categoria,
            i.descripcion,
            i.fuente,
            ",".join(i.tags),
        ]

    # ---------- Ingresos: API ----------

    def insert_ingreso(self, ingreso: Ingreso) -> str:
        if not ingreso.id:
            ingreso.id = uuid.uuid4().hex[:12]
        self._append_row(ING_SHEET, ING_RANGE_END, self._ingreso_to_row(ingreso))
        return ingreso.id

    def query_ingresos(
        self,
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        categoria: Optional[str] = None,
        moneda: Optional[str] = None,
        limit: int = 100,
    ) -> list[Ingreso]:
        ings = [self._row_to_ingreso(r) for r in self._read_rows(ING_SHEET, ING_RANGE_END) if r]
        out = []
        for i in ings:
            if desde and i.fecha < desde:
                continue
            if hasta and i.fecha > hasta:
                continue
            if categoria and i.categoria.lower() != categoria.lower():
                continue
            if moneda and i.moneda.upper() != moneda.upper():
                continue
            out.append(i)
        out.sort(key=lambda x: x.fecha, reverse=True)
        return out[:limit]

    def resumen_ingresos(
        self,
        desde: date,
        hasta: date,
        moneda: Optional[str] = None,
    ) -> Resumen:
        ings = self.query_ingresos(desde=desde, hasta=hasta, moneda=moneda, limit=10000)
        return _resumen_from_items(
            desde, hasta, ings,
            get_monto=lambda x: x.monto,
            get_moneda=lambda x: x.moneda,
            get_categoria=lambda x: x.categoria,
        )


def _resumen_from_items(desde, hasta, items, get_monto, get_moneda, get_categoria) -> Resumen:
    total_moneda: dict[str, float] = {}
    total_cat: dict[str, dict[str, float]] = {}
    for it in items:
        m, mon, cat = get_monto(it), get_moneda(it), get_categoria(it)
        total_moneda[mon] = total_moneda.get(mon, 0) + m
        total_cat.setdefault(cat, {})
        total_cat[cat][mon] = total_cat[cat].get(mon, 0) + m
    return Resumen(
        desde=desde,
        hasta=hasta,
        total_por_moneda=total_moneda,
        total_por_categoria=total_cat,
        cantidad=len(items),
    )
