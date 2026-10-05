"""Validaciones de calidad entre capas.

Son funciones puras: reciben un DataFrame y devuelven la lista de incidencias
(vacía si todo está bien). `ensure_valid` convierte las incidencias en una
excepción, de modo que un lote defectuoso detiene el pipeline y no se promueve
a la siguiente capa. En Cloud Run eso hace fallar la ejecución del job, que
queda visible en sus logs y alertas.

    ingesta  -> validate_raw      (antes de escribir en raw/)
    curated  -> validate_curated  (antes de escribir en curated/)
    mensual  -> validate_monthly  (antes de escribir gastos y objetivos)
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import PII_COLUMNS
from .simulate import EXPENSE_RANGES

REQUIRED_RAW = ["date", "dealer_name", "company", "model", "price"]
TEXT_COLUMNS = ["dealer_name", "company", "model"]
MAX_PRICE = 10_000_000          # tope de sensatez para un precio de venta
MARGIN_BOUNDS = (0.05, 0.25)    # la simulación genera 7%–21%
ROUNDING_TOLERANCE = 0.011      # costo y utilidad se redondean a centavos
EXPENSE_COLUMNS = list(EXPENSE_RANGES) + ["impuestos"]


@dataclass(frozen=True)
class Issue:
    check: str
    detail: str

    def __str__(self) -> str:
        return f"{self.check}: {self.detail}"


class ValidationError(Exception):
    def __init__(self, context: str, issues: list[Issue]):
        self.context = context
        self.issues = issues
        super().__init__(
            f"{context}: {len(issues)} problema(s) -> " + "; ".join(str(i) for i in issues)
        )


def ensure_valid(issues: list[Issue], context: str) -> None:
    if issues:
        raise ValidationError(context, issues)


def validate_raw(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []

    missing = [c for c in REQUIRED_RAW if c not in df.columns]
    if missing:
        return [Issue("columnas", f"faltan {missing}")]

    pii = [c for c in PII_COLUMNS if c in df.columns]
    if pii:
        issues.append(Issue("pii", f"columnas con datos personales en raw: {pii}"))

    for col in REQUIRED_RAW:
        nulls = int(df[col].isna().sum())
        if nulls:
            issues.append(Issue("nulos", f"{col}: {nulls} fila(s)"))

    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        issues.append(Issue("tipo", "date no es una fecha"))

    for col in TEXT_COLUMNS:
        blank = int(df[col].dropna().astype(str).str.strip().eq("").sum())
        if blank:
            issues.append(Issue("vacios", f"{col}: {blank} valor(es) en blanco"))

    if "car_id" in df.columns:
        dups = int(df["car_id"].duplicated().sum())
        if dups:
            issues.append(Issue("duplicados", f"car_id repetido en {dups} fila(s)"))

    if not pd.api.types.is_numeric_dtype(df["price"]):
        issues.append(Issue("tipo", "price no es numérico"))
    else:
        non_positive = int((df["price"] <= 0).sum())
        if non_positive:
            issues.append(Issue("rango", f"price <= 0 en {non_positive} fila(s)"))
        too_high = int((df["price"] > MAX_PRICE).sum())
        if too_high:
            issues.append(Issue("rango", f"price > {MAX_PRICE} en {too_high} fila(s)"))

    return issues


def validate_curated(df: pd.DataFrame, raw_rows: int) -> list[Issue]:
    required = ["price", "costo", "utilidad_bruta", "mes"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return [Issue("columnas", f"faltan {missing}")]

    issues: list[Issue] = []

    if len(df) != raw_rows:
        issues.append(Issue("conciliacion", f"raw tiene {raw_rows} filas y curated {len(df)}"))

    for col in required:
        nulls = int(df[col].isna().sum())
        if nulls:
            issues.append(Issue("nulos", f"{col}: {nulls} fila(s)"))

    bad_cost = int(((df["costo"] <= 0) | (df["costo"] >= df["price"])).sum())
    if bad_cost:
        issues.append(Issue("rango", f"costo fuera de (0, price) en {bad_cost} fila(s)"))

    mismatch = int(
        ((df["utilidad_bruta"] - (df["price"] - df["costo"])).abs() > ROUNDING_TOLERANCE).sum()
    )
    if mismatch:
        issues.append(Issue("consistencia", f"utilidad_bruta != price - costo en {mismatch} fila(s)"))

    margin = df["utilidad_bruta"] / df["price"]
    off_margin = int((~margin.between(*MARGIN_BOUNDS)).sum())
    if off_margin:
        issues.append(
            Issue("rango", f"margen fuera de {MARGIN_BOUNDS} en {off_margin} fila(s)")
        )

    return issues


def validate_monthly(gastos: pd.DataFrame, objetivos: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    key = ["dealer_name", "mes"]

    for name, table in (("gastos", gastos), ("objetivos", objetivos)):
        missing = [c for c in key if c not in table.columns]
        if missing:
            return [Issue("columnas", f"{name}: faltan {missing}")]
        dups = int(table.duplicated(subset=key).sum())
        if dups:
            issues.append(Issue("duplicados", f"{name}: {dups} clave(s) dealer+mes repetida(s)"))

    missing_exp = [c for c in EXPENSE_COLUMNS if c not in gastos.columns]
    if missing_exp:
        issues.append(Issue("columnas", f"gastos: faltan {missing_exp}"))
    else:
        if int(gastos[EXPENSE_COLUMNS].isna().sum().sum()):
            issues.append(Issue("nulos", "gastos tiene valores nulos"))
        if int((gastos[EXPENSE_COLUMNS] < 0).sum().sum()):
            issues.append(Issue("rango", "gastos tiene valores negativos"))

    if "objetivo_ventas" not in objetivos.columns:
        issues.append(Issue("columnas", "objetivos: falta objetivo_ventas"))
    elif int((objetivos["objetivo_ventas"].isna() | (objetivos["objetivo_ventas"] <= 0)).sum()):
        issues.append(Issue("rango", "objetivo_ventas nulo o <= 0"))

    g_keys = set(map(tuple, gastos[key].to_numpy().tolist()))
    o_keys = set(map(tuple, objetivos[key].to_numpy().tolist()))
    if g_keys != o_keys:
        issues.append(Issue("conciliacion", "gastos y objetivos no cubren las mismas dealer+mes"))

    return issues
