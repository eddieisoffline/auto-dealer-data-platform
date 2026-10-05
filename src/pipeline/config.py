"""Configuración del pipeline, leída de variables de entorno."""
from __future__ import annotations

import os
from dataclasses import dataclass

# Columnas con datos personales: se eliminan en la ingesta, nunca llegan al lake.
PII_COLUMNS = ("customer_name", "phone", "gender", "annual_income")


@dataclass(frozen=True)
class Settings:
    backend: str = "local"                          # almacenamiento: "local" o "gcs"
    data_dir: str = "data"                          # raíz del lake con backend local
    bucket: str = ""                                # bucket con backend gcs
    project: str = ""                               # proyecto de GCP (para el warehouse)
    source: str = "kaggle"                          # origen de los datos: "kaggle" o "file"
    kaggle_dataset: str = "missionjee/car-sales-report"
    kaggle_file: str = ""                           # solo si el dataset trae varios CSV
    source_csv: str = "data/source/Car Sales.csv"   # ruta del CSV con source == "file"
    sim_year: int = 2022                            # año del dataset que se "reproduce" a diario

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            backend=os.getenv("PIPELINE_BACKEND", "local"),
            data_dir=os.getenv("PIPELINE_DATA_DIR", "data"),
            bucket=os.getenv("PIPELINE_BUCKET", ""),
            project=os.getenv("PIPELINE_PROJECT", ""),
            source=os.getenv("PIPELINE_SOURCE", "kaggle"),
            kaggle_dataset=os.getenv("PIPELINE_KAGGLE_DATASET", "missionjee/car-sales-report"),
            kaggle_file=os.getenv("PIPELINE_KAGGLE_FILE", ""),
            source_csv=os.getenv("PIPELINE_SOURCE_CSV", "data/source/Car Sales.csv"),
            sim_year=int(os.getenv("PIPELINE_SIM_YEAR", "2022")),
        )
