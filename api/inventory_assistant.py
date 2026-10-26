import re
from typing import Any


LOW_STOCK_TERMS = {'low', 'reorder', 'restock', 'running', 'short'}
INVENTORY_TERMS = {'inventory', 'all', 'list', 'items', 'overview'}


def _tokens(value: str) -> set[str]:
    words = re.findall(r'[a-z0-9]+', value.casefold())
    return {word[:-1] if len(word) > 4 and word.endswith('s') else word for word in words}


def _item_dict(item: Any) -> dict[str, Any]:
    return dict(item)


def answer_inventory_query(query: str, inventory: list[Any]) -> dict[str, Any]:
    """Answer supported inventory questions without changing inventory."""
    items = [_item_dict(item) for item in inventory]
    query_tokens = _tokens(query)

    matches = []
    for item in items:
        name_tokens = _tokens(item['name'])
        sku_tokens = _tokens(item['sku'])
        if (name_tokens and name_tokens <= query_tokens) or (sku_tokens and sku_tokens <= query_tokens):
            matches.append(item)

    if query_tokens & LOW_STOCK_TERMS:
        if len(matches) > 1:
            return {
                'answer': 'I found more than one matching item. Please include the exact item name or SKU.',
                'items': matches,
            }
        candidates = matches or items
        low_stock = [
            item for item in candidates
            if item['quantity'] <= item['reorder_point']
        ]
        if matches and not low_stock:
            item = matches[0]
            return {
                'answer': (
                    f"{item['name']} ({item['sku']}) has {item['quantity']} units in stock, "
                    f"above its reorder point of {item['reorder_point']}; no reorder is suggested."
                ),
                'items': matches,
            }
        if not low_stock:
            return {
                'answer': 'No items are currently at or below their reorder point.',
                'items': [],
            }

        suggestions = []
        for item in low_stock:
            suggested_quantity = max(0, item['target_stock'] - item['quantity'])
            suggestions.append(
                f"{item['name']} ({item['sku']}): {item['quantity']} in stock; "
                f"reorder point {item['reorder_point']}. Suggested reorder: "
                f"{suggested_quantity} to reach the target of {item['target_stock']}."
            )
        return {
            'answer': 'Low-stock items (suggestions only; no orders were placed): '
            + ' '.join(suggestions),
            'items': low_stock,
        }

    if len(matches) == 1:
        item = matches[0]
        status = (
            'at or below its reorder point'
            if item['quantity'] <= item['reorder_point']
            else 'above its reorder point'
        )
        return {
            'answer': (
                f"{item['name']} ({item['sku']}) has {item['quantity']} units in stock, "
                f"which is {status} of {item['reorder_point']}."
            ),
            'items': matches,
        }

    if len(matches) > 1:
        return {
            'answer': 'I found more than one matching item. Please include the exact item name or SKU.',
            'items': matches,
        }

    if query_tokens & INVENTORY_TERMS:
        summary = [
            f"{item['name']} ({item['sku']}): {item['quantity']} in stock"
            for item in items
        ]
        return {
            'answer': 'Current inventory: ' + '; '.join(summary) if summary else 'The inventory is empty.',
            'items': items,
        }

    return {
        'answer': (
            "I couldn't identify an inventory item in that question. Ask about an item by name or SKU, "
            "or ask which items are low in stock. I only provide read-only inventory information."
        ),
        'items': [],
    }
