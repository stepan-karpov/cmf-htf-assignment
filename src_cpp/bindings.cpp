// ─────────────────────────────────────────────────────────────────────────────
// bindings.cpp — THE ONLY FILE WITH PYTHON INTEROP
//
// Contains:
//   1. PyStrategy  — wraps a Python strategy object, calls on_lob / on_fill
//                    via pybind11. This is the single C++ ↔ Python seam.
//   2. run()       — takes file paths, creates readers, runs C++ Backtester,
//                    writes result CSVs to disk.
//   3. pybind11 module definition.
//
// All business logic lives in engine/*.hpp (pure C++, no Python headers).
// ─────────────────────────────────────────────────────────────────────────────

#include <pybind11/pybind11.h>

#include "engine/backtester.hpp"
#include "engine/execution.hpp"
#include "engine/orderbook.hpp"
#include "engine/reader.hpp"
#include "engine/result.hpp"
#include "engine/strategy.hpp"

#include <cstdint>
#include <string>

namespace py = pybind11;
using namespace pybind11::literals;

// ─── PyStrategy: the C++ ↔ Python seam ───────────────────────────────────────
//
// on_lob: strategy returns list[(side_str, price, size)]; parsed to vector<Order>.
// on_fill: called with primitive args (t_us, side_str, price, size).

class PyStrategy : public StrategyBase {
    py::object _on_lob;
    py::object _on_fill;

public:
    explicit PyStrategy(py::object strategy)
        : _on_lob (strategy.attr("on_lob"))
        , _on_fill(strategy.attr("on_fill"))
    {}

    std::vector<Order> on_lob(const OrderBook& ob, double inventory) override {
        py::object ret = _on_lob(
            py::cast(&ob, py::return_value_policy::reference),
            inventory
        );
        std::vector<Order> orders;
        for (auto item : ret) {
            auto tup = item.cast<py::tuple>();
            const char s = tup[0].cast<std::string>()[0];  // 'b' or 'a'
            orders.push_back({
                s == 'b',
                tup[1].cast<double>(),
                tup[2].cast<double>()
            });
        }
        return orders;
    }

    void on_fill(int64_t t_us, const Fill& f) override {
        static const char* SIDES[] = {"bid", "ask", "markout"};
        _on_fill(t_us, SIDES[f.side], f.price, f.size);
    }
};

// ─── run(): file paths → C++ Backtester → CSV files ──────────────────────────

static void run(
    py::object         strategy,
    const std::string& lob_path,
    const std::string& trades_path,
    int64_t            latency_us,
    int64_t            log_interval_us,
    int64_t            quote_log_stride,
    const std::string& output_path
) {
    PyStrategy           py_strat(std::move(strategy));
    PessimisticExecution exec;
    Backtester           bt(latency_us, log_interval_us, quote_log_stride);
    LobReader            lob(lob_path);
    TradeReader          trades(trades_path);

    RunData data = bt.run(py_strat, exec, lob, trades);
    data.save_csv(output_path);
}

// ─── pybind11 module ──────────────────────────────────────────────────────────

PYBIND11_MODULE(_engine, m) {
    m.doc() = "C++ backtester engine";

    py::class_<OrderBook>(m, "OrderBook")
        .def_property_readonly("best_bid",    &OrderBook::best_bid)
        .def_property_readonly("best_ask",    &OrderBook::best_ask)
        .def_property_readonly("mid",         &OrderBook::mid)
        .def_property_readonly("spread",      &OrderBook::spread)
        .def_property_readonly("timestamp_us",
            [](const OrderBook& ob) { return ob.timestamp_us; })
        .def_property_readonly("bids", [](const OrderBook& ob) {
            py::list r;
            for (const auto& l : ob.bids) {
                py::list row; row.append(l.price); row.append(l.amount);
                r.append(row);
            }
            return r;
        })
        .def_property_readonly("asks", [](const OrderBook& ob) {
            py::list r;
            for (const auto& l : ob.asks) {
                py::list row; row.append(l.price); row.append(l.amount);
                r.append(row);
            }
            return r;
        });

    m.def("run", &run,
        "strategy"_a,
        "lob_path"_a, "trades_path"_a,
        "latency_us"_a, "log_interval_us"_a, "quote_log_stride"_a,
        "output_path"_a
    );
}
