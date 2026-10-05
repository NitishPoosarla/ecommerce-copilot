"""STEP 2: Inspect every raw CSV — columns, row count, sample rows."""
import glob
import os

import pandas as pd

DATA_DIR = "Data/Raw"

DESCRIBE = {
    "olist_customers_dataset.csv": "Who bought: one row per customer with their ID and Brazilian state/city.",
    "olist_geolocation_dataset.csv": "Where: maps Brazilian zip codes to lat/long (reference data, not loaded as a dimension).",
    "olist_orders_dataset.csv": "The spine: one row per order with the key dates (purchase, estimated arrival, delivered).",
    "olist_order_items_dataset.csv": "What was bought: one row per product line in an order (links orders to products/sellers).",
    "olist_order_payments_dataset.csv": "How it was paid: one row per order payment (value, type, installments).",
    "olist_order_reviews_dataset.csv": "What buyers thought: one row per order review (1-5 stars + comment text).",
    "olist_products_dataset.csv": "The catalog: one row per product with category, weight, photos.",
    "olist_sellers_dataset.csv": "Who sold: one row per seller with their state/city.",
    "product_category_name_translation.csv": "Lookup: translates Portuguese product category names to English.",
}

files = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
print(f"Found {len(files)} CSV files in {DATA_DIR}/\n")
print("=" * 90)

for f in files:
    name = os.path.basename(f)
    df = pd.read_csv(f)
    print(f"\nFILE: {name}")
    print(f"  Rows: {len(df):,} | Columns: {len(df.columns)}")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Nulls per column: {df.isna().sum()[df.isna().sum() > 0].to_dict() or 'none'}")
    print(f"  What it is: {DESCRIBE.get(name, 'n/a')}")
    print("  Sample rows:")
    print(df.head(3).to_string(max_colwidth=28, index=False))
    print("-" * 90)
