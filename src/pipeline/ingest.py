"""Ingesta incremental simulada: una partición por día de venta.

El dataset de origen es estático; "ingerir un día" significa extraer solo las
ventas de esa fecha. Cada ejecución sobrescribe su partición, por lo que es
idempotente: correr dos veces la misma fecha no duplica filas.
"""
from __future__ import annotations

import io
import logging
from datetime import date, timedelta
from typing import BinaryIO

import pandas as pd

from .config import PII_COLUMNS
from .storage import Storage
from .validate import ensure_valid, validate_raw

log = logging.getLogger(__name__)

RAW_PREFIX = "raw/ventas"
REQUIRED_COLUMNS = {"date", "dealer_name", "company", "model", "price"}


def load_source(path: str | BinaryIO) -> pd.DataFrame:
    """Lee el CSV de origen desde una ruta o un archivo en memoria."""
    df = pd.read_csv(path)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    # En el dataset de Kaggle el precio viene como "price_($)"
    df = df.rename(columns={"price_($)": "price"})
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas en la fuente: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df.drop(columns=[c for c in PII_COLUMNS if c in df.columns])


def partition_path(day: date) -> str:
    return f"{RAW_PREFIX}/sale_date={day.isoformat()}/ventas.parquet"


def ingest_day(df: pd.DataFrame, day: date, storage: Storage) -> int:
    """Escribe la partición del día y devuelve el número de filas."""
    chunk = df[df["date"] == pd.Timestamp(day)]
    if chunk.empty:
        log.info("sin ventas para %s, no se escribe partición", day)
        return 0
    ensure_valid(validate_raw(chunk), f"raw {day}")  # un lote malo nunca entra al lake
    buf = io.BytesIO()
    chunk.to_parquet(buf, index=False)
    storage.write_bytes(partition_path(day), buf.getvalue())
    log.info("partición %s escrita: %d filas", day, len(chunk))
    return len(chunk)


def backfill(df: pd.DataFrame, start: date, end: date, storage: Storage) -> dict[str, int]:
    if end < start:
        raise ValueError("end no puede ser anterior a start")
    result: dict[str, int] = {}
    day = start
    while day <= end:
        result[day.isoformat()] = ingest_day(df, day, storage)
        day += timedelta(days=1)
    return result
