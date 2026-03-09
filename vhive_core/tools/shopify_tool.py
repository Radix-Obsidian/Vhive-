"""
Shopify SDK integrations via GraphQL Admin API 2026-01.
Uses ShopifyAPI or direct GraphQL requests. Handles rate limits (429).
"""

from __future__ import annotations

import logging
import os
import re

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class ShopifyProductToolInput(BaseModel):
    """Input schema for Shopify product creation."""

    title: str = Field(..., description="Product title")
    description: str = Field(..., description="Product description")
    product_type: str = Field(default="digital", description="Product type (e.g., digital)")


class ShopifyProductTool(BaseTool):
    """Create products on Shopify via GraphQL Admin API 2026-01."""

    name: str = "ShopifyProductTool"
    description: str = "Create a product on Shopify. Requires SHOPIFY_SHOP_DOMAIN and SHOPIFY_ACCESS_TOKEN."
    args_schema: type = ShopifyProductToolInput

    def _run(
        self,
        title: str,
        description: str,
        product_type: str = "digital",
    ) -> str:
        shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "").strip()
        access_token = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()
        api_version = os.getenv("SHOPIFY_API_VERSION", "2026-01")

        if not shop_domain or not access_token:
            return "Error: SHOPIFY_SHOP_DOMAIN and SHOPIFY_ACCESS_TOKEN must be set in .env"

        url = f"https://{shop_domain}/admin/api/{api_version}/graphql.json"
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        }

        mutation = """
        mutation productCreate($product: ProductCreateInput!) {
            productCreate(product: $product) {
                product { id title }
                userErrors { field message }
            }
        }
        """
        variables = {
            "product": {
                "title": title,
                "descriptionHtml": description,
                "productType": product_type,
            }
        }

        try:
            resp = requests.post(url, json={"query": mutation, "variables": variables}, headers=headers, timeout=30)

            if resp.status_code == 429:
                return "Error: Shopify rate limit (429) - graph will retry"

            resp.raise_for_status()
            data = resp.json()

            errors = data.get("data", {}).get("productCreate", {}).get("userErrors", [])
            if errors:
                return f"Error: {errors}"

            product = data.get("data", {}).get("productCreate", {}).get("product", {})
            return f"Created product: {product.get('title', 'N/A')} (id: {product.get('id', 'N/A')})"
        except requests.RequestException as e:
            raise RuntimeError(f"Shopify API error: {e}") from e


# ── Helper: extract product ID from deploy result string ────────

_GID_PATTERN = re.compile(r"gid://shopify/Product/\d+")


def extract_shopify_gid(deploy_result: str) -> str | None:
    """Pull the Shopify GID from a deploy result string like 'Created product: X (id: gid://shopify/Product/123)'."""
    m = _GID_PATTERN.search(deploy_result)
    return m.group(0) if m else None


def extract_product_title(deploy_result: str) -> str | None:
    """Pull product title from 'Created product: TITLE (id: ...)'."""
    m = re.search(r"Created product:\s*(.+?)\s*\(id:", deploy_result)
    return m.group(1).strip() if m else None


# ── Shopify read helpers (not CrewAI tools — called by sync) ────


def _shopify_graphql(query: str, variables: dict | None = None) -> dict:
    """Execute a Shopify Admin GraphQL query. Returns the JSON data."""
    shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "").strip()
    access_token = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()
    api_version = os.getenv("SHOPIFY_API_VERSION", "2026-01")

    if not shop_domain or not access_token:
        raise RuntimeError("SHOPIFY_SHOP_DOMAIN and SHOPIFY_ACCESS_TOKEN must be set")

    url = f"https://{shop_domain}/admin/api/{api_version}/graphql.json"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": access_token,
    }
    body: dict = {"query": query}
    if variables:
        body["variables"] = variables

    resp = requests.post(url, json=body, headers=headers, timeout=30)
    if resp.status_code == 429:
        raise RuntimeError("Shopify rate limit (429)")
    resp.raise_for_status()
    return resp.json()


def fetch_orders(since_cursor: str | None = None, limit: int = 50) -> list[dict]:
    """Fetch recent orders with line items from Shopify.

    Returns list of dicts: {id, created_at, total_cents, currency, customer_email, line_items: [{product_id, title, quantity, price_cents}]}
    """
    after_clause = f', after: "{since_cursor}"' if since_cursor else ""
    query = f"""
    {{
      orders(first: {limit}, sortKey: CREATED_AT, reverse: true{after_clause}) {{
        edges {{
          cursor
          node {{
            id
            createdAt
            totalPriceSet {{ shopMoney {{ amount currencyCode }} }}
            email
            lineItems(first: 10) {{
              edges {{
                node {{
                  product {{ id }}
                  title
                  quantity
                  originalUnitPriceSet {{ shopMoney {{ amount currencyCode }} }}
                }}
              }}
            }}
          }}
        }}
        pageInfo {{ hasNextPage }}
      }}
    }}
    """
    try:
        data = _shopify_graphql(query)
    except Exception as e:
        log.warning("Failed to fetch Shopify orders: %s", e)
        return []

    orders_data = data.get("data", {}).get("orders", {}).get("edges", [])
    results = []
    for edge in orders_data:
        node = edge["node"]
        money = node.get("totalPriceSet", {}).get("shopMoney", {})
        total_cents = int(float(money.get("amount", "0")) * 100)

        line_items = []
        for li_edge in node.get("lineItems", {}).get("edges", []):
            li = li_edge["node"]
            li_money = li.get("originalUnitPriceSet", {}).get("shopMoney", {})
            line_items.append({
                "product_id": (li.get("product") or {}).get("id", ""),
                "title": li.get("title", ""),
                "quantity": li.get("quantity", 1),
                "price_cents": int(float(li_money.get("amount", "0")) * 100),
            })

        results.append({
            "id": node["id"],
            "created_at": node["createdAt"],
            "total_cents": total_cents,
            "currency": money.get("currencyCode", "USD"),
            "customer_email": node.get("email", ""),
            "line_items": line_items,
        })

    return results
