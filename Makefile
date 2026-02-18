# Makefile for spectrik

# use a local.env file if it exists
-include local.env

BASEDIR ?= $(PWD)
SRCDIR ?= $(BASEDIR)/src

APPNAME ?= $(shell grep -m1 '^name' "$(BASEDIR)/pyproject.toml" | sed -e 's/name.*"\(.*\)"/\1/')
APPVER ?= $(shell grep -m1 '^version' "$(BASEDIR)/pyproject.toml" | sed -e 's/version.*"\(.*\)"/\1/')

WITH_VENV := uv run

export


.PHONY: all
all: venv preflight build


.PHONY: venv
venv:
	uv sync --all-extras
	$(WITH_VENV) pre-commit install --install-hooks --overwrite


uv.lock: venv
	uv lock


.PHONY: tidy
tidy: venv
	$(WITH_VENV) ruff format "$(SRCDIR)" "$(BASEDIR)/tests"
	$(WITH_VENV) ruff check --fix "$(SRCDIR)" "$(BASEDIR)/tests"


.PHONY: build-dist
build-dist: preflight
	uv build


.PHONY: build
build: build-dist


.PHONY: release
release: preflight
	git tag "v$(APPVER)" main
	git push origin "v$(APPVER)"


.PHONY: precommit
precommit: venv
	$(WITH_VENV) pre-commit run --all-files --verbose


.PHONY: unit-tests
unit-tests: venv
	$(WITH_VENV) pytest "$(BASEDIR)/tests"


.PHONY: test
test: unit-tests


.PHONY: preflight
preflight: precommit unit-tests


.PHONY: clean
clean:
	rm -f "$(BASEDIR)/.coverage"
	rm -Rf "$(BASEDIR)/.pytest_cache"
	rm -Rf "$(BASEDIR)/.ruff_cache"
	find "$(BASEDIR)" -name "*.pyc" -print | xargs rm -f
	find "$(BASEDIR)" -name '__pycache__' -print | xargs rm -Rf


.PHONY: clobber
clobber: clean
	$(WITH_VENV) pre-commit uninstall || true
	rm -Rf "$(BASEDIR)/dist"
	rm -Rf "$(BASEDIR)/.venv"
	rm -f "$(BASEDIR)"/*.log
