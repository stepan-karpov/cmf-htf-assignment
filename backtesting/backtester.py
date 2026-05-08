from __future__ import annotations

from .strategy import Strategy

try:
    from . import _engine
except ImportError:
    raise ImportError("C++ engine not compiled.\nRun:  cd backtesting && make")


class Backtester:
    """Thin wrapper — CSV reading and hot loop run entirely in C++."""

    def __init__(
        self,
        lob_path: str,
        trades_path: str,
        latency_ns: int = 0,
        log_interval_sec: float = 10.0,
        quote_log_stride: int = 50,
    ):
        self.lob_path = lob_path
        self.trades_path = trades_path
        self._latency_us = latency_ns // 1000
        self.log_interval_us = int(log_interval_sec * 1_000_000)
        self.quote_log_stride = max(1, int(quote_log_stride))

    def run(self, strategy: Strategy, output_path: str = "result") -> str:
        """Run simulation; saves CSVs with prefix output_path. Returns prefix."""
        _engine.run(
            strategy,
            self.lob_path, self.trades_path,
            self._latency_us, self.log_interval_us, self.quote_log_stride,
            output_path,
        )
        return output_path
