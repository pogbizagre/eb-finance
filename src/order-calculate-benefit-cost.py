import pandas as pd
import logging

# Create and configure logger
logging.basicConfig(filename="logs/order-cost-benefit.log",
                    format='%(asctime)s %(message)s',
                    filemode='w')

# Creating an object
logger = logging.getLogger('order-cost-benefit')


# =====================
# LOAD DATA
# =====================
orders_df = pd.read_csv("data/shopify_orders.csv")
products_df = pd.read_csv("data/shopify_products.csv")

logger.info("📊 Orders shape:", orders_df.shape)
logger.info("📊 Products shape:", products_df.shape)

# =====================
# JOIN ORDERS WITH PRODUCTS
# =====================
merged_df = orders_df.merge(
    products_df[['variant_id', 'variant_cost', 'product_title']],
    left_on='item_variant_id',
    right_on='variant_id',
    how='left'
)

logger.info(f"✅ Merged shape: {merged_df.shape}")

merged_df.to_csv("data/shopify_orders_detailed.csv", index=False)
logger.info(f"✅ Export terminé : shopify_orders_detailed.csv")

# =====================
# CALCULATE COSTS & PROFIT BY ORDER
# =====================
# Calculate line item total cost
merged_df['line_item_total_cost'] = merged_df['item_qty'] * pd.to_numeric(merged_df['variant_cost'], errors='coerce')

# Group by order
order_summary = merged_df.groupby('order_number').agg({
    'order_total_price': 'first',  # Revenue
    'line_item_total_cost': 'sum',  # Total cost
    'item_qty': 'sum',              # Total items
    'order_dt' : 'min'
}).reset_index()

# Calculate benefit (profit)
order_summary['total_cost'] = order_summary['line_item_total_cost']
order_summary['benefit'] = order_summary['order_total_price'] - order_summary['total_cost']
order_summary['profit_margin_%'] = ((order_summary['benefit'] / order_summary['order_total_price'].replace(0, 1)) * 100).round(2)
order_summary.loc[order_summary['order_total_price'] == 0, 'profit_margin_%'] = 0

# Rename columns
order_summary = order_summary.rename(columns={
    'order_number': 'order_number',
    'order_total_price': 'revenue',
    'item_qty': 'total_items'
})

# Select and reorder columns
order_summary = order_summary[['order_number', 'order_dt','revenue', 'total_cost', 'benefit', 'profit_margin_%', 'total_items']]

# =====================
# EXPORT
# =====================
order_summary.to_csv("data/shopify_orders_with_profit.csv", index=False)
logger.info(f"\n✅ Export terminé : shopify_orders_with_profit.csv")

logger.info(f"\n📈 Résumé des commandes:")
logger.info(order_summary.head(10))
logger.info(f"\n💰 Total revenue: {order_summary['revenue'].sum():.2f}")
logger.info(f"💰 Total cost: {order_summary['total_cost'].sum():.2f}")
logger.info(f"💰 Total benefit: {order_summary['benefit'].sum():.2f}")
logger.info(f"📊 Average profit margin: {order_summary['profit_margin_%'].mean():.2f}%")