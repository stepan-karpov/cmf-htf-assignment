#pragma once
#include "execution.hpp"
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

struct RunData {
    std::vector<int64_t> pnl_t;
    std::vector<double>  pnl_v, inv_v;

    std::vector<int64_t> qt_t;
    std::vector<double>  qt_bid, qt_ask, qt_mid;

    std::vector<int64_t> fill_t;
    std::vector<int32_t> fill_side;
    std::vector<double>  fill_price, fill_size, fill_inv;

    void reserve(std::size_t n_lob_hint, std::size_t n_fill_hint) {
        pnl_t.reserve(n_lob_hint / 10);
        pnl_v.reserve(n_lob_hint / 10);
        inv_v.reserve(n_lob_hint / 10);
        fill_t.reserve(n_fill_hint);
        fill_side.reserve(n_fill_hint);
        fill_price.reserve(n_fill_hint);
        fill_size.reserve(n_fill_hint);
        fill_inv.reserve(n_fill_hint);
    }

    // ── write API (called by Backtester) ──────────────────────────────────────

    void add_pnl_snapshot(int64_t t, double pnl, double inv) {
        pnl_t.push_back(t);
        pnl_v.push_back(pnl);
        inv_v.push_back(inv);
    }

    void add_quote(int64_t t,
                   bool has_bid, double bid_price,
                   bool has_ask, double ask_price,
                   double mid) {
        static const double kNaN = std::numeric_limits<double>::quiet_NaN();
        qt_t.push_back(t);
        qt_bid.push_back(has_bid ? bid_price : kNaN);
        qt_ask.push_back(has_ask ? ask_price : kNaN);
        qt_mid.push_back(mid);
    }

    void add_fill(int64_t t, const Fill& f, double inv_after) {
        fill_t.push_back(t);
        fill_side.push_back(f.side);
        fill_price.push_back(f.price);
        fill_size.push_back(f.size);
        fill_inv.push_back(inv_after);
    }

    // ── serialisation ─────────────────────────────────────────────────────────
    // Writes three CSV files:
    //   {prefix}_pnl.csv    — t_us, pnl, inventory
    //   {prefix}_quotes.csv — t_us, bid, ask, mid
    //   {prefix}_fills.csv  — t_us, side, price, size, inventory

    void save_csv(const std::string& prefix) const {
        static const char* SIDES[] = {"bid", "ask", "markout"};

        auto dbl = [](double v) -> std::string {
            if (std::isnan(v)) return "";
            std::ostringstream os;
            os << std::setprecision(12) << v;
            return os.str();
        };

        {
            std::ofstream f(prefix + "_pnl.csv");
            f << "t_us,pnl,inventory\n";
            for (std::size_t i = 0; i < pnl_t.size(); ++i)
                f << pnl_t[i] << ',' << dbl(pnl_v[i]) << ',' << dbl(inv_v[i]) << '\n';
        }
        {
            std::ofstream f(prefix + "_quotes.csv");
            f << "t_us,bid,ask,mid\n";
            for (std::size_t i = 0; i < qt_t.size(); ++i)
                f << qt_t[i] << ','
                  << dbl(qt_bid[i]) << ',' << dbl(qt_ask[i]) << ',' << dbl(qt_mid[i]) << '\n';
        }
        {
            std::ofstream f(prefix + "_fills.csv");
            f << "t_us,side,price,size,inventory\n";
            for (std::size_t i = 0; i < fill_t.size(); ++i)
                f << fill_t[i] << ','
                  << SIDES[fill_side[i]] << ','
                  << dbl(fill_price[i]) << ','
                  << dbl(fill_size[i]) << ','
                  << dbl(fill_inv[i]) << '\n';
        }
    }
};
