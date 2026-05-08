#pragma once
#include "execution.hpp"
#include "orderbook.hpp"
#include "reader.hpp"
#include "result.hpp"
#include "strategy.hpp"
#include <cstdint>
#include <stdexcept>

// Pure C++ replay engine. No Python types anywhere in this file.
//
// Two-pointer merge of LobReader and TradeReader.
// Trades-first tie-breaking: at equal timestamps, trades processed before LOB.

class Backtester {
    int64_t _latency_us;
    int64_t _log_interval_us;
    int64_t _quote_log_stride;

public:
    Backtester(int64_t latency_us, int64_t log_interval_us, int64_t quote_log_stride)
        : _latency_us(latency_us)
        , _log_interval_us(log_interval_us)
        , _quote_log_stride(quote_log_stride < 1 ? 1 : quote_log_stride)
    {}

    RunData run(
        StrategyBase&    strategy,
        ExecutionModel&  exec,
        LobReader& lob,
        TradeReader&      trades
    ) const {
        if (!lob.valid()) throw std::runtime_error("empty LOB data");

        RunData data;

        double  cash = 0.0, inventory = 0.0;

        bool   has_bid = false, has_ask = false;
        Order  bid_ord{}, ask_ord{};

        bool    has_pending       = false;
        bool    pend_bid = false, pend_ask = false;
        Order   pend_bid_o{}, pend_ask_o{};
        int64_t pending_active_at = 0;

        int64_t last_log_us = lob.timestamp();
        int64_t lob_counter = 0;
        int64_t t_us        = lob.timestamp();

        std::vector<Fill> trade_fills;
        trade_fills.reserve(2);

        while (lob.valid() || trades.valid()) {
            // Trades first on equal timestamps (LOB reflects post-trade state)
            const bool take_lob =
                !trades.valid() ||
                (lob.valid() && lob.timestamp() < trades.timestamp());

            if (take_lob) {
                // ── LOB event ─────────────────────────────────────────────────
                t_us = lob.timestamp();
                OrderBook& ob = lob.orderbook();

                auto orders = strategy.on_lob(ob, inventory);

                bool new_hb = false, new_ha = false;
                Order new_b{}, new_a{};
                for (const auto& o : orders) {
                    if (o.is_bid) { new_hb = true; new_b = o; }
                    else          { new_ha = true; new_a = o; }
                }

                if (_latency_us == 0) {
                    has_bid = new_hb; bid_ord = new_b;
                    has_ask = new_ha; ask_ord = new_a;
                } else {
                    has_pending       = true;
                    pend_bid          = new_hb; pend_bid_o = new_b;
                    pend_ask          = new_ha; pend_ask_o = new_a;
                    pending_active_at = t_us + _latency_us;
                }

                if (lob_counter % _quote_log_stride == 0)
                    data.add_quote(t_us,
                                   has_bid, bid_ord.price,
                                   has_ask, ask_ord.price,
                                   ob.mid());
                ++lob_counter;
                lob.advance();

            } else {
                // ── Trade event ───────────────────────────────────────────────
                t_us = trades.timestamp();
                OrderBook&       ob = lob.orderbook();
                const TradeEvent& ev = trades.event();

                if (has_pending && t_us >= pending_active_at) {
                    has_bid     = pend_bid; bid_ord = pend_bid_o;
                    has_ask     = pend_ask; ask_ord = pend_ask_o;
                    has_pending = false;
                }

                trade_fills.clear();
                exec.match(has_bid, bid_ord, has_ask, ask_ord,
                           ob, ev.is_sell, ev.price, ev.amount,
                           trade_fills);

                for (const auto& f : trade_fills) {
                    if (f.side == 0) { cash -= f.price * f.size; inventory += f.size; }
                    else             { cash += f.price * f.size; inventory -= f.size; }
                    data.add_fill(t_us, f, inventory);
                    strategy.on_fill(t_us, f);
                }
                trades.advance();
            }

            if (t_us - last_log_us >= _log_interval_us) {
                data.add_pnl_snapshot(t_us,
                    cash + inventory * lob.orderbook().mid(), inventory);
                last_log_us = t_us;
            }
        }

        // Final markout — lob.orderbook() retains last valid state
        const double fin_mid = lob.orderbook().mid();
        cash += inventory * fin_mid;
        data.add_fill(t_us, Fill{2, fin_mid, -inventory}, 0.0);
        data.add_pnl_snapshot(t_us, cash, 0.0);

        return data;
    }
};
