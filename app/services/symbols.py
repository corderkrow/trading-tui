"""Common US-market symbol aliases -> data-source symbols.

Users type the index name everyone uses ("SPX", "NDX", "DJI"), but the market
data source only answers to its own form ("^GSPC", "^NDX", "^DJI"). Resolve
once here so alerts and every market-data lookup agree on the same symbol.
"""

from __future__ import annotations

# Yahoo Finance index symbols (the caret form is the canonical one).
US_INDEX_ALIASES: dict[str, str] = {
    "SPX": "^GSPC",
    "SP500": "^GSPC",
    "GSPC": "^GSPC",
    "NDX": "^NDX",
    "NASDAQ100": "^NDX",
    "DJI": "^DJI",
    "DOW": "^DJI",
    "DOWJONES": "^DJI",
    "VIX": "^VIX",
    "RUT": "^RUT",
    "RUSSELL2000": "^RUT",
    "IXIC": "^IXIC",
    "COMP": "^IXIC",
    "NASDAQ": "^IXIC",
}


def resolve_symbol(symbol: str) -> str:
    """Upper-cased symbol, with common US index names mapped to the real one."""
    key = symbol.strip().upper()
    return US_INDEX_ALIASES.get(key, key)
