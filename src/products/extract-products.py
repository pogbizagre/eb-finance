import requests
import pandas as pd
import os
import json

# =====================
# CONFIG
# =====================
SHOP_NAME = "epiphanieboutique.myshopify.com"
ACCESS_TOKEN = os.getenv("SHOPIFY_TOKEN", "")
API_VERSION = "2024-01"

if not ACCESS_TOKEN:
    raise ValueError("SHOPIFY_TOKEN environment variable not set")

# =====================
# GraphQL QUERY FOR PRODUCTS
# =====================
GRAPHQL_URL = f"https://{SHOP_NAME}/admin/api/{API_VERSION}/graphql.json"

headers = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json"
}

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
        variants(first: 100) {{
          edges {{
            node {{
              id
              title
              sku
              price
              compareAtPrice
              inventoryQuantity
              inventoryItem {{
                unitCost {{
                  amount
                }}
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
        print(f"❌ Erreur GraphQL: {data['errors']}")
        break
    
    products_data = data["data"]["products"]
    all_products.extend(products_data["edges"])
    
    has_next_page = products_data["pageInfo"]["hasNextPage"]
    after_cursor = products_data["pageInfo"]["endCursor"]
    
    print(f"Récupéré {len(all_products)} produits...")

# Save raw JSON data
with open("data/shopify_products_raw.json", "w") as f:
    json.dump({"products": all_products}, f, indent=2)

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
        
        products.append({
            "product_id": product["id"].split('/')[-1],
            "product_title": product["title"],
            "product_handle": product["handle"],
            "product_created_at": pd.to_datetime(product["createdAt"]).date(),
            "product_updated_at": pd.to_datetime(product["updatedAt"]).date(),
            "product_type": product.get("productType"),
            "product_status": product.get("status"),
            "product_tags": ", ".join(product.get("tags", [])),
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
df.to_csv("data/shopify_products.csv", index=False)

print(f"✅ Export terminé : shopify_products.csv ({len(df)} variantes)")