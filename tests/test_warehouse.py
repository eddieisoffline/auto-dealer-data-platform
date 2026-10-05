from types import SimpleNamespace

import pytest

from pipeline.config import Settings
from pipeline.ingest import load_source
from pipeline.simulate import OPEX_COLUMNS, add_costs, build_monthly_tables
from pipeline.storage import LocalStorage
from pipeline.warehouse import (
    REQUIRED_PREFIXES,
    build_statements,
    refresh_warehouse,
    run_warehouse,
    split_statements,
)


class FakeClient:
    """Imita al cliente de BigQuery: guarda cada consulta recibida."""

    def __init__(self):
        self.queries = []

    def query(self, sql):
        self.queries.append(sql)
        return SimpleNamespace(result=lambda: None)


@pytest.fixture
def statements():
    return build_statements("mi-proyecto", "mi-bucket")


def by_kind(statements, kind):
    return [s for s in statements if s.startswith(f"CREATE OR REPLACE {kind}")]


# ---- SQL ------------------------------------------------------------------

def test_sql_has_three_external_three_tables_four_views(statements):
    assert len(by_kind(statements, "EXTERNAL TABLE")) == 3
    assert len(by_kind(statements, "TABLE")) == 3
    assert len(by_kind(statements, "VIEW")) == 4
    assert len(statements) == 10


def test_every_statement_is_idempotent_ddl(statements):
    assert all(s.startswith("CREATE OR REPLACE") for s in statements)


def test_order_is_external_then_tables_then_views(statements):
    kinds = [s.split()[3] for s in statements]  # EXTERNAL / TABLE / VIEW
    assert kinds == ["EXTERNAL"] * 3 + ["TABLE"] * 3 + ["VIEW"] * 4


def test_placeholders_are_fully_resolved(statements):
    joined = "\n".join(statements)
    assert "${" not in joined
    assert "mi-proyecto" in joined and "mi-bucket" in joined


def test_external_tables_read_the_curated_prefixes(statements):
    externals = "\n".join(by_kind(statements, "EXTERNAL TABLE"))
    for prefix in REQUIRED_PREFIXES:
        assert f"gs://mi-bucket/{prefix}/*" in externals


def test_split_statements_ignores_comments_and_blanks():
    sql = "-- encabezado\nSELECT 1;\n\n-- solo comentario\n;\nSELECT 2;\n-- cola\n"
    assert split_statements(sql) == ["SELECT 1", "SELECT 2"]


# ---- el SQL y la capa Python hablan el mismo idioma -------------------------

def test_kpi_view_uses_the_same_opex_as_the_simulation(statements):
    view = next(s for s in by_kind(statements, "VIEW") if "kpi_mensual" in s.splitlines()[0])
    for column in OPEX_COLUMNS:
        assert f"g.{column}" in view
    assert "utilidad_bruta - opex AS ebitda" in view
    assert "utilidad_bruta - opex - depreciacion - intereses - impuestos AS utilidad_neta" in view


def test_tables_select_columns_that_curated_actually_has(statements, sales_csv):
    ventas = add_costs(load_source(sales_csv))
    gastos, objetivos = build_monthly_tables(ventas)
    tables = {s.splitlines()[0]: s for s in by_kind(statements, "TABLE")}

    sql_ventas = next(v for k, v in tables.items() if "dealer_curated.ventas`" in k)
    for column in ("car_id", "date", "mes", "dealer_name", "dealer_region", "company",
                   "model", "price", "costo", "utilidad_bruta"):
        assert column in ventas.columns
        assert column in sql_ventas

    sql_gastos = next(v for k, v in tables.items() if "gastos_mensuales`" in k)
    for column in ("nomina", "renta", "marketing", "otros_gastos",
                   "depreciacion", "intereses", "impuestos"):
        assert column in gastos.columns
        assert column in sql_gastos

    sql_obj = next(v for k, v in tables.items() if "objetivos`" in k)
    assert "objetivo_ventas" in objetivos.columns and "objetivo_ventas" in sql_obj


# ---- ejecución --------------------------------------------------------------

def test_refresh_runs_every_statement_in_order(statements):
    client = FakeClient()
    assert refresh_warehouse(client, "mi-proyecto", "mi-bucket") == 10
    assert client.queries == statements


def seeded_lake(tmp_path):
    storage = LocalStorage(str(tmp_path / "lake"))
    for prefix in REQUIRED_PREFIXES:
        storage.write_bytes(f"{prefix}/x/archivo.parquet", b"datos")
    return storage


def cloud(**overrides):
    return Settings(backend="gcs", project="mi-proyecto", bucket="mi-bucket", **overrides)


def test_run_warehouse_happy_path(tmp_path):
    client = FakeClient()
    assert run_warehouse(cloud(), seeded_lake(tmp_path), client) == 10
    assert len(client.queries) == 10


def test_run_warehouse_requires_gcs_backend(tmp_path):
    with pytest.raises(ValueError, match="PIPELINE_BACKEND"):
        run_warehouse(Settings(backend="local"), seeded_lake(tmp_path), FakeClient())


def test_run_warehouse_requires_project(tmp_path):
    with pytest.raises(ValueError, match="PIPELINE_PROJECT"):
        run_warehouse(Settings(backend="gcs", bucket="b"), seeded_lake(tmp_path), FakeClient())


def test_run_warehouse_requires_bucket(tmp_path):
    with pytest.raises(ValueError, match="PIPELINE_BUCKET"):
        run_warehouse(Settings(backend="gcs", project="p"), seeded_lake(tmp_path), FakeClient())


def test_run_warehouse_refuses_an_empty_lake(tmp_path):
    client = FakeClient()
    empty = LocalStorage(str(tmp_path / "vacio"))
    with pytest.raises(RuntimeError, match="curate"):
        run_warehouse(cloud(), empty, client)
    assert client.queries == []  # no se ejecutó nada


def test_run_warehouse_names_what_is_missing(tmp_path):
    storage = LocalStorage(str(tmp_path / "lake"))
    storage.write_bytes("curated/ventas/x/a.parquet", b"datos")
    with pytest.raises(RuntimeError, match="gastos_mensuales"):
        run_warehouse(cloud(), storage, FakeClient())
