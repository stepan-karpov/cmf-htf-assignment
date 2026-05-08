# Entrance Assignment — CMF HFT School

Backtesting engine + Avellaneda–Stoikov strategy on limit order book data.

## 1. Repository Structure

```
.
├── DataAnalysis.ipynb          # EDA: tick size, spread, volatility, trade arrival
├── Strategy.ipynb              # All strategies + grid search + results (§1–§3)
│
├── backtesting/                # C++ backtesting engine (pybind11)
│   ├── Makefile                # clang++ -O3 -std=c++17 → _engine*.so
│   ├── bindings.cpp            # Only Python↔C++ seam: PyStrategy + run()
│   ├── strategy.py             # Strategy base class (Python)
│   ├── backtester.py           # Thin wrapper: passes paths to C++, returns prefix
│   ├── engine/
│   │   ├── orderbook.hpp       # OrderBook: refresh(), apply_trade(), queue_at()
│   │   ├── execution.hpp       # Order, Fill, PessimisticExecution
│   │   ├── strategy.hpp        # StrategyBase abstract class
│   │   ├── reader.hpp          # LobReader, TradeReader (stream CSV line-by-line)
│   │   ├── backtester.hpp      # Two-pointer merge loop (LOB + trades)
│   │   └── result.hpp          # RunData accumulator + save_csv()
│   └── visualize/
│       └── result.py           # BacktestResult: reads CSVs → summary_df() + plot()
│
└── data/
    ├── lob_train.csv / lob_val.csv / lob_test.csv
    └── trades_train.csv / trades_val.csv / trades_test.csv
```

**Build engine:** `cd backtesting && make`

**Usage:**
```python
from backtesting import Backtester
from backtesting.visualize import BacktestResult

bt = Backtester("data/lob_val.csv", "data/trades_val.csv")
prefix = bt.run(MyStrategy(), output_path="results/my_run")
r = BacktestResult(prefix, capital=1000.0)
r.summary_df()
```

## 2 Simulation setup

**Dataset** — DOGE/USDT, Binance, Aug 1–7 2024. 

- Capital = $1 000
- 0 % maker fee
- 0 ns latency
- no market impact.
- Execution: **Pessimistic** (bid fills only on sell trade ≤ bid price).

Splits: 

- **Train** Aug 1–2 12:00 (1.5 d, calibration + grid search)
- **Val** Aug 2 12:00–3 00:00 (0.5 d, hyperparameter selection)
- **Test** Aug 3–7 (4 d, out-of-sample).

---

## 3 Strategy overview

| # | Strategy | Key idea |
|---|---|---|
| §1.1 | **AS Static** | AS 2008 with fixed calibrated σ, κ; grid-searched γ |
| §1.2 | **AS Rolling** | Replace fixed σ with rolling estimate from raw LOB ticks |
| §1.3 | **AS Heuristic** | 1-sec σ resampling · reservation-price clamp · inventory cap |
| §2.1 | **Microprice** | Depth-weighted fair value as reference price |
| §2.2 | **Microprice V2** | Tighter σ cap · volatility pause · trend EMA overlay |

---

## 4 Performance

| Strategy | Val PnL | Test PnL | Test % | Test Sharpe | Test fills |
|---|---:|---:|---:|---:|---:|
| §1.1 AS Static     | −4.45  | −27.22  | −2.722%  | −71.6   | 362,615 |
| §1.2 AS Rolling    | −24.58 | −157.68 | −15.768% | −1126.2 | 598,855 |
| §1.3 AS Heuristic  | −7.35  | −49.99  | −4.999%  | −460.5  | 538,629 |
| §2.1 Microprice    | −7.37  | −49.98  | −4.998%  | −455.7  | 538,657 |
| §2.2 Microprice V2 | −7.58  | −48.16  | −4.816%  | −777.2  | 519,137 |

PnL in USD. Sharpe annualized. Capital = $1 000.
