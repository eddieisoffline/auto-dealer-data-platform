import pandas as pd

from pipeline.ingest import load_source
from pipeline.simulate import (
    EXPENSE_RANGES,
    OPEX_COLUMNS,
    TAX_RATE,
    add_costs,
    build_monthly_tables,
)


def test_costs_are_deterministic(sales_csv):
    df = load_source(sales_csv)
    pd.testing.assert_frame_equal(add_costs(df), add_costs(df))


def test_costs_do_not_depend_on_batch(sales_csv):
    """Un día procesado solo da lo mismo que dentro del dataset completo."""
    df = load_source(sales_csv)
    full = add_costs(df).set_index("car_id")
    one_day = add_costs(df[df["date"] == df["date"].min()]).set_index("car_id")
    pd.testing.assert_frame_equal(full.loc[one_day.index], one_day)


def test_gross_profit_and_margin_range(sales_csv):
    out = add_costs(load_source(sales_csv))
    assert (out["utilidad_bruta"] - (out["price"] - out["costo"])).abs().max() < 0.011
    margin = out["utilidad_bruta"] / out["price"]
    assert margin.between(0.06, 0.22).all()  # 8%–20% más el ruido de ±1%


def test_same_model_has_stable_margin(sales_csv):
    out = add_costs(load_source(sales_csv))
    per_model = (out["utilidad_bruta"] / out["price"]).groupby(
        [out["company"], out["model"]]
    )
    assert (per_model.max() - per_model.min()).max() < 0.021


def test_monthly_tables_shape_and_ranges(sales_csv):
    ventas = add_costs(load_source(sales_csv))
    gastos, objetivos = build_monthly_tables(ventas)

    assert len(gastos) == len(objetivos) == 4  # 2 concesionarias x 2 meses
    assert set(EXPENSE_RANGES) <= set(gastos.columns)
    assert (gastos[list(EXPENSE_RANGES) + ["impuestos"]] >= 0).all().all()

    base = ventas.groupby(["dealer_name", "mes"], as_index=False).agg(
        v=("price", "sum"), ub=("utilidad_bruta", "sum")
    )
    merged = base.merge(objetivos, on=["dealer_name", "mes"]).merge(
        gastos, on=["dealer_name", "mes"]
    )
    ratio = merged["objetivo_ventas"] / merged["v"]
    assert ratio.between(0.899, 1.151).all()

    # El impuesto es la tasa sobre la utilidad antes de impuestos (o 0 si es negativa)
    antes = (
        merged["ub"]
        - merged[OPEX_COLUMNS].sum(axis=1)
        - merged["depreciacion"]
        - merged["intereses"]
    )
    esperado = (antes.clip(lower=0) * TAX_RATE).round(2)
    assert (merged["impuestos"] - esperado).abs().max() < 0.011


def test_monthly_tables_ignore_row_order(sales_csv):
    ventas = add_costs(load_source(sales_csv))
    a, _ = build_monthly_tables(ventas)
    b, _ = build_monthly_tables(ventas.sample(frac=1, random_state=3))
    key = ["dealer_name", "mes"]
    pd.testing.assert_frame_equal(
        a.sort_values(key).reset_index(drop=True),
        b.sort_values(key).reset_index(drop=True),
    )
