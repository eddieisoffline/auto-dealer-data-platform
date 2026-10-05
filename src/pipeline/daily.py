"""Ejecución diaria simulada.

El dataset es estático, así que cada día real se "reproduce" el mismo día del
calendario en `sim_year`: hoy 15 de marzo carga las ventas del 15 de marzo de
2022. Así el job programado siempre trae datos nuevos sin cambiar nada.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from .curate import curate_range
from .ingest import ingest_day
from .storage import Storage


def simulated_day(today: date, sim_year: int) -> date:
    """Mismo día y mes de `today`, en el año simulado (29 de febrero -> 28)."""
    try:
        return today.replace(year=sim_year)
    except ValueError:
        return date(sim_year, 2, 28)


def run_daily(storage: Storage, df: pd.DataFrame, day: date) -> tuple[int, int]:
    """Ingesta (con validación) y curated de un día. Devuelve (filas raw, filas curated)."""
    raw_rows = ingest_day(df, day, storage)
    curated_rows = curate_range(storage, day, day)[day.isoformat()]
    return raw_rows, curated_rows
