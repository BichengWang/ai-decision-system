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

RELIA_DIR := ai-workflows/ai-decision-reliability
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

EXPGATE_DIR := ai-workflows/experiment-gate
EXPGATE_OUT ?=

.PHONY: expgate-test expgate-run
expgate-test:
	cd $(EXPGATE_DIR) && python3 -m unittest discover -s tests -v

expgate-run:
	@test -n "$(EXPGATE_OUT)" || { echo "Set EXPGATE_OUT to a new absolute output directory"; exit 2; }
	cd $(EXPGATE_DIR) && python3 -m expgate.run --all-scenarios --out "$(EXPGATE_OUT)"

JEV_DIR := ai-workflows/jev-decision

.PHONY: jev-test jev-dry-run jev-eval
jev-test:
	cd $(JEV_DIR) && python3 -m unittest discover -s tests -v

jev-dry-run:
	cd $(JEV_DIR) && for backend in jev openai; do \
		python3 -m jevdecision --questions examples/support-ticket.json \
			--state "Help! My payouts have been failing for 3 days." --backend $$backend --dry-run || exit 1; \
	done

jev-eval:
	cd $(JEV_DIR) && out=$$(mktemp -d) && python3 -m jevdecision.evaluation \
		--questions examples/support-ticket.json --cases examples/support-ticket-cases.jsonl \
		--responses examples/support-ticket-responses.jsonl \
		--require examples/support-ticket-requirements.json --out "$$out" && cat "$$out/EVALUATION.md"

# Workspace commands read workspace.json (see ai-workflows/README.md).
WORKSPACE := python3 scripts/workspace.py
BASE ?= origin/main
COMPONENTS ?=

.PHONY: workspace-list workspace-check workspace-test workspace-new affected affected-test
workspace-list:
	$(WORKSPACE) list

workspace-check:
	python3 -m unittest discover -s scripts/tests -p 'test_workspace.py'
	$(WORKSPACE) check

workspace-test:
	@test -n "$(COMPONENTS)" || { echo "Set COMPONENTS to component names from 'make workspace-list'"; exit 2; }
	$(WORKSPACE) test $(COMPONENTS)

workspace-new:
	@test -n "$(NAME)" && test -n "$(SUMMARY)" || { echo 'Set NAME=<project-dir> and SUMMARY="<one line>"'; exit 2; }
	$(WORKSPACE) new "$(NAME)" --summary "$(SUMMARY)"

affected:
	$(WORKSPACE) affected --base "$(BASE)"

affected-test:
	$(WORKSPACE) test --affected --base "$(BASE)"


.PHONY: bootstrap
bootstrap:
	pip3 install -U "pip>=25.0.1" "setuptools>=75.8.0" wheel "pip-tools>=44.0.0"
	pip3 install --no-deps -r requirements.txt --no-cache-dir
	pip3 install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu123

.PHONY: compile
compile:
	pip-compile requirements.in

.PHONY: env
env:
	python3 -m venv venv

# Lint only what the baseline covers; the wider src/ tree has ~1300 legacy findings.
baseline_lint := tests $(wildcard src/lc/*_test.py src/lc/*/*_test.py)

.PHONY: lint
lint:
	python3 -m flake8 $(baseline_lint)

# Baseline check for the research workbench (see [tool.pytest.ini_options] in pyproject.toml).
# Needs: pip install -c requirements.txt pytest pytest-custom-exit-code flake8 pandas tabulate
# FILE_NAME=<file> runs one file under tests/ instead of the whole baseline.
.PHONY: test
test: clean lint
	SIM_TEST_MODE=true $(pytest) -k "not personal_transport_e2e" $(if $(FILE_NAME),tests/$(FILE_NAME),) $(pytest_extra_args)

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
