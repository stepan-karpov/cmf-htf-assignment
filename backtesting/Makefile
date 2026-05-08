PYTHON   := python3
CXX      := clang++
CXXFLAGS := -O3 -march=native -std=c++17 -fPIC -Wall

PYBIND   := $(shell $(PYTHON) -c "import pybind11; print(pybind11.get_include())")
NUMPY    := $(shell $(PYTHON) -c "import numpy; print(numpy.get_include())")
PYINC    := $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_path('include'))")
SUFFIX   := $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX'))")

TARGET   := _engine$(SUFFIX)
HEADERS  := engine/orderbook.hpp engine/execution.hpp engine/result.hpp \
            engine/strategy.hpp  engine/reader.hpp    engine/backtester.hpp

$(TARGET): bindings.cpp $(HEADERS)
	$(CXX) $(CXXFLAGS) -shared \
		-I$(PYBIND) -I$(NUMPY) -I$(PYINC) \
		-undefined dynamic_lookup \
		bindings.cpp -o $@
	@echo "Built: $(TARGET)"

clean:
	rm -f _engine*.so _engine*.dylib

.PHONY: clean
