"""Línea de comandos: python -m pipeline.cli ingest|backfill|curate|daily ..."""
from __future__ import annotations

import argparse
import logging
from datetime import date

import pandas as pd

from .config import Settings
from .curate import curate_range
from .daily import run_daily, simulated_day
from .ingest import backfill, ingest_day, load_source
from .kaggle_source import Downloader, download_dataset, fetch_source
from .storage import get_storage
from .warehouse import run_warehouse


def read_source(settings: Settings, download: Downloader = download_dataset) -> pd.DataFrame:
    """Origen de los datos: la API de Kaggle (por defecto) o un CSV local."""
    if settings.source == "kaggle":
        return fetch_source(settings.kaggle_dataset, settings.kaggle_file, download)
    if settings.source == "file":
        return load_source(settings.source_csv)
    raise ValueError(f"PIPELINE_SOURCE desconocido: {settings.source!r} (usa 'kaggle' o 'file')")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="ingiere las ventas de un día")
    p_ingest.add_argument("--date", required=True, type=date.fromisoformat)

    p_back = sub.add_parser("backfill", help="ingiere un rango de días")
    p_back.add_argument("--start", required=True, type=date.fromisoformat)
    p_back.add_argument("--end", required=True, type=date.fromisoformat)

    p_cur = sub.add_parser("curate", help="raw -> curated para un rango de días")
    p_cur.add_argument("--start", required=True, type=date.fromisoformat)
    p_cur.add_argument("--end", type=date.fromisoformat, help="por defecto igual a --start")

    sub.add_parser("warehouse", help="refresca BigQuery desde curated/ (tablas y vistas de KPIs)")

    p_daily = sub.add_parser("daily", help="ingesta + curated del día simulado")
    p_daily.add_argument(
        "--warehouse", action="store_true", help="al terminar, refresca también BigQuery"
    )
    p_daily.add_argument(
        "--date",
        type=date.fromisoformat,
        help="por defecto: hoy trasladado al año PIPELINE_SIM_YEAR",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = Settings.from_env()
    storage = get_storage(settings)

    if args.command == "curate":  # solo lee del lake: no necesita la fuente
        result = curate_range(storage, args.start, args.end or args.start)
        logging.info("curate: %d días, %d filas", len(result), sum(result.values()))
        return

    if args.command == "warehouse":  # tampoco necesita la fuente
        done = run_warehouse(settings, storage)
        logging.info("warehouse: %d sentencias ejecutadas", done)
        return

    df = read_source(settings)
    if args.command == "ingest":
        ingest_day(df, args.date, storage)
    elif args.command == "backfill":
        result = backfill(df, args.start, args.end, storage)
        logging.info("backfill: %d días, %d filas", len(result), sum(result.values()))
    else:  # daily
        day = args.date or simulated_day(date.today(), settings.sim_year)
        raw_rows, curated_rows = run_daily(storage, df, day)
        logging.info("daily %s: %d filas raw, %d filas curated", day, raw_rows, curated_rows)
        if args.warehouse:
            done = run_warehouse(settings, storage)
            logging.info("warehouse: %d sentencias ejecutadas", done)


if __name__ == "__main__":
    main()
