# Linux Makefile for running BunkrDownloader with venv in the current workspace
# Examples:
#   make venv
#   make run-batch
#   make run-single URL="https://bunkr.si/a/PUK068QE" EXTRA="--ignore .zip"

SHELL := /bin/bash

PYTHON ?= python3
WORKSPACE_DIR := $(CURDIR)
VENV_DIR := $(WORKSPACE_DIR)/myenv
PYTHON_BIN := $(VENV_DIR)/bin/python
PIP := $(PYTHON_BIN) -m pip

.DEFAULT_GOAL := help

# Create venv and install dependencies
$(VENV_DIR)/.installed: requirements.txt
	@echo "Creating virtual environment in $(WORKSPACE_DIR)..."
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "Installing dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@touch $@

.PHONY: venv
venv: $(VENV_DIR)/.installed

.PHONY: run-batch
run-batch: venv  ## Run main.py which reads URLs.txt
	$(PYTHON_BIN) main.py $(EXTRA)

.PHONY: run-single
run-single: venv  ## Run downloader.py for a single URL (make run-single URL=<url>)
ifndef URL
	$(error You must provide URL, for example: make run-single URL="https://bunkr.si/a/PUK068QE")
endif
	$(PYTHON_BIN) downloader.py $(URL) $(EXTRA)

.PHONY: clean
clean:  ## Remove the venv and Downloads
	@if [ -d "$(VENV_DIR)" ]; then rm -rf "$(VENV_DIR)"; fi
	@if [ -d "$(WORKSPACE_DIR)/Downloads" ]; then rm -rf "$(WORKSPACE_DIR)/Downloads"; fi

.PHONY: help
help:
	@echo ""
	@echo "Usage:"
	@echo "  make venv          Create virtual environment and install dependencies"
	@echo "  make run-batch     Run main.py (batch mode using URLs.txt)"
	@echo "  make run-single    Run downloader.py for one URL (provide URL=...)"
	@echo "  make clean         Remove virtual environment and Downloads folder"
	@echo ""
