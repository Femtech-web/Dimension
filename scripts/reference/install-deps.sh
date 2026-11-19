#!/usr/bin/env bash
# Installs the Solidity dependencies of contracts/reference at pinned commits:
# forge-std, and OpenZeppelin Contracts for the ERC4626 the vault is compared with.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

install() {
  local name=$1 repo=$2 tag=$3 commit=$4
  local dest="$root/contracts/reference/lib/$name"
  if [[ -d "$dest/.git" && "$(git -C "$dest" rev-parse HEAD)" == "$commit" ]]; then
    return 0
  fi
  rm -rf "$dest"
  git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$tag" "https://github.com/$repo" "$dest"
  local actual
  actual=$(git -C "$dest" rev-parse HEAD)
  if [[ "$actual" != "$commit" ]]; then
    echo "$name $tag resolved to $actual, expected $commit" >&2
    exit 1
  fi
}

install forge-std foundry-rs/forge-std v1.9.7 77041d2ce690e692d6e03cc812b57d1ddaa4d505
install openzeppelin-contracts OpenZeppelin/openzeppelin-contracts v5.1.0 69c8def5f222ff96f2b5beff05dfba996368aa79
