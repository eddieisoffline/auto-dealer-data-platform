from datetime import date

import pandas as pd
import pytest

from pipeline.ingest import backfill, ingest_day, load_source, partition_path
from pipeline.storage import LocalStorage


@pytest.fixture
def source_csv(tmp_path):
    df = pd.DataFrame(
        {
            "Car_id": [1, 2, 3, 4],
            "Date": ["2022-01-01", "2022-01-01", "2022-01-02", "2022-01-04"],
            "Customer Name": ["a", "b", "c", "d"],
            "Gender": ["M", "F", "M", "F"],
            "Annual Income": [1, 2, 3, 4],
            "Dealer_Name": ["A", "B", "A", "B"],
            "Company": ["Ford", "Nissan", "Ford", "Nissan"],
            "Model": ["m1", "m2", "m1", "m2"],
            "Price ($)": [100, 200, 300, 400],
            "Phone": [1, 2, 3, 4],
        }
    )
    path = tmp_path / "source.csv"
    df.to_csv(path, index=False)
    return str(path)


def test_load_source_removes_pii(source_csv):
    df = load_source(source_csv)
    assert not {"customer_name", "phone", "gender", "annual_income"} & set(df.columns)
    assert "price" in df.columns


def test_ingest_day_writes_partition(tmp_path, source_csv):
    storage = LocalStorage(str(tmp_path / "lake"))
    df = load_source(source_csv)
    assert ingest_day(df, date(2022, 1, 1), storage) == 2
    assert storage.exists(partition_path(date(2022, 1, 1)))


def test_ingest_is_idempotent(tmp_path, source_csv):
    storage = LocalStorage(str(tmp_path / "lake"))
    df = load_source(source_csv)
    for _ in range(3):
        ingest_day(df, date(2022, 1, 1), storage)
    assert len(storage.list("raw/ventas")) == 1
    stored = pd.read_parquet(tmp_path / "lake" / partition_path(date(2022, 1, 1)))
    assert len(stored) == 2


def test_empty_day_writes_nothing(tmp_path, source_csv):
    storage = LocalStorage(str(tmp_path / "lake"))
    df = load_source(source_csv)
    assert ingest_day(df, date(2022, 1, 3), storage) == 0
    assert storage.list("raw/ventas") == []


def test_backfill_range(tmp_path, source_csv):
    storage = LocalStorage(str(tmp_path / "lake"))
    df = load_source(source_csv)
    result = backfill(df, date(2022, 1, 1), date(2022, 1, 4), storage)
    assert sum(result.values()) == 4
    assert len(storage.list("raw/ventas")) == 3  # el 3 de enero no tiene ventas


def test_backfill_rejects_inverted_range(tmp_path, source_csv):
    storage = LocalStorage(str(tmp_path / "lake"))
    df = load_source(source_csv)
    with pytest.raises(ValueError):
        backfill(df, date(2022, 1, 5), date(2022, 1, 1), storage)


def test_missing_columns_raise(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"Date": ["2022-01-01"]}).to_csv(path, index=False)
    with pytest.raises(ValueError):
        load_source(str(path))
