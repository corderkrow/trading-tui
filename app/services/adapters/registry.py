"""Adapter registry — resolves exchange name to adapter class."""

from app.services.adapters.base import MarketDataAdapter


_ADAPTERS: dict[str, type[MarketDataAdapter]] = {}


def register_adapter(name: str, adapter_cls: type[MarketDataAdapter]) -> None:
    _ADAPTERS[name] = adapter_cls


def get_adapter(name: str, **kwargs) -> MarketDataAdapter:
    if name not in _ADAPTERS:
        raise ValueError(f"Unknown adapter: {name}. Registered: {list(_ADAPTERS)}")
    return _ADAPTERS[name](**kwargs)


def register_default_adapters() -> None:
    from app.services.adapters.binance import BinanceAdapter
    from app.services.adapters.yahoo import YahooAdapter
    register_adapter("binance", BinanceAdapter)
    register_adapter("yahoo", YahooAdapter)


register_default_adapters()