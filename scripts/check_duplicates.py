"""Pre-ETL check: duplicate keys and join cardinality (decides fact grain safety)."""
import pandas as pd

D = "Data/Raw"
orders = pd.read_csv(f"{D}/olist_orders_dataset.csv")
items = pd.read_csv(f"{D}/olist_order_items_dataset.csv")
reviews = pd.read_csv(f"{D}/olist_order_reviews_dataset.csv")
payments = pd.read_csv(f"{D}/olist_order_payments_dataset.csv")
customers = pd.read_csv(f"{D}/olist_customers_dataset.csv")
products = pd.read_csv(f"{D}/olist_products_dataset.csv")
sellers = pd.read_csv(f"{D}/olist_sellers_dataset.csv")

def check(name, df, keys):
    dup = df.duplicated(subset=keys).sum()
    print(f"{name}: rows={len(df):,} key={keys} duplicate_rows={dup:,}")

check("orders", orders, ["order_id"])
check("customers", customers, ["customer_id"])
check("products", products, ["product_id"])
check("sellers", sellers, ["seller_id"])
check("items", items, ["order_id", "order_item_id"])
check("payments", payments, ["order_id", "payment_sequential"])
check("reviews(review_id)", reviews, ["review_id"])
check("reviews(order_id)", reviews, ["order_id"])

# Does joining reviews onto orders multiply rows?
m = orders.merge(reviews, on="order_id", how="left")
print(f"\norders rows={len(orders):,} -> after review join={len(m):,} (inflation={len(m)-len(orders):,})")
m2 = orders.merge(payments.groupby("order_id").agg(
    payment_total=("payment_value", "sum"),
    n_payments=("payment_sequential", "count")).reset_index(), on="order_id", how="left")
print(f"orders after payment AGG join={len(m2):,} (inflation={len(m2)-len(orders):,})")
