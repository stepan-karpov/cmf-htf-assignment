#pragma once
#include "orderbook.hpp"
#include <vector>

// ─── Order / Fill ─────────────────────────────────────────────────────────────

struct Order {
    bool   is_bid;
    double price;
    double size;
};

struct Fill {
    // 0 = bid, 1 = ask, 2 = markout
    int    side;
    double price;
    double size;
};

// ─── ExecutionModel (abstract) ────────────────────────────────────────────────

class ExecutionModel {
public:
    virtual ~ExecutionModel() = default;

    // Match active orders against one incoming trade.
    //   has_bid / has_ask   — updated in-place (cleared on fill)
    //   bid / ask           — updated in-place
    //   ob                  — apply_trade called in-place
    //   fills_out           — filled events appended here
    virtual void match(
        bool& has_bid, Order& bid,
        bool& has_ask, Order& ask,
        OrderBook& ob,
        bool is_sell, double trade_price, double trade_amount,
        std::vector<Fill>& fills_out
    ) = 0;
};

// ─── PessimisticExecution ─────────────────────────────────────────────────────
// We are last in queue at our price level.
// Fill only if trade_amount > LOB volume at our price.

class PessimisticExecution : public ExecutionModel {
public:
    void match(
        bool& has_bid, Order& bid,
        bool& has_ask, Order& ask,
        OrderBook& ob,
        bool is_sell, double trade_price, double trade_amount,
        std::vector<Fill>& fills_out
    ) override {
        if (has_bid && is_sell && trade_price <= bid.price) {
            double leftover = trade_amount - ob.queue_at(true, bid.price);
            if (leftover > 0.0) {
                fills_out.push_back({0, bid.price,
                                     bid.size < leftover ? bid.size : leftover});
                has_bid = false;
            }
        }
        if (has_ask && !is_sell && trade_price >= ask.price) {
            double leftover = trade_amount - ob.queue_at(false, ask.price);
            if (leftover > 0.0) {
                fills_out.push_back({1, ask.price,
                                     ask.size < leftover ? ask.size : leftover});
                has_ask = false;
            }
        }
        ob.apply_trade(is_sell, trade_price, trade_amount);
    }
};
