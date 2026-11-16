from utils import shopify_graphql
import json

query = f"""{{
      customers(first: 5) {{
        edges {{
          node {{
            id firstName lastName email phone createdAt updatedAt numberOfOrders
            defaultAddress {{ city country }}
            }}
          }}
      pageInfo {{ hasNextPage endCursor }}
      }}
    }}
    """
data = shopify_graphql(query).json()

customers_data = data["data"]["customers"]

with open("data/shopify_customers_raw.json", "w", encoding="utf-8") as f:
    json.dump({"customers": data}, f, indent=2, ensure_ascii=False)