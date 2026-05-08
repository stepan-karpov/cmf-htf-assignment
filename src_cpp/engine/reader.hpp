#pragma once
#include "orderbook.hpp"
#include <cstdint>
#include <cstdlib>   // strtod, strtoll
#include <fstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

// ─────────────────────────────────────────────────────────────────────────────
// Streaming CSV helpers
// ─────────────────────────────────────────────────────────────────────────────

namespace detail {

// Split a line in-place into string_views (no allocation).
// All views point into `line`; valid until line is modified.
inline void split_csv(const std::string& line,
                      std::vector<std::string_view>& out) {
    out.clear();
    const char* p   = line.data();
    const char* end = p + line.size();
    while (p <= end) {
        const char* q = p;
        while (q < end && *q != ',') ++q;
        out.emplace_back(p, static_cast<std::size_t>(q - p));
        p = q + 1;
    }
}

// strtod/strtoll stop at the first non-numeric char (comma, \0, etc.).
// Safe here because all views point into a null-terminated std::string.
inline double  to_f64(std::string_view sv) { return std::strtod(sv.data(), nullptr); }
inline int64_t to_i64(std::string_view sv) { return (int64_t)std::strtoll(sv.data(), nullptr, 10); }

inline int find_col(const std::vector<std::string_view>& hdr,
                    std::string_view name) {
    for (int i = 0; i < (int)hdr.size(); ++i)
        if (hdr[i] == name) return i;
    throw std::runtime_error("Column not found: " + std::string(name));
}

} // namespace detail

// ─────────────────────────────────────────────────────────────────────────────
// LobReader — streams lob.csv row-by-row, maintains OrderBook state
//
// Usage:
//   LobReader lob("data/lob_train.csv");
//   while (lob.valid()) {
//       use lob.orderbook(), lob.timestamp();
//       lob.advance();
//   }
// ─────────────────────────────────────────────────────────────────────────────

class LobReader {
    std::ifstream             _file;
    std::string               _line;
    std::vector<std::string_view> _fields;

    OrderBook _ob;
    bool      _valid = false;

    int _col_ts = -1;
    int _col_bid_p[LOB_LEVELS], _col_bid_a[LOB_LEVELS];
    int _col_ask_p[LOB_LEVELS], _col_ask_a[LOB_LEVELS];

    void _parse_header() {
        std::getline(_file, _line);
        detail::split_csv(_line, _fields);
        _col_ts = detail::find_col(_fields, "local_timestamp");
        for (int i = 0; i < LOB_LEVELS; ++i) {
            _col_bid_p[i] = detail::find_col(_fields,
                "bids[" + std::to_string(i) + "].price");
            _col_bid_a[i] = detail::find_col(_fields,
                "bids[" + std::to_string(i) + "].amount");
            _col_ask_p[i] = detail::find_col(_fields,
                "asks[" + std::to_string(i) + "].price");
            _col_ask_a[i] = detail::find_col(_fields,
                "asks[" + std::to_string(i) + "].amount");
        }
    }

    bool _read_row() {
        while (std::getline(_file, _line)) {
            if (!_line.empty() && _line.back() == '\r') _line.pop_back();
            if (_line.empty()) continue;
            detail::split_csv(_line, _fields);
            if ((int)_fields.size() <= _col_ts) continue;

            double bp[LOB_LEVELS], ba[LOB_LEVELS];
            double ap[LOB_LEVELS], aa[LOB_LEVELS];
            for (int k = 0; k < LOB_LEVELS; ++k) {
                bp[k] = detail::to_f64(_fields[_col_bid_p[k]]);
                ba[k] = detail::to_f64(_fields[_col_bid_a[k]]);
                ap[k] = detail::to_f64(_fields[_col_ask_p[k]]);
                aa[k] = detail::to_f64(_fields[_col_ask_a[k]]);
            }
            _ob.refresh(bp, ba, ap, aa, detail::to_i64(_fields[_col_ts]));
            return true;
        }
        return false;
    }

public:
    explicit LobReader(const std::string& path) : _file(path) {
        if (!_file.is_open())
            throw std::runtime_error("Cannot open LOB file: " + path);
        _fields.reserve(110);
        _parse_header();
        _valid = _read_row();
    }

    bool             valid()     const noexcept { return _valid; }
    int64_t          timestamp() const noexcept { return _ob.timestamp_us; }

    // Non-const: exec.match() calls ob.apply_trade() in-place.
    // ob state is overwritten on the next advance() call.
    OrderBook&       orderbook()       noexcept { return _ob; }
    const OrderBook& orderbook() const noexcept { return _ob; }

    void advance() { _valid = _read_row(); }
};

// ─────────────────────────────────────────────────────────────────────────────
// TradeReader — streams trades.csv row-by-row
// ─────────────────────────────────────────────────────────────────────────────

struct TradeEvent {
    int64_t t_us;
    bool    is_sell;
    double  price;
    double  amount;
};

class TradeReader {
    std::ifstream             _file;
    std::string               _line;
    std::vector<std::string_view> _fields;

    TradeEvent _ev{};
    bool       _valid = false;

    int _col_ts, _col_side, _col_price, _col_amount;

    void _parse_header() {
        std::getline(_file, _line);
        detail::split_csv(_line, _fields);
        _col_ts     = detail::find_col(_fields, "local_timestamp");
        _col_side   = detail::find_col(_fields, "side");
        _col_price  = detail::find_col(_fields, "price");
        _col_amount = detail::find_col(_fields, "amount");
    }

    bool _read_row() {
        while (std::getline(_file, _line)) {
            if (!_line.empty() && _line.back() == '\r') _line.pop_back();
            if (_line.empty()) continue;
            detail::split_csv(_line, _fields);
            if ((int)_fields.size() <= _col_amount) continue;
            _ev.t_us    = detail::to_i64(_fields[_col_ts]);
            _ev.is_sell = (_fields[_col_side] == "sell");
            _ev.price   = detail::to_f64(_fields[_col_price]);
            _ev.amount  = detail::to_f64(_fields[_col_amount]);
            return true;
        }
        return false;
    }

public:
    explicit TradeReader(const std::string& path) : _file(path) {
        if (!_file.is_open())
            throw std::runtime_error("Cannot open trades file: " + path);
        _fields.reserve(10);
        _parse_header();
        _valid = _read_row();
    }

    bool              valid()     const noexcept { return _valid; }
    int64_t           timestamp() const noexcept { return _ev.t_us; }
    const TradeEvent& event()     const noexcept { return _ev; }

    void advance() { _valid = _read_row(); }
};
