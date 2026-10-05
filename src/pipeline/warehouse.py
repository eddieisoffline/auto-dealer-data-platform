"""Warehouse: refresca BigQuery a partir del Parquet curado del data lake.

El trabajo lo hacen tres archivos SQL (ELT): tablas externas sobre `curated/`,
tablas nativas tipadas en `dealer_curated` y vistas de KPIs en `dealer_marts`,
que es lo que consume Power BI. Cada sentencia es CREATE OR REPLACE, así que el
refresco es idempotente.

El cliente de BigQuery se inyecta (cualquier objeto con `.query(sql).result()`),
de modo que la lógica se prueba sin red ni credenciales.
"""
from __future__ import annotations

import logging
from importlib import resources
from string import Template
from typing import Protocol

from .config import Settings
from .storage import Storage

log = logging.getLogger(__name__)

SQL_FILES = ("01_external_tables.sql", "02_tables.sql", "03_marts.sql")
REQUIRED_PREFIXES = ("curated/ventas", "curated/gastos_mensuales", "curated/objetivos")


class QueryClient(Protocol):
    def query(self, sql: str): ...


def split_statements(sql: str) -> list[str]:
    """Separa un script en sentencias, sin comentarios de línea ni trozos vacíos."""
    statements = []
    for chunk in sql.split(";"):
        lines = [line for line in chunk.splitlines() if not line.strip().startswith("--")]
        statement = "\n".join(lines).strip()
        if statement:
            statements.append(statement)
    return statements


def build_statements(project: str, bucket: str) -> list[str]:
    """Sentencias SQL listas para ejecutar, en orden, con proyecto y bucket resueltos."""
    statements: list[str] = []
    for name in SQL_FILES:
        text = (resources.files("pipeline") / "sql" / name).read_text(encoding="utf-8")
        # substitute() falla si queda un marcador sin valor: mejor un error que SQL roto
        statements.extend(split_statements(Template(text).substitute(project=project, bucket=bucket)))
    return statements


def refresh_warehouse(client: QueryClient, project: str, bucket: str) -> int:
    statements = build_statements(project, bucket)
    for number, sql in enumerate(statements, start=1):
        log.info("warehouse %d/%d: %s", number, len(statements), sql.splitlines()[0])
        client.query(sql).result()
    return len(statements)


def run_warehouse(settings: Settings, storage: Storage, client: QueryClient | None = None) -> int:
    """Valida el entorno y refresca el warehouse. Devuelve las sentencias ejecutadas."""
    if settings.backend != "gcs":
        raise ValueError("el warehouse se carga desde Cloud Storage: usa PIPELINE_BACKEND=gcs")
    if not settings.project:
        raise ValueError("define PIPELINE_PROJECT con el ID del proyecto de GCP")
    if not settings.bucket:
        raise ValueError("define PIPELINE_BUCKET con el bucket del data lake")

    missing = [p for p in REQUIRED_PREFIXES if not storage.list(p + "/")]
    if missing:
        raise RuntimeError(
            f"no hay datos curados en {missing}: ejecuta antes 'curate' (o 'daily') "
            "para que existan las tablas externas"
        )

    if client is None:
        from google.cloud import bigquery  # import tardío: dependencia opcional

        client = bigquery.Client(project=settings.project)
    return refresh_warehouse(client, settings.project, settings.bucket)
