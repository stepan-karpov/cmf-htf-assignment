from __future__ import annotations


class Strategy:
    def on_lob(self, order_book, inventory: float) -> list[tuple]:
        """Called on every LOB snapshot.

        Args:
            order_book: current book state (C++ OrderBook wrapped by pybind11).
            inventory:  current signed position.

        Returns:
            List of (side, price, size) tuples where side is 'bid' or 'ask'.
            Return [] to pull all quotes.
        """
        raise NotImplementedError

    def on_fill(self, t_us: int, side: str, price: float, size: float) -> None:
        """Called after each fill."""
