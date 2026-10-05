import shutil
from pathlib import Path

import pytest

from pipeline.cli import read_source
from pipeline.config import Settings
from pipeline.kaggle_source import fetch_source


def fake_download(sales_csv, names, nested=True):
    """Simula la API: deja los CSV indicados (ya descomprimidos) en el destino."""
    calls = []

    def download(dataset, dest):
        calls.append(dataset)
        folder = Path(dest) / "unzipped" if nested else Path(dest)
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            shutil.copy(sales_csv, folder / name)

    download.calls = calls
    return download


def test_fetch_source_loads_the_only_csv_without_personal_data(sales_csv):
    df = fetch_source("owner/data", download=fake_download(sales_csv, ["cars.csv"]))
    assert len(df) == 24
    assert "price" in df.columns
    assert not {"customer_name", "phone", "gender", "annual_income"} & set(df.columns)


def test_fetch_source_requests_the_given_dataset(sales_csv):
    download = fake_download(sales_csv, ["cars.csv"])
    fetch_source("missionjee/car-sales-report", download=download)
    assert download.calls == ["missionjee/car-sales-report"]


def test_several_csv_require_a_file_name(sales_csv):
    download = fake_download(sales_csv, ["a.csv", "b.csv"])
    with pytest.raises(ValueError, match="PIPELINE_KAGGLE_FILE"):
        fetch_source("owner/data", download=download)
    assert len(fetch_source("owner/data", "b.csv", download=download)) == 24


def test_dataset_without_csv(sales_csv):
    with pytest.raises(FileNotFoundError):
        fetch_source("owner/data", download=fake_download(sales_csv, []))


def test_unknown_file_name_lists_what_was_found(sales_csv):
    download = fake_download(sales_csv, ["a.csv"])
    with pytest.raises(FileNotFoundError, match="a.csv"):
        fetch_source("owner/data", "otro.csv", download=download)


def test_read_source_uses_kaggle_by_default(sales_csv):
    download = fake_download(sales_csv, ["cars.csv"])
    settings = Settings(kaggle_dataset="owner/data")
    assert len(read_source(settings, download)) == 24
    assert download.calls == ["owner/data"]


def test_read_source_from_local_file(sales_csv):
    assert len(read_source(Settings(source="file", source_csv=sales_csv))) == 24


def test_read_source_rejects_unknown_origin():
    with pytest.raises(ValueError, match="PIPELINE_SOURCE"):
        read_source(Settings(source="ftp"))
