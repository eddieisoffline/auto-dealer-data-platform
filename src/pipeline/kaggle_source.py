"""Fuente de datos: descarga del dataset desde la API de Kaggle.

Cada ejecución consulta la API, descarga el dataset a un directorio temporal
y lo carga en memoria. Los datos personales se eliminan al cargar (ver
`ingest.load_source`), así que nunca llegan al lake.

Credenciales: variable de entorno KAGGLE_API_TOKEN (en Cloud Run se inyecta
desde Secret Manager) o el archivo ~/.kaggle/access_token.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Callable

import pandas as pd

from .ingest import load_source

log = logging.getLogger(__name__)

Downloader = Callable[[str, str], None]


def download_dataset(dataset: str, dest: str) -> None:
    """Descarga y descomprime `dataset` (owner/slug) en `dest` con la API de Kaggle."""
    # Import tardío: el paquete es opcional y la autenticación ocurre al usarlo.
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(dataset, path=dest, unzip=True, quiet=True)


def fetch_source(
    dataset: str, filename: str = "", download: Downloader = download_dataset
) -> pd.DataFrame:
    """Descarga el dataset y devuelve su CSV cargado y sin datos personales."""
    with tempfile.TemporaryDirectory() as tmp:
        log.info("descargando %s desde Kaggle", dataset)
        download(dataset, tmp)
        csvs = sorted(Path(tmp).rglob("*.csv"))
        found = [p.name for p in csvs]

        chosen = [p for p in csvs if p.name == filename] if filename else csvs
        if not chosen:
            raise FileNotFoundError(
                f"no hay un CSV{' llamado ' + repr(filename) if filename else ''} "
                f"en {dataset}; archivos encontrados: {found}"
            )
        if len(chosen) > 1:
            raise ValueError(
                f"{dataset} trae varios CSV {found}; "
                "define PIPELINE_KAGGLE_FILE con el nombre del que quieres usar"
            )
        return load_source(str(chosen[0]))
