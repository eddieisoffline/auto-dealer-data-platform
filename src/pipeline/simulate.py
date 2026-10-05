"""Simulación de costos, gastos y objetivos (funciones puras, sin I/O).

Los datos de Kaggle no traen costos, así que se generan de forma sintética.
Todo valor aleatorio se deriva de un hash estable de su clave de negocio
(modelo, venta, concesionaria + mes), no de un generador con estado. Por eso
el resultado es idéntico sin importar el orden ni el lote en que se procese:
reprocesar un día o hacer un backfill da exactamente los mismos números.
"""
from __future__ import annotations

import hashlib

import pandas as pd

SEED = 42
TAX_RATE = 0.30  # simplificación: 30% sobre la utilidad antes de impuestos

# Gastos mensuales como fracción de las ventas del mes (rango min, max)
EXPENSE_RANGES = {
    "nomina": (0.030, 0.045),
    "renta": (0.010, 0.020),
    "marketing": (0.005, 0.015),
    "otros_gastos": (0.005, 0.012),
    "depreciacion": (0.003, 0.006),
    "intereses": (0.002, 0.008),
}
OPEX_COLUMNS = ["nomina", "renta", "marketing", "otros_gastos"]


def _uniform(lo: float, hi: float, *keys: object) -> float:
    """Número en [lo, hi) determinista a partir de las claves dadas."""
    raw = "|".join(str(k) for k in (SEED, *keys)).encode()
    u = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") / 2**64
    return lo + (hi - lo) * u


def add_costs(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega costo, utilidad_bruta y mes a un lote de ventas."""
    out = df.copy()
    if "car_id" in out.columns:
        keys = out["car_id"].tolist()
    else:  # sin identificador, se usa la posición dentro del lote
        keys = list(range(len(out)))

    # Margen fijo por modelo (8%–20%) más una variación pequeña por venta (±1%)
    margins = {
        (c, m): _uniform(0.08, 0.20, "margen", c, m)
        for c, m in out[["company", "model"]].drop_duplicates().itertuples(index=False)
    }
    margen = [margins[(c, m)] for c, m in zip(out["company"], out["model"])]
    ruido = [_uniform(-0.01, 0.01, "ruido", k) for k in keys]

    factor = pd.Series([1 - (a + b) for a, b in zip(margen, ruido)], index=out.index)
    out["costo"] = (out["price"] * factor).round(2)
    out["utilidad_bruta"] = (out["price"] - out["costo"]).round(2)
    out["mes"] = out["date"].dt.to_period("M").dt.to_timestamp()
    return out


def build_monthly_tables(ventas: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gastos y objetivos mensuales por concesionaria a partir de ventas con costo."""
    base = ventas.groupby(["dealer_name", "mes"], as_index=False).agg(
        ventas=("price", "sum"), utilidad_bruta=("utilidad_bruta", "sum")
    )
    labels = base["mes"].dt.strftime("%Y-%m").tolist()
    dealers = base["dealer_name"].tolist()

    gastos = base[["dealer_name", "mes"]].copy()
    for concepto, (lo, hi) in EXPENSE_RANGES.items():
        pct = pd.Series(
            [_uniform(lo, hi, concepto, d, m) for d, m in zip(dealers, labels)],
            index=base.index,
        )
        gastos[concepto] = (base["ventas"] * pct).round(2)

    opex = gastos[OPEX_COLUMNS].sum(axis=1)
    antes_impuestos = (
        base["utilidad_bruta"] - opex - gastos["depreciacion"] - gastos["intereses"]
    )
    gastos["impuestos"] = (antes_impuestos.clip(lower=0) * TAX_RATE).round(2)

    objetivos = base[["dealer_name", "mes"]].copy()
    factor = pd.Series(
        [_uniform(0.90, 1.15, "objetivo", d, m) for d, m in zip(dealers, labels)],
        index=base.index,
    )
    objetivos["objetivo_ventas"] = (base["ventas"] * factor).round(2)
    return gastos, objetivos
