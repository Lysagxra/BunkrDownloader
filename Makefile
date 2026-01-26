# Makefile using uv with pyproject.toml
# Examples:
#   make sync
#   make run-batch
#   make run-single URL="https://bunkr.si/a/PUK068QE" EXTRA="--ignore .zip"

SHELL := /bin/bash

UV := uv
PY := uv run python

.DEFAULT_GOAL := help

.PHONY: sync
sync:
	@echo "Syncing environment with uv..."
	$(UV) sync

.PHONY: run-batch
run-batch: sync
	$(PY) main.py $(EXTRA)

.PHONY: run-single
run-single: sync
ifndef URL
	$(error You must provide URL, for example: make run-single URL="https://bunkr.si/a/PUK068QE")
endif
	$(PY) downloader.py $(URL) $(EXTRA)

.PHONY: clean
clean:
	@if [ -d ".venv" ]; then rm -rf ".venv"; fi
	@if [ -d "Downloads" ]; then rm -rf "Downloads"; fi

.PHONY: help
help:
	@echo ""
	@echo "Usage:"
	@echo "  make sync          Create or update the uv environment from pyproject.toml"
	@echo "  make run-batch     Run main.py using URLs.txt"
	@echo "  make run-single    Run downloader.py for one URL (provide URL=...)"
	@echo "  make clean         Remove .venv and Downloads"
	@echo ""
