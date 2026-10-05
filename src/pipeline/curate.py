"""Capa curated: lee raw/, agrega costos simulados y arma las tablas mensuales.

    raw/ventas/sale_date=D/            -> curated/ventas/sale_date=D/
    curated/ventas (todo el mes M)     -> curated/gastos_mensuales/month=M/
                                          curated/objetivos/month=M/

Cada paso sobrescribe su salida, así que es idempotente.
"""
from __future__ import annotations

import io
import logging
from datetime import date, timedelta

import pandas as pd

from .ingest import partition_path
from .simulate import add_costs, build_monthly_tables
from .storage import Storage
from .validate import ensure_valid, validate_curated, validate_monthly

log = logging.getLogger(__name__)

CURATED_VENTAS = "curated/ventas"
CURATED_GASTOS = "curated/gastos_mensuales"
CURATED_OBJETIVOS = "curated/objetivos"


def _read(storage: Storage, path: str) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(storage.read_bytes(path)))


def _write(storage: Storage, path: str, df: pd.DataFrame) -> None:
    buf = io.BytesIO()
    # Marcas de tiempo en microsegundos: es lo que BigQuery lee sin ambigüedad
    df.to_parquet(buf, index=False, coerce_timestamps="us", allow_truncated_timestamps=True)
    storage.write_bytes(path, buf.getvalue())


def curated_partition(day: date) -> str:
    return f"{CURATED_VENTAS}/sale_date={day.isoformat()}/ventas.parquet"


def curate_day(storage: Storage, day: date) -> int:
    """raw -> curated para un día. Devuelve filas escritas (0 si no hay raw)."""
    raw_path = partition_path(day)
    if not storage.exists(raw_path):
        log.info("sin raw para %s, se omite", day)
        return 0
    raw = _read(storage, raw_path)
    curated = add_costs(raw)
    ensure_valid(validate_curated(curated, len(raw)), f"curated {day}")
    _write(storage, curated_partition(day), curated)
    log.info("curated %s: %d filas", day, len(curated))
    return len(curated)


def build_month(storage: Storage, year: int, month: int) -> int:
    """Gastos y objetivos del mes a partir de las ventas curadas disponibles."""
    key = f"{year:04d}-{month:02d}"
    files = storage.list(f"{CURATED_VENTAS}/sale_date={key}")
    if not files:
        return 0
    ventas = pd.concat([_read(storage, f) for f in files], ignore_index=True)
    gastos, objetivos = build_monthly_tables(ventas)
    ensure_valid(validate_monthly(gastos, objetivos), f"tablas mensuales {key}")
    _write(storage, f"{CURATED_GASTOS}/month={key}/gastos.parquet", gastos)
    _write(storage, f"{CURATED_OBJETIVOS}/month={key}/objetivos.parquet", objetivos)
    log.info("tablas mensuales %s: %d concesionarias", key, len(gastos))
    return len(gastos)


def curate_range(storage: Storage, start: date, end: date) -> dict[str, int]:
    if end < start:
        raise ValueError("end no puede ser anterior a start")
    days: dict[str, int] = {}
    months: set[tuple[int, int]] = set()
    day = start
    while day <= end:
        rows = curate_day(storage, day)
        days[day.isoformat()] = rows
        if rows:
            months.add((day.year, day.month))
        day += timedelta(days=1)
    for year, month in sorted(months):
        build_month(storage, year, month)
    return days
