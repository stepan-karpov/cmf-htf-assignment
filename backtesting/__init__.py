from __future__ import annotations

try:
    from ._engine import OrderBook
except ImportError:
    raise ImportError(
        "C++ engine not compiled.\n"
        "Run:  cd backtesting && make\n"
        "(requires: pip install pybind11)"
    )

from .strategy import Strategy
from .backtester import Backtester

__all__ = ["Strategy", "Backtester", "OrderBook"]
