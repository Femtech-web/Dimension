SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

PYTHON ?= python3
HARNESS := PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts $(PYTHON) -m harness.
CASES := $(HARNESS)cases
FE := .tools/fe-$(shell sed -n 's/^version=//p' scripts/toolchain/fe.lock)/fe
# The feasibility probes are kept exactly as recorded, so they are not formatted.
FORMATTED := ingots tests/core tests/oracle tests/explorer tests/compile_fail

.PHONY: help toolchain reference-deps fmt fmt-check test unit compile-fail probes differential explore evm fidelity moonwell unsafe-policy page show demo update ci

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

toolchain: ## Install the pinned Fe compiler into .tools/ (checksum verified)
	@scripts/toolchain/install-fe.sh >/dev/null

reference-deps: ## Install the pinned forge-std used by contracts/reference
	@scripts/reference/install-deps.sh

fmt: toolchain ## Format Fe sources
	@for path in $(FORMATTED); do $(FE) fmt $$path; done

fmt-check: toolchain ## Fail if any Fe source is not formatted
	@status=0; for path in $(FORMATTED); do $(FE) fmt --check $$path || status=1; done; exit $$status

test: unit compile-fail probes ## Run every suite

unit: toolchain ## Dimension API tests on EVM and native
	@$(CASES) unit

compile-fail: toolchain ## Code that must not compile, with the mechanism each case blocks
	@$(CASES) compile-fail

probes: toolchain ## The Fe 26.6 feasibility probes the design rests on
	@$(CASES) probes

differential: toolchain reference-deps ## Fe port vs Balancer V2's Solidity on identical calldata (needs forge)
	@$(HARNESS)differential

explore: toolchain ## Native search and repeated attacks on the faithful, typed and guarded Balancer kernels
	@$(HARNESS)explore

evm: toolchain reference-deps ## The three Fe pool contracts on a real EVM: repeated-exit attack and gas (needs forge)
	@$(HARNESS)evm

fidelity: toolchain reference-deps ## The Fe port against the deployed exploited pool on a mainnet fork (needs forge and an archive RPC)
	@$(HARNESS)fidelity

moonwell: toolchain reference-deps ## Moonwell's cbETH market on Base forks around MIP-X43 (needs forge and a Base RPC)
	@$(HARNESS)moonwell

page: toolchain ## Render docs/index.html, the verification page, from the saved reports
	@$(HARNESS)page

show: toolchain ## Show one compile-fail case live: make show CASE=<name> (all cases if omitted)
	@$(HARNESS)show $(CASE)

demo: toolchain ## The two incidents: Moonwell MIP-X43, and Balancer V2's _upscale put back into the typed pool
	@$(HARNESS)show moonwell_component_feed_in_usd_market typed_pool_with_balancer_upscale

update: toolchain ## Regenerate golden files for every suite (review the diff before keeping it)
	@for suite in unit compile-fail probes; do $(CASES) $$suite --update; done

# Ingots that contracts are built from. Only Dimension's own test constructors
# may be unsafe, and none of these may reach them.
PROTOCOL := dimension balancer_v2 moonwell

unsafe-policy: ## Fail if a protocol ingot could forge a trusted value
	@if grep -n allow_unsafe $(PROTOCOL:%=ingots/%/fe.toml); then echo "a protocol ingot sets allow_unsafe"; exit 1; fi
	@if grep -rnE '\bunsafe\b' $(PROTOCOL:%=ingots/%/src) | grep -v ingots/dimension/src/value/testing.fe | grep -vE ':[0-9]+:\s*//'; then \
		echo "unsafe code outside dimension::value::testing"; exit 1; fi

ci: fmt-check unsafe-policy test differential explore evm ## Everything CI runs
