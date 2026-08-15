import pandas as pd
import os
import json
from datetime import datetime, timezone
from utils import setup_logger, check_credentials, shopify_graphql

# =====================
# SETUP DOSSIERS / LOGGING
# =====================
os.makedirs("data", exist_ok=True)
logger = setup_logger('extract-orders', 'extract-orders.log')

check_credentials()

# Horodatage unique de l'extraction, appliqué à toutes les lignes
EXTRACTION_DATE = datetime.now(timezone.utc).isoformat()

# Fragment de champs partagé entre la requête principale et le backfill, pour
# éviter que les deux listes de champs divergent (voir fetch_remaining_line_items).
LINE_ITEM_FIELDS = """
                  id
                  title
                  quantity
                  originalUnitPriceSet {
                    shopMoney {
                      amount
                    }
                  }
                  variant {
                    id
                    title
                  }
"""

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
            lineItems(first: 50) {{
              edges {{
                node {{
{LINE_ITEM_FIELDS}
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
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

    response = shopify_graphql(query)

    data = response.json()

    if "errors" in data:
        logger.info(f"❌ Erreur GraphQL: {data['errors']}")
        break

    orders_data = data["data"]["orders"]
    all_orders.extend(orders_data["edges"])

    has_next_page = orders_data["pageInfo"]["hasNextPage"]
    after_cursor = orders_data["pageInfo"]["endCursor"]

    logger.info(f"Récupéré {len(all_orders)} commandes...")

# =====================
# BACKFILL TRUNCATED LINE ITEMS
# =====================
# lineItems is capped at 50 per order above (Shopify's nested connection cost
# grows with orders_first * lineItems_first, so we can't just request everyone's
# line items in one shot). Any order with more than 50 line items gets flagged
# via pageInfo.hasNextPage; fetch the rest one order at a time.

def fetch_remaining_line_items(order_gid, after_cursor):
    """Paginate the remaining lineItems for a single order (cheap: one order at a time)."""
    edges = []
    while True:
        query = f"""
        {{
          order(id: "{order_gid}") {{
            lineItems(first: 250, after: {f'"{after_cursor}"' if after_cursor else 'null'}) {{
              edges {{
                node {{
{LINE_ITEM_FIELDS}
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
          }}
        }}
        """
        response = shopify_graphql(query)
        data = response.json()

        if "errors" in data or not data.get("data", {}).get("order"):
            logger.info(f"❌ Échec récupération des line items restants pour {order_gid}: {data.get('errors', data)}")
            break

        line_items = data["data"]["order"]["lineItems"]
        edges.extend(line_items["edges"])

        if not line_items["pageInfo"]["hasNextPage"]:
            break
        after_cursor = line_items["pageInfo"]["endCursor"]

    return edges


truncated_orders = [
    edge for edge in all_orders
    if edge["node"]["lineItems"]["pageInfo"]["hasNextPage"]
]

if truncated_orders:
    logger.info(f"⚠️ {len(truncated_orders)} commande(s) avec plus de 50 articles, récupération des articles restants...")
    for edge in truncated_orders:
        order = edge["node"]
        extra_edges = fetch_remaining_line_items(
            order["id"], order["lineItems"]["pageInfo"]["endCursor"]
        )
        order["lineItems"]["edges"].extend(extra_edges)
        logger.info(f"  ↳ {order['name']}: +{len(extra_edges)} articles récupérés")

# Save raw JSON data
with open("data/shopify_orders_raw.json", "w", encoding="utf-8") as f:
    json.dump({"orders": all_orders}, f, indent=2, ensure_ascii=False)

# =====================
# TRANSFORMATION
# =====================
orders = []

for edge in all_orders:
    order = edge["node"]
    
    total_price = float(order["totalPriceSet"]["shopMoney"]["amount"])

    for line_item_edge in order["lineItems"]["edges"]:
        line_item = line_item_edge["node"]
        item_id = line_item["id"].split('/')[-1]
        item_title = line_item["title"]
        item_qty = line_item["quantity"]
        item_price = float(line_item["originalUnitPriceSet"]["shopMoney"]["amount"])
        item_variant_id = line_item["variant"]["id"].split('/')[-1] if line_item.get("variant") else None
    
        orders.append({
            "extraction_date": EXTRACTION_DATE,
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
df.to_csv("data/shopify_orders.csv", index=False, encoding="utf-8")

logger.info(f"✅ Export terminé : shopify_orders.csv ({len(df)} orders)")