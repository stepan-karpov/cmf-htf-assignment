from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DARK = "plotly_dark"


class BacktestResult:
    """Loads C++ backtest output from CSV files; same API as src.BacktestResult."""

    def __init__(self, prefix: str, capital: float = 1000.0):
        self.capital = capital
        self._load(prefix)

    def _load(self, prefix: str) -> None:
        def to_dt(col):
            return pd.to_datetime(np.asarray(col, np.int64), unit="us")

        pnl_df = pd.read_csv(f"{prefix}_pnl.csv")
        self.pnl = pd.Series(
            pnl_df["pnl"].values,
            index=to_dt(pnl_df["t_us"]),
            name="pnl",
        )
        self.inventory = pd.Series(
            pnl_df["inventory"].values,
            index=to_dt(pnl_df["t_us"]),
            name="inventory",
        )

        qt_df = pd.read_csv(f"{prefix}_quotes.csv")
        self.quotes = pd.DataFrame(
            {"mid": qt_df["mid"].values,
             "bid": qt_df["bid"].values,
             "ask": qt_df["ask"].values},
            index=to_dt(qt_df["t_us"]),
        )

        fl_df = pd.read_csv(f"{prefix}_fills.csv")
        self.fills = pd.DataFrame(
            {"side":      fl_df["side"].values,
             "price":     fl_df["price"].values,
             "size":      fl_df["size"].values,
             "inv_after": fl_df["inventory"].values},
            index=to_dt(fl_df["t_us"]),
        )

    # ── read API ──────────────────────────────────────────────────────────────
    # Identical to src/result.py from here down.

    def summary(self) -> dict:
        out = {}
        pnl = self.pnl.values
        if len(pnl) >= 2:
            returns = np.diff(pnl)
            total_sec = (self.pnl.index[-1] - self.pnl.index[0]).total_seconds()
            obs_dt = total_sec / (len(pnl) - 1)
            obs_per_year = (365.25 * 86400.0) / max(obs_dt, 1e-9)
            std_ret = float(np.std(returns))
            out["total_pnl"] = float(pnl[-1])
            out["sharpe_annualized"] = (
                float(np.mean(returns)) / std_ret * np.sqrt(obs_per_year)
                if std_ret > 0 else 0.0
            )
            out["max_drawdown"] = float((pnl - np.maximum.accumulate(pnl)).min())
        else:
            out["total_pnl"] = float(pnl[-1]) if len(pnl) else 0.0
            out["sharpe_annualized"] = 0.0
            out["max_drawdown"] = 0.0

        trade_fills = self.fills[self.fills["side"].isin(["bid", "ask"])]
        n_bid = int((trade_fills["side"] == "bid").sum())
        n_ask = int((trade_fills["side"] == "ask").sum())
        out["n_fills"] = n_bid + n_ask
        out["n_bid_fills"] = n_bid
        out["n_ask_fills"] = n_ask
        out["fill_imbalance"] = (
            (n_bid - n_ask) / (n_bid + n_ask) if (n_bid + n_ask) > 0 else 0.0
        )
        out["avg_inventory"] = float(self.inventory.mean())
        out["std_inventory"] = float(self.inventory.std())
        out["max_abs_inventory"] = float(self.inventory.abs().max())
        out["turnover"] = float(trade_fills["size"].sum())
        out["turnover_usd"] = float((trade_fills["price"] * trade_fills["size"]).sum())
        return out

    def summary_df(self) -> pd.DataFrame:
        s = self.summary()
        c = self.capital
        rows = [
            ("PnL",       "total_pnl ($)",        f"{s['total_pnl']:+.4f}"),
            ("PnL",       "total_pnl (%)",         f"{s['total_pnl']/c*100:+.4f}%"),
            ("PnL",       "sharpe_annualized",     f"{s['sharpe_annualized']:+.2f}"),
            ("PnL",       "max_drawdown ($)",      f"{s['max_drawdown']:+.4f}"),
            ("PnL",       "max_drawdown (%)",       f"{s['max_drawdown']/c*100:+.4f}%"),
            ("Fills",     "n_fills",               f"{s['n_fills']:,}"),
            ("Fills",     "n_bid_fills",           f"{s['n_bid_fills']:,}"),
            ("Fills",     "n_ask_fills",           f"{s['n_ask_fills']:,}"),
            ("Fills",     "fill_imbalance",        f"{s['fill_imbalance']:+.4f}"),
            ("Inventory", "avg_inventory",         f"{s['avg_inventory']:+.4f}"),
            ("Inventory", "std_inventory",         f"{s['std_inventory']:.4f}"),
            ("Inventory", "max_abs_inventory",     f"{s['max_abs_inventory']:.4f}"),
            ("Inventory", "turnover ($)",          f"{s['turnover_usd']:,.2f}"),
        ]
        idx = pd.MultiIndex.from_tuples(
            [(g, m) for g, m, _ in rows], names=["group", "metric"]
        )
        return pd.DataFrame({"value": [v for _, _, v in rows]}, index=idx)

    def plot(self, height: int = 1100, tick_size: float | None = None):
        trade_fills = self.fills[self.fills["side"].isin(["bid", "ask"])]

        # --- PnL decomposition: spread capture vs inventory drift ---
        spread_pnl = pd.Series(dtype=float)
        inv_drift  = pd.Series(dtype=float)
        if len(trade_fills) and len(self.quotes):
            fills_m = pd.merge_asof(
                trade_fills[["side", "price", "size"]].sort_index(),
                self.quotes[["mid"]].sort_index(),
                left_index=True, right_index=True,
                direction="backward",
            ).dropna(subset=["mid"])
            per_fill = np.where(
                fills_m["side"] == "bid",
                (fills_m["mid"] - fills_m["price"]) * fills_m["size"],
                (fills_m["price"] - fills_m["mid"]) * fills_m["size"],
            )
            cum_spread = pd.Series(per_fill.cumsum(), index=fills_m.index)
            cs_df  = pd.DataFrame({"val": cum_spread.values}, index=cum_spread.index)
            pnl_df = pd.DataFrame({"t": self.pnl.index}, index=self.pnl.index)
            merged = pd.merge_asof(
                pnl_df.sort_index(), cs_df.sort_index(),
                left_index=True, right_index=True,
                direction="backward",
            )
            spread_pnl = pd.Series(merged["val"].fillna(0.0).values, index=self.pnl.index)
            inv_drift  = self.pnl - spread_pnl

        # --- Quote offsets from mid ---
        if len(self.quotes):
            divisor    = tick_size if tick_size else 1.0
            ylabel_off = "ticks" if tick_size else "price units"
            bid_off = (self.quotes["bid"] - self.quotes["mid"]) / divisor
            ask_off = (self.quotes["ask"] - self.quotes["mid"]) / divisor
        else:
            ylabel_off = ""

        # --- Cumulative signed fill imbalance ---
        cum_imbalance = pd.Series(dtype=float)
        if len(trade_fills) > 1:
            signed        = trade_fills["side"].map({"bid": 1.0, "ask": -1.0})
            cum_imbalance = signed.cumsum()

        fig = make_subplots(
            rows=4, cols=1, shared_xaxes=True,
            row_heights=[0.15, 0.30, 0.25, 0.30],
            vertical_spacing=0.06,
            subplot_titles=(
                f"Quote offset from mid ({ylabel_off})",
                "PnL",
                "Inventory",
                "Cumulative fill imbalance (bid fills − ask fills)",
            ),
        )

        if len(self.quotes):
            fig.add_trace(go.Scatter(
                x=self.quotes.index, y=ask_off,
                mode="lines", name="ask offset",
                line=dict(width=1, dash="dot", color="red")), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=self.quotes.index, y=bid_off,
                mode="lines", name="bid offset",
                line=dict(width=1, dash="dot", color="lime")), row=1, col=1)
            fig.add_hline(y=0, line=dict(width=0.5, dash="dot", color="gray"), row=1, col=1)

        scale = 100.0 / self.capital
        fig.add_trace(go.Scatter(
            x=self.pnl.index, y=self.pnl.values * scale,
            mode="lines", name="total PnL",
            line=dict(color="cyan", width=2)), row=2, col=1)
        if len(spread_pnl):
            fig.add_trace(go.Scatter(
                x=spread_pnl.index, y=spread_pnl.values * scale,
                mode="lines", name="spread capture",
                line=dict(color="lime", dash="dot")), row=2, col=1)
            fig.add_trace(go.Scatter(
                x=inv_drift.index, y=inv_drift.values * scale,
                mode="lines", name="inventory drift",
                line=dict(color="orange", dash="dot")), row=2, col=1)
        fig.add_hline(y=0, line=dict(width=0.5, dash="dot", color="gray"), row=2, col=1)
        fig.update_yaxes(title_text="% of capital", row=2, col=1)

        fig.add_trace(go.Scatter(
            x=self.inventory.index, y=self.inventory.values,
            mode="lines", name="inventory",
            line=dict(color="orange")), row=3, col=1)
        fig.add_hline(y=0, line=dict(width=0.5, dash="dot", color="gray"), row=3, col=1)

        if len(cum_imbalance):
            fig.add_trace(go.Scatter(
                x=cum_imbalance.index, y=cum_imbalance.values,
                mode="lines", name="cum imbalance",
                line=dict(color="magenta")), row=4, col=1)
            fig.add_hline(y=0, line=dict(width=0.5, dash="dot", color="gray"), row=4, col=1)

        fig.update_layout(
            template=DARK, height=height, showlegend=True,
            legend=dict(orientation="v", x=1.02, y=1, xanchor="left", yanchor="top"),
            margin=dict(r=160),
        )
        return fig
