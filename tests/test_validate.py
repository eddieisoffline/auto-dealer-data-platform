from datetime import date

import pandas as pd
import pytest

from pipeline.ingest import ingest_day, load_source
from pipeline.simulate import add_costs, build_monthly_tables
from pipeline.storage import LocalStorage
from pipeline.validate import (
    ValidationError,
    ensure_valid,
    validate_curated,
    validate_monthly,
    validate_raw,
)


def names(issues):
    return {i.check for i in issues}


@pytest.fixture
def raw(sales_csv):
    return load_source(sales_csv)


@pytest.fixture
def curated(raw):
    return add_costs(raw)


@pytest.fixture
def monthly(curated):
    return build_monthly_tables(curated)


def test_clean_data_passes_every_layer(raw, curated, monthly):
    assert validate_raw(raw) == []
    assert validate_curated(curated, len(raw)) == []
    assert validate_monthly(*monthly) == []


# ---- raw ----------------------------------------------------------------

def test_raw_missing_column(raw):
    assert names(validate_raw(raw.drop(columns=["price"]))) == {"columnas"}


def test_raw_null_price(raw):
    bad = raw.copy()
    bad["price"] = bad["price"].astype(float)
    bad.loc[0, "price"] = float("nan")
    assert "nulos" in names(validate_raw(bad))


def test_raw_non_positive_and_huge_price(raw):
    bad = raw.copy()
    bad["price"] = bad["price"].astype(float)
    bad.loc[0, "price"] = -5.0
    bad.loc[1, "price"] = 2e7
    issues = validate_raw(bad)
    assert names(issues) == {"rango"} and len(issues) == 2


def test_raw_text_price(raw):
    bad = raw.copy()
    bad["price"] = bad["price"].astype(str)
    assert "tipo" in names(validate_raw(bad))


def test_raw_duplicate_car_id(raw):
    bad = raw.copy()
    bad.loc[1, "car_id"] = bad.loc[0, "car_id"]
    assert "duplicados" in names(validate_raw(bad))


def test_raw_blank_text(raw):
    bad = raw.copy()
    bad.loc[0, "dealer_name"] = "   "
    assert "vacios" in names(validate_raw(bad))


def test_raw_rejects_personal_data(raw):
    bad = raw.copy()
    bad["phone"] = 5551234
    assert "pii" in names(validate_raw(bad))


def test_raw_date_must_be_datetime(raw):
    bad = raw.copy()
    bad["date"] = bad["date"].astype(str)
    assert "tipo" in names(validate_raw(bad))


# ---- curated ------------------------------------------------------------

def test_curated_row_count_must_reconcile(raw, curated):
    assert "conciliacion" in names(validate_curated(curated, len(raw) + 1))


def test_curated_inconsistent_gross_profit(raw, curated):
    bad = curated.copy()
    bad.loc[0, "utilidad_bruta"] += 50
    assert "consistencia" in names(validate_curated(bad, len(raw)))


def test_curated_cost_above_price(raw, curated):
    bad = curated.copy()
    bad.loc[0, "costo"] = bad.loc[0, "price"] + 1
    assert "rango" in names(validate_curated(bad, len(raw)))


def test_curated_null_cost(raw, curated):
    bad = curated.copy()
    bad.loc[0, "costo"] = float("nan")
    assert "nulos" in names(validate_curated(bad, len(raw)))


def test_curated_margin_out_of_bounds(raw, curated):
    bad = curated.copy()
    bad["costo"] = (bad["price"] * 0.5).round(2)
    bad["utilidad_bruta"] = (bad["price"] - bad["costo"]).round(2)
    assert names(validate_curated(bad, len(raw))) == {"rango"}


# ---- tablas mensuales ---------------------------------------------------

def test_monthly_duplicate_keys(monthly):
    gastos, objetivos = monthly
    dup = pd.concat([gastos, gastos.iloc[:1]], ignore_index=True)
    assert "duplicados" in names(validate_monthly(dup, objetivos))


def test_monthly_negative_expense(monthly):
    gastos, objetivos = monthly
    bad = gastos.copy()
    bad.loc[0, "renta"] = -1.0
    assert "rango" in names(validate_monthly(bad, objetivos))


def test_monthly_non_positive_target(monthly):
    gastos, objetivos = monthly
    bad = objetivos.copy()
    bad.loc[0, "objetivo_ventas"] = 0.0
    assert "rango" in names(validate_monthly(gastos, bad))


def test_monthly_tables_must_cover_same_keys(monthly):
    gastos, objetivos = monthly
    assert "conciliacion" in names(validate_monthly(gastos, objetivos.iloc[1:]))


# ---- integración --------------------------------------------------------

def test_ensure_valid_message_lists_problems(raw):
    bad = raw.copy()
    bad["price"] = bad["price"].astype(float)
    bad.loc[0, "price"] = -1.0
    with pytest.raises(ValidationError, match="price <= 0"):
        ensure_valid(validate_raw(bad), "raw 2022-01-30")


def test_bad_batch_never_reaches_the_lake(tmp_path, raw):
    bad = raw.copy()
    bad["price"] = bad["price"].astype(float)
    bad.loc[0, "price"] = -1.0
    storage = LocalStorage(str(tmp_path / "lake"))
    with pytest.raises(ValidationError):
        ingest_day(bad, date(2022, 1, 30), storage)
    assert storage.list("raw/") == []
