from datetime import date

from pipeline.daily import run_daily, simulated_day
from pipeline.ingest import load_source
from pipeline.storage import LocalStorage


def test_simulated_day_keeps_month_and_day():
    assert simulated_day(date(2026, 10, 2), 2022) == date(2022, 10, 2)


def test_simulated_day_handles_leap_day():
    assert simulated_day(date(2024, 2, 29), 2022) == date(2022, 2, 28)


def test_run_daily_ingests_and_curates(tmp_path, sales_csv):
    storage = LocalStorage(str(tmp_path / "lake"))
    df = load_source(sales_csv)
    assert run_daily(storage, df, date(2022, 1, 31)) == (6, 6)
    assert storage.exists("raw/ventas/sale_date=2022-01-31/ventas.parquet")
    assert storage.exists("curated/ventas/sale_date=2022-01-31/ventas.parquet")
    assert storage.exists("curated/gastos_mensuales/month=2022-01/gastos.parquet")


def test_run_daily_is_idempotent(tmp_path, sales_csv):
    storage = LocalStorage(str(tmp_path / "lake"))
    df = load_source(sales_csv)
    for _ in range(2):
        run_daily(storage, df, date(2022, 1, 31))
    assert len(storage.list("raw/")) == 1
    assert len(storage.list("curated/ventas")) == 1


def test_run_daily_on_a_day_without_sales(tmp_path, sales_csv):
    storage = LocalStorage(str(tmp_path / "lake"))
    assert run_daily(storage, load_source(sales_csv), date(2022, 3, 1)) == (0, 0)
    assert storage.list("") == []
