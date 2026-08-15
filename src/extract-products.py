import pandas as pd
import os
import json
from datetime import datetime, timezone
from utils import setup_logger, check_credentials, shopify_graphql

# =====================
# SETUP DOSSIERS / LOGGING
# =====================
os.makedirs("data", exist_ok=True)
logger = setup_logger('extract-products', 'extract-products.log')

check_credentials()

# Horodatage unique de l'extraction, appliqué à toutes les lignes
EXTRACTION_DATE = datetime.now(timezone.utc).isoformat()

# Fragment de champs partagé entre la requête principale et le backfill, pour
# éviter que les deux listes de champs divergent (voir fetch_remaining_variants).
VARIANT_FIELDS = """
              id
              title
              sku
              price
              compareAtPrice
              inventoryQuantity
              inventoryItem {
                unitCost {
                  amount
                }
              }
"""

# =====================
# FETCH ALL PRODUCTS WITH PAGINATION
# =====================
all_products = []
has_next_page = True
after_cursor = None

while has_next_page:

    query = f"""{{
  products(first: 250, after: {f'"{after_cursor}"' if after_cursor else 'null'}) {{
    edges {{
      node {{
        id
        title
        handle
        createdAt
        updatedAt
        vendor
        productType
        status
        tags
        images(first: 1) {{
          edges {{
            node {{
              url
            }}
          }}
        }}
        variants(first: 100) {{
          edges {{
            node {{
{VARIANT_FIELDS}
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

    logger.info('Querying Shopify...')
    response = shopify_graphql(query)

    try:
        data = response.json()
    except ValueError:
        logger.info(f'Response is not JSON: {response.text}')
        logger.info(f"❌ Non-JSON response: {response.status_code} {response.text}")
        break

    if "errors" in data:
        logger.info(f"❌ Erreur GraphQL: {data['errors']}")
        break

    products_data = data["data"]["products"]
    all_products.extend(products_data["edges"])

    has_next_page = products_data["pageInfo"]["hasNextPage"]
    after_cursor = products_data["pageInfo"]["endCursor"]

    logger.info(f"Récupéré {len(all_products)} produits...")

# =====================
# BACKFILL TRUNCATED VARIANTS
# =====================
# variants is capped at 100 per product above (same nested-cost constraint as
# lineItems in extract-orders.py). Any product with more than 100 variants gets
# flagged via pageInfo.hasNextPage; fetch the rest one product at a time.

def fetch_remaining_variants(product_gid, after_cursor):
    """Paginate the remaining variants for a single product (cheap: one product at a time)."""
    edges = []
    while True:
        query = f"""
        {{
          product(id: "{product_gid}") {{
            variants(first: 250, after: {f'"{after_cursor}"' if after_cursor else 'null'}) {{
              edges {{
                node {{
{VARIANT_FIELDS}
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

        if "errors" in data or not data.get("data", {}).get("product"):
            logger.info(f"❌ Échec récupération des variantes restantes pour {product_gid}: {data.get('errors', data)}")
            break

        variants = data["data"]["product"]["variants"]
        edges.extend(variants["edges"])

        if not variants["pageInfo"]["hasNextPage"]:
            break
        after_cursor = variants["pageInfo"]["endCursor"]

    return edges


truncated_products = [
    edge for edge in all_products
    if edge["node"]["variants"]["pageInfo"]["hasNextPage"]
]

if truncated_products:
    logger.info(f"⚠️ {len(truncated_products)} produit(s) avec plus de 100 variantes, récupération des variantes restantes...")
    for edge in truncated_products:
        product = edge["node"]
        extra_edges = fetch_remaining_variants(
            product["id"], product["variants"]["pageInfo"]["endCursor"]
        )
        product["variants"]["edges"].extend(extra_edges)
        logger.info(f"  ↳ {product['title']}: +{len(extra_edges)} variantes récupérées")

# Save raw JSON data
with open("data/shopify_products_raw.json", "w", encoding="utf-8") as f:
    json.dump({"products": all_products}, f, indent=2, ensure_ascii=False)

# =====================
# TRANSFORMATION
# =====================
products = []

for edge in all_products:
    product = edge["node"]

    # Iterate through variants
    for variant_edge in product.get("variants", {}).get("edges", []):
        variant = variant_edge["node"]

        inventory_item = variant.get("inventoryItem", {})
        unit_cost = inventory_item.get("unitCost", {}).get("amount") if inventory_item else None

        first_image_edges = product.get("images", {}).get("edges", [])
        first_image_url = first_image_edges[0]["node"]["url"] if first_image_edges else None

        products.append({
            "extraction_date": EXTRACTION_DATE,
            "product_id": product["id"].split('/')[-1],
            "product_title": product["title"],
            "product_handle": product["handle"],
            "product_created_at": pd.to_datetime(product["createdAt"]).date(),
            "product_updated_at": pd.to_datetime(product["updatedAt"]).date(),
            "product_type": product.get("productType"),
            "product_status": product.get("status"),
            "product_tags": ", ".join(product.get("tags", [])),
            "product_image_url": first_image_url,
            "variant_id": variant["id"].split('/')[-1],
            "variant_title": variant.get("title"),
            "variant_cost": unit_cost,
            "variant_price": variant.get("price"),
            "variant_inventory_qty": variant.get("inventoryQuantity"),
        })

df = pd.DataFrame(products)

# =====================
# EXPORT
# =====================
df.to_csv("data/shopify_products.csv", index=False, encoding="utf-8")

logger.info(f"✅ Export terminé : shopify_products.csv ({len(df)} variantes)")