#!/usr/bin/env bash
# Installs forge-std at a pinned commit for contracts/reference.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
dest="$root/contracts/reference/lib/forge-std"
tag=v1.9.7
commit=77041d2ce690e692d6e03cc812b57d1ddaa4d505

if [[ -d "$dest/.git" && "$(git -C "$dest" rev-parse HEAD)" == "$commit" ]]; then
  exit 0
fi

rm -rf "$dest"
git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$tag" https://github.com/foundry-rs/forge-std "$dest"
actual=$(git -C "$dest" rev-parse HEAD)
if [[ "$actual" != "$commit" ]]; then
  echo "forge-std $tag resolved to $actual, expected $commit" >&2
  exit 1
fi
