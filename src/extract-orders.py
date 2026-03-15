import requests
import pandas as pd
import os
import json
import logging

# Create and configure logger
logging.basicConfig(filename="logs/extract-orders.log",
                    format='%(asctime)s %(message)s',
                    filemode='w')

# Creating an object
logger = logging.getLogger('extract-orders')

# =====================
# CONFIG
# =====================
SHOP_NAME = "epiphanieboutique.myshopify.com"
ACCESS_TOKEN = os.getenv("SHOPIFY_TOKEN", "")
API_VERSION = "2024-01"

if not ACCESS_TOKEN:
    raise ValueError("SHOPIFY_TOKEN environment variable not set")

# =====================
# GraphQL QUERY
# =====================
GRAPHQL_URL = f"https://{SHOP_NAME}/admin/api/{API_VERSION}/graphql.json"

headers = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json"
}

# =====================
# FETCH ALL ORDERS WITH PAGINATION
# =====================
all_orders = []
has_next_page = True
after_cursor = None

while has_next_page:
    query = f"""
    {{
      orders(first: 250, after: {f'"{after_cursor}"' if after_cursor else 'null'}) {{
        edges {{
          node {{
            id
            name
            createdAt
            totalPriceSet {{
              shopMoney {{
                amount
                currencyCode
              }}
            }}
            lineItems(first: 10) {{
              edges {{
                node {{
                  id
                  title
                  quantity
                  originalUnitPriceSet {{
                    shopMoney {{
                      amount
                    }}
                  }}
                  variant {{
                    id
                    title
                  }}
                }}
              }}
            }}
          }}
        }}
        pageInfo {{
          hasNextPage
          endCursor
        }}
      }}
    }}
    """
    
    response = requests.post(
        GRAPHQL_URL,
        json={"query": query},
        headers=headers
    )
    
    data = response.json()
    
    if "errors" in data:
        logger.info(f"❌ Erreur GraphQL: {data['errors']}")
        break
    
    orders_data = data["data"]["orders"]
    all_orders.extend(orders_data["edges"])
    
    has_next_page = orders_data["pageInfo"]["hasNextPage"]
    after_cursor = orders_data["pageInfo"]["endCursor"]
    
    logger.info(f"Récupéré {len(all_orders)} commandes...")

# Save raw JSON data
with open("data/shopify_orders_raw.json", "w") as f:
    json.dump({"orders": all_orders}, f, indent=2)

# =====================
# TRANSFORMATION
# =====================
orders = []

for edge in all_orders:
    order = edge["node"]
    
    total_price = float(order["totalPriceSet"]["shopMoney"]["amount"])
    currency = order["totalPriceSet"]["shopMoney"]["currencyCode"]
    
    for line_item_edge in order["lineItems"]["edges"]:
        line_item = line_item_edge["node"]
        item_id = line_item["id"].split('/')[-1]
        item_title = line_item["title"]
        item_qty = line_item["quantity"]
        item_price = float(line_item["originalUnitPriceSet"]["shopMoney"]["amount"])
        item_variant_id = line_item["variant"]["id"].split('/')[-1] if line_item.get("variant") else None
    
        orders.append({
            "order_number": order["name"],
            "order_dt": pd.to_datetime(order["createdAt"]).date(),
            "order_total_price": total_price,
            "item_id" : item_id,
            "item_title" : item_title,
            "item_qty" : item_qty,
            "item_price" : item_price,
            "item_variant_id" : item_variant_id,
        })

df = pd.DataFrame(orders)

# =====================
# EXPORT
# =====================
df.to_csv("data/shopify_orders.csv", index=False)

logger.info(f"✅ Export terminé : shopify_orders.csv ({len(df)} orders)")