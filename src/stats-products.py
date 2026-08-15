import pandas as pd
import os
from utils import setup_logger, add_size_standard, categorize_products

# =====================
# SETUP DOSSIERS / LOGGING
# =====================
os.makedirs("data", exist_ok=True)
logger = setup_logger('stats-products', 'stats-products.log')

logger.info("=" * 50)
logger.info("Starting stats-products script")
logger.info("=" * 50)

# =====================
# LOAD DATA
# =====================
logger.info("Loading products data...")
products_df = pd.read_csv("data/shopify_products.csv")
logger.info(f"Loaded {len(products_df)} rows")

logger.info("Creating size_standard column...")
products_df = add_size_standard(products_df)

logger.info("Cleaning product tags...")
products_df = categorize_products(products_df)
logger.info("✅ Tags cleaned")

cond1 = (products_df['size_standard'].notna())
cond2 = (products_df['product_status'].isin(['ACTIVE']))

logger.info("Applying filters...")
filtered_df = products_df[cond1 & cond2].copy()
logger.info(f"Filtered to {len(filtered_df)} rows")

filtered_df['total_variant_price'] = filtered_df['variant_price']*filtered_df['variant_inventory_qty']
filtered_df['total_variant_cost'] = filtered_df['variant_cost']*filtered_df['variant_inventory_qty']

logger.info("Grouping by size...")
stats_by_size = filtered_df.groupby('size_standard').agg({
    'extraction_date': 'first',
    'variant_inventory_qty': 'sum',
    'total_variant_price' : 'sum',
    'total_variant_cost' : 'sum',
    'product_title': lambda x: ', '.join(x.unique()),
}).reset_index()
logger.info(f"Grouped into {len(stats_by_size)} size categories")

logger.info("Exporting to CSV...")
stats_by_size.to_csv("data/shoes_size_stats.csv", index=False, encoding="utf-8")
logger.info("Export complete: data/shoes_size_stats.csv")
logger.info("=" * 50)
logger.info("Script finished successfully")
logger.info("=" * 50)

logger.info("Extracting unique tags...")

active_products_df = products_df[cond2].copy()
tags_uniques = active_products_df['product_tags_cleaned'].unique()
logger.info(f"List of available tags : {tags_uniques}")

active_products_df['total_variant_price'] = active_products_df['variant_price']*active_products_df['variant_inventory_qty']
active_products_df['total_variant_cost'] = active_products_df['variant_cost']*active_products_df['variant_inventory_qty']

logger.info("Grouping by tags...")
stats_by_tags = active_products_df.groupby('product_category').agg({
    'extraction_date': 'first',
    'variant_inventory_qty': 'sum',
    'total_variant_price': 'sum',
    'total_variant_cost' : 'sum',
    'product_title': lambda x: ', '.join(x.unique()),
}).reset_index()
logger.info(f"Grouped into {len(stats_by_tags)} tag categories")

logger.info("Calculating margin by category...")
stats_by_tags['margin'] = stats_by_tags['total_variant_price'] - stats_by_tags['total_variant_cost']
stats_by_tags['margin_%'] = (
    (stats_by_tags['margin'] / stats_by_tags['total_variant_price']) * 100
).round(2)
stats_by_tags.loc[stats_by_tags['total_variant_price'] == 0, 'margin_%'] = 0

logger.info("Exporting to CSV...")
stats_by_tags.to_csv("data/products_tags_stats.csv", index=False, encoding="utf-8")
logger.info("Export complete: data/products_tags_stats.csv")
logger.info("=" * 50)
logger.info("Script finished successfully")
logger.info("=" * 50)