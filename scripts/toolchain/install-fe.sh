#!/usr/bin/env bash
# Installs a pinned Fe release into .tools/ after verifying its SHA-256: the one
# in fe.lock, or in the lock file given as the first argument. Prints the
# installed binary path on stdout.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
lock="${1:-$root/scripts/toolchain/fe.lock}"

lock_value() { sed -n "s/^$1=//p" "$lock"; }

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) platform=linux_amd64 ;;
  Linux-aarch64 | Linux-arm64) platform=linux_arm64 ;;
  Darwin-x86_64) platform=mac_amd64 ;;
  Darwin-arm64) platform=mac_arm64 ;;
  *) echo "unsupported platform: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

version=$(lock_value version)
expected=$(lock_value "sha256_$platform")
dest="$root/.tools/fe-$version"
bin="$dest/fe"

sha256() {
  if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

if [[ -x "$bin" && "$(sha256 "$bin")" == "$expected" ]]; then
  echo "$bin"
  exit 0
fi

mkdir -p "$dest"
tmp=$(mktemp "$dest/fe.XXXXXX")
trap 'rm -f "$tmp"' EXIT
curl -fsSL --retry 3 -o "$tmp" "$(lock_value url)/fe_$platform"

actual=$(sha256 "$tmp")
if [[ "$actual" != "$expected" ]]; then
  echo "checksum mismatch for fe_$platform: expected $expected, got $actual" >&2
  exit 1
fi

chmod +x "$tmp"
mv "$tmp" "$bin"
trap - EXIT
echo "$bin"
