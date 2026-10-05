"""Load and validate the fixed reference masters (12 branches, 5 products).

The CSVs under ``reference_data/`` are the project's existing branch and
product masters and must not be changed without an explicit decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REF_DIR = Path(__file__).parent / "reference_data"

BRANCH_COLS = ["branch_code", "branch_name", "city", "region", "opened_date"]
PRODUCT_COLS = [
    "product_code", "product_name", "product_family", "min_amount", "max_amount",
    "min_term_months", "max_term_months", "base_rate",
]

# Operational (non-risk) branch profile: relative catchment size and how
# digital the local customer base is. These only shape volumes / channel mix.
BRANCH_PROFILE = {
    "BR001": (0.14, 0.60), "BR002": (0.08, 0.45), "BR003": (0.07, 0.65),
    "BR004": (0.06, 0.65), "BR005": (0.11, 0.55), "BR006": (0.07, 0.50),
    "BR007": (0.08, 0.40), "BR008": (0.04, 0.35), "BR009": (0.07, 0.38),
    "BR010": (0.06, 0.42), "BR011": (0.09, 0.40), "BR012": (0.04, 0.30),
}

# Pass-through of the ECB-style reference rate into product pricing.
RATE_PASS_THROUGH = {
    "PL-STD": 0.60, "PL-GRN": 0.55, "AUT-NEW": 0.65, "MTG-FIX": 0.40, "SME-WCL": 0.70,
}


@dataclass
class Reference:
    branches: pd.DataFrame
    products: pd.DataFrame

    @property
    def branch_codes(self) -> list:
        return list(self.branches["branch_code"])

    @property
    def product_codes(self) -> list:
        return list(self.products["product_code"])


def load_reference() -> Reference:
    branches = pd.read_csv(REF_DIR / "branches.csv", dtype=str)
    products = pd.read_csv(REF_DIR / "products.csv")
    assert list(branches.columns) == BRANCH_COLS, "branch schema changed"
    assert list(products.columns) == PRODUCT_COLS, "product schema changed"
    assert len(branches) == 12 and branches["branch_code"].is_unique, "expected exactly 12 branches"
    assert len(products) == 5 and products["product_code"].is_unique, "expected exactly 5 products"
    assert set(branches["branch_code"]) == set(BRANCH_PROFILE), "branch profile mismatch"
    return Reference(branches=branches, products=products)
