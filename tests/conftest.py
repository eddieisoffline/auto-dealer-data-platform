import pandas as pd
import pytest


@pytest.fixture
def sales_csv(tmp_path):
    """CSV con la forma del dataset de Kaggle: 3 días de enero y 2 de febrero."""
    dates = (
        ["2022-01-30"] * 6 + ["2022-01-31"] * 6 + ["2022-02-01"] * 6 + ["2022-02-02"] * 6
    )
    n = len(dates)
    df = pd.DataFrame(
        {
            "Car_id": [f"C{i:03d}" for i in range(n)],
            "Date": dates,
            "Customer Name": ["x"] * n,
            "Gender": ["M"] * n,
            "Annual Income": [1000] * n,
            "Dealer_Name": ["Norte", "Sur"] * (n // 2),
            "Company": ["Ford", "Nissan", "Ford"] * (n // 3),
            "Model": ["m1", "m2", "m3", "m1"] * (n // 4),
            "Price ($)": [15000 + 500 * i for i in range(n)],
            "Phone": [1] * n,
            "Dealer_Region": ["R"] * n,
        }
    )
    path = tmp_path / "sales.csv"
    df.to_csv(path, index=False)
    return str(path)
