project := python-notebook
pytest_args := -rs --tb short --junitxml junit.xml --suppress-no-test-exit-code
pytest := py.test $(pytest_args)
file_name := ''
ifdef FILE_NAME
	file_name := $(FILE_NAME)
endif
ifdef TEST_NAME
	pytest_extra_args := -k "$(TEST_NAME)"
endif
server := sim-dev.dev
ifdef SERVER
	server := $(SERVER).dev
endif
ifdef VERSION
    version := $(VERSION)
endif
ifdef LOG_FILE
    log_file := $(LOG_FILE)
endif

.DEFAULT_GOAL := test

RELIA_DIR := projects/ai-decision-reliability-framework
RELIA_OUT ?=
RELIA_REF ?= HEAD

.PHONY: relia-sync relia-test relia-reproduce relia-export relia-export-test
relia-sync:
	cd $(RELIA_DIR) && uv sync --frozen

relia-test:
	cd $(RELIA_DIR) && OMP_NUM_THREADS=$${OMP_NUM_THREADS:-1} OPENBLAS_NUM_THREADS=$${OPENBLAS_NUM_THREADS:-1} MKL_NUM_THREADS=$${MKL_NUM_THREADS:-1} VECLIB_MAXIMUM_THREADS=$${VECLIB_MAXIMUM_THREADS:-1} uv run --frozen python -m pytest -q

relia-reproduce:
	@test -n "$(RELIA_OUT)" || { echo "Set RELIA_OUT to a new absolute output directory"; exit 2; }
	cd $(RELIA_DIR) && bash scripts/reproduce.sh "$(RELIA_OUT)"

relia-export:
	@test -n "$(RELIA_OUT)" || { echo "Set RELIA_OUT to a new absolute export directory"; exit 2; }
	python3 scripts/export-relia.py --source-ref "$(RELIA_REF)" --output "$(RELIA_OUT)"

relia-export-test:
	python3 -m unittest discover -s scripts/tests -p 'test_export_relia.py' -v


.PHONY: bootstrap
bootstrap:
	pip3 install -U pip>=25.0.1 setuptools>=75.8.0 wheel pip-tools>=44.0.0
	pip3 install --no-deps -r requirements.txt --no-cache-dir
	pip3 install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu123

.PHONY: compile
compile:
	pip-compile requirements.in

.PHONY: env
env:
	python3 -m venv venv

.PHONY: test
test: clean lint
	SIM_TEST_MODE=true $(pytest) -k "not personal_transport_e2e" tests/$(file_name) $(pytest_extra_args)

.PHONY: all_test
all_test: test

.PHONY: open_tunnels
open_tunnels:
	echo "Opening tunnels to $(server)"
# 	ssh -fN -L port:localhost:port $(server)

.PHONY: close_tunnels
close_tunnels:
	echo "Closing tunnels"
	kill $$(lsof -ti:port) 2> /dev/null &

.PHONY: clean
clean:
	@find . "(" -name "*.pyc" -o -name "coverage.xml" -o -name "junit.xml" ")" -delete
	@rm -rf coverage
