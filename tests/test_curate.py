from datetime import date

import pandas as pd
import pytest

from pipeline.curate import build_month, curate_day, curate_range, curated_partition
from pipeline.ingest import backfill, load_source
from pipeline.storage import LocalStorage


@pytest.fixture
def lake(tmp_path, sales_csv):
    storage = LocalStorage(str(tmp_path / "lake"))
    backfill(load_source(sales_csv), date(2022, 1, 30), date(2022, 2, 2), storage)
    return storage, tmp_path / "lake"


def test_curate_day_writes_costs(lake):
    storage, root = lake
    assert curate_day(storage, date(2022, 1, 30)) == 6
    out = pd.read_parquet(root / curated_partition(date(2022, 1, 30)))
    assert {"costo", "utilidad_bruta", "mes"} <= set(out.columns)


def test_curate_day_without_raw_is_skipped(lake):
    storage, _ = lake
    assert curate_day(storage, date(2022, 3, 1)) == 0


def test_curate_range_builds_monthly_tables(lake):
    storage, root = lake
    result = curate_range(storage, date(2022, 1, 30), date(2022, 2, 2))
    assert sum(result.values()) == 24
    assert (root / "curated/gastos_mensuales/month=2022-01/gastos.parquet").exists()
    assert (root / "curated/objetivos/month=2022-02/objetivos.parquet").exists()


def test_curate_is_idempotent(lake):
    storage, root = lake
    curate_range(storage, date(2022, 1, 30), date(2022, 2, 2))
    path = root / "curated/gastos_mensuales/month=2022-01/gastos.parquet"
    first = pd.read_parquet(path)
    curate_range(storage, date(2022, 1, 30), date(2022, 2, 2))
    pd.testing.assert_frame_equal(first, pd.read_parquet(path))
    assert len(storage.list("curated/ventas")) == 4


def test_month_without_data_writes_nothing(lake):
    storage, _ = lake
    assert build_month(storage, 2023, 5) == 0
    assert storage.list("curated/gastos_mensuales") == []


def test_curate_range_rejects_inverted_range(lake):
    storage, _ = lake
    with pytest.raises(ValueError):
        curate_range(storage, date(2022, 2, 2), date(2022, 1, 30))


def test_local_list_uses_prefix_semantics(lake):
    storage, _ = lake
    jan = storage.list("raw/ventas/sale_date=2022-01")
    assert len(jan) == 2 and all("2022-01" in p for p in jan)
