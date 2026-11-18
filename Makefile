SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

PYTHON ?= python3
HARNESS := PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts $(PYTHON) -m harness.
CASES := $(HARNESS)cases
FE := .tools/fe-$(shell sed -n 's/^version=//p' scripts/toolchain/fe.lock)/fe
# The feasibility probes are kept exactly as recorded, so they are not formatted.
FORMATTED := ingots tests/core tests/oracle tests/compile_fail

.PHONY: help toolchain reference-deps fmt fmt-check test unit compile-fail probes differential update ci

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

toolchain: ## Install the pinned Fe compiler into .tools/ (checksum verified)
	@scripts/toolchain/install-fe.sh >/dev/null

reference-deps: ## Install the pinned forge-std used by contracts/reference
	@scripts/reference/install-deps.sh

fmt: toolchain ## Format Fe sources
	@for path in $(FORMATTED); do $(FE) fmt $$path; done

fmt-check: toolchain ## Fail if any Fe source is not formatted
	@for path in $(FORMATTED); do $(FE) fmt --check $$path; done

test: unit compile-fail probes ## Run every suite

unit: toolchain ## Dimension API tests on EVM and native
	@$(CASES) unit

compile-fail: toolchain ## Code that must not compile, with the mechanism each case blocks
	@$(CASES) compile-fail

probes: toolchain ## The Fe 26.6 feasibility probes the design rests on
	@$(CASES) probes

differential: toolchain reference-deps ## Fe port vs Balancer V2's Solidity on identical calldata (needs forge)
	@$(HARNESS)differential

update: toolchain ## Regenerate golden files for every suite (review the diff before keeping it)
	@for suite in unit compile-fail probes; do $(CASES) $$suite --update; done

ci: fmt-check test differential ## Everything CI runs
