#!/usr/bin/env bash
# Builds the Fe compiler with its WebAssembly backend, which the release
# binaries leave out, from the commit pinned in fe.lock, into
# .tools/fe-<version>-wasm/. Needs git, Node.js and Rust 1.96 or later.
# Prints the binary's path on stdout.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
lock="$root/scripts/toolchain/fe.lock"
lock_value() { sed -n "s/^$1=//p" "$lock"; }

version=$(lock_value version)
commit=$(lock_value commit)
dest="$root/.tools/fe-$version-wasm"
bin="$dest/fe"
src="$root/.tools/fe-src"

if [[ -x "$bin" && "$("$bin" --version)" == *"(${commit:0:9})" ]]; then
  echo "$bin"
  exit 0
fi

rust=$(rustc --version | sed -E 's/^rustc ([0-9]+)\.([0-9]+).*/\1 \2/')
if (( ${rust% *} == 1 && ${rust#* } < 96 )); then
  echo "Fe's wasm feature needs Rust 1.96 or later; rustc is $(rustc --version)" >&2
  exit 1
fi

if [[ ! -d "$src/.git" ]]; then
  git clone --quiet https://github.com/argotorg/fe "$src"
fi
git -C "$src" -c advice.detachedHead=false checkout --quiet "$commit" 2>/dev/null \
  || { git -C "$src" fetch --quiet origin && git -C "$src" -c advice.detachedHead=false checkout --quiet "$commit"; }

# The grammar is generated at build time by the tree-sitter CLI, which the
# compiler's own lock file pins.
(cd "$src/crates/tree-sitter-fe" && npm ci --silent >&2)
PATH="$src/crates/tree-sitter-fe/node_modules/.bin:$PATH" \
  cargo build --release --manifest-path "$src/Cargo.toml" -p fe --no-default-features --features wasm >&2

mkdir -p "$dest"
cp "$src/target/release/fe" "$bin"
echo "$bin"
