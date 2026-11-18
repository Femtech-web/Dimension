"""Resolves and runs the pinned Fe compiler."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "scripts" / "toolchain" / "fe.lock"

# The 26.6.0 release builds native executables only on these hosts.
NATIVE_PLATFORMS = {"linux_amd64", "mac_arm64"}

_TIMING = re.compile(r"\s*\[\d+(?:\.\d+)?s\]")


def read_lock() -> dict[str, str]:
    entries = {}
    for line in LOCK.read_text().splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            entries[key] = value
    return entries


def host_platform() -> str:
    system = {"Linux": "linux", "Darwin": "mac"}[platform.system()]
    machine = {"x86_64": "amd64", "AMD64": "amd64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine()]
    return f"{system}_{machine}"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Outcome:
    code: int
    output: str


@dataclass(frozen=True)
class Fe:
    binary: Path
    version: str
    commit: str
    binary_sha256: str
    platform: str

    @property
    def native(self) -> bool:
        return self.platform in NATIVE_PLATFORMS

    def run(self, args: list[str], cwd: Path) -> Outcome:
        proc = subprocess.run(
            [str(self.binary), "--color", "never", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        return Outcome(proc.returncode, normalize(proc.stdout + proc.stderr))


def normalize(output: str) -> str:
    """Strips timings and trailing space so outputs compare across runs."""
    lines = [_TIMING.sub("", line).rstrip() for line in output.splitlines()]
    return "\n".join(line for line in lines if line) + "\n"


def resolve() -> Fe:
    lock = read_lock()
    plat = host_platform()
    binary = Path(os.environ.get("FE", ROOT / ".tools" / f"fe-{lock['version']}" / "fe"))
    if not binary.is_file():
        raise SystemExit(f"Fe not found at {binary}; run `make toolchain`")

    digest = sha256_file(binary)
    expected = lock.get(f"sha256_{plat}")
    if digest != expected and not os.environ.get("FE_ALLOW_UNPINNED"):
        raise SystemExit(f"{binary} is not the pinned Fe {lock['version']} for {plat} (sha256 {digest})")

    reported = subprocess.run([str(binary), "--version"], capture_output=True, text=True).stdout.strip()
    if reported != f"fe {lock['version']} ({lock['commit'][:7]})":
        raise SystemExit(f"unexpected compiler version: {reported}")

    return Fe(binary, lock["version"], lock["commit"], digest, plat)
